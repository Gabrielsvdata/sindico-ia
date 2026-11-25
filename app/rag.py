"""RAG sobre a base de perguntas frequentes (data/faq.json).

A base do FAQ é a ÚNICA fonte de conhecimento que a IA pode usar para responder dúvidas.
Para cada mensagem, buscamos as entradas mais parecidas (BM25) e só elas vão para o prompt.
Depois validamos que a IA citou apenas entradas que recebeu: se citar outra coisa, ou
não citar nada, a resposta não é tratada como resolvida e vira chamado para um humano.
"""

import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache

from .ai import normalizar
from .faq import carregar_faq

# Palavras que não ajudam a diferenciar um assunto do outro
STOPWORDS = set("""
a o os as um uma uns umas de do da dos das em no na nos nas por pelo pela para pra pro com sem
e ou que se eu voce voces ele ela eles elas meu minha meus minhas seu sua nosso nossa isso isto esse essa
este esta aqui ai la ja nao sim mais menos muito pouco tem ter tenho ha foi ser sao estou esta estao
como qual quais quando onde quem porque oi ola bom boa dia tarde noite obrigado obrigada favor gostaria
queria preciso posso pode podem saber sobre ate
""".split())

K1, B = 1.5, 0.75
TAMANHO_RAIZ = 5
MAX_TRECHOS = 3
SCORE_MINIMO = 1.5


def tokens(texto: str) -> list[str]:
    palavras = re.findall(r"[a-z0-9]+", normalizar(texto))
    return [raiz(p) for p in palavras if p not in STOPWORDS and len(p) > 1]


def raiz(palavra: str) -> str:
    """Radical por prefixo, robusto para o português:
    'reciclavel', 'reciclaveis' e 'reciclagem' viram 'recic'; 'churrasco' e 'churrasqueira' viram 'churr'."""
    return palavra[:TAMANHO_RAIZ]


@dataclass
class Trecho:
    id: str
    pergunta: str
    resposta: str
    trecho_regimento: str
    setor: str
    score: float

    def para_prompt(self) -> str:
        return f'[{self.id}] Pergunta: {self.pergunta}\nResposta oficial: {self.resposta}\nRegimento: {self.trecho_regimento}'


@lru_cache
def _indice():
    docs = []
    for item in carregar_faq():
        texto = " ".join([item["pergunta"], *item.get("perguntas_alternativas", []), item["resposta"],
                          item["trecho_regimento"]])
        # A pergunta e as variações pesam mais que o texto da resposta
        perguntas = " ".join([item["pergunta"], *item.get("perguntas_alternativas", [])])
        docs.append((item, Counter(tokens(texto)) + Counter(tokens(perguntas))))
    n = len(docs)
    tamanho_medio = sum(sum(c.values()) for _, c in docs) / max(n, 1)
    df = Counter(t for _, c in docs for t in c)
    idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
    return docs, tamanho_medio, idf


def buscar(texto: str, k: int = MAX_TRECHOS) -> list[Trecho]:
    docs, tamanho_medio, idf = _indice()
    consulta = set(tokens(texto))
    resultados = []
    for item, freq in docs:
        tamanho = sum(freq.values())
        score = 0.0
        for termo in consulta:
            f = freq.get(termo, 0)
            if f:
                score += idf[termo] * f * (K1 + 1) / (f + K1 * (1 - B + B * tamanho / tamanho_medio))
        if score >= SCORE_MINIMO:
            resultados.append(Trecho(item["id"], item["pergunta"], item["resposta"], item["trecho_regimento"],
                                     item["setor"], round(score, 2)))
    resultados.sort(key=lambda t: t.score, reverse=True)
    return resultados[:k]
