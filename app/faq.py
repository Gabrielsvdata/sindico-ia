"""Respostas sem IA: perguntas frequentes (por palavra-chave) e cache de respostas já dadas.

Economiza chamadas ao modelo e responde na hora as dúvidas mais repetidas.
"""

import json
import re
from functools import lru_cache

from . import config
from .ai import normalizar
from .schemas import AnaliseIA

# Mensagens longas costumam misturar vários assuntos: essas vão sempre para a IA.
TAMANHO_MAXIMO_FAQ = 250

# Sinais de reclamação ou problema: a mensagem não é uma dúvida simples, então vai para a IA.
# Ex.: "meu boleto veio errado, onde resolvo?" não deve receber a resposta pronta sobre segunda via.
SINAIS_DE_PROBLEMA = (
    "errad", "cobra", "quebr", "vaza", "vazou", "barulho", "nao funciona", "parou", "estrag", "reclam",
    "absurd", "problema", "defeito", "suj", "entup", "espalh", "briga", "ameac", "denunc", "multa",
    "vizinh", "de novo", "toda hora", "todo dia", "toda noite",
)


@lru_cache
def carregar_faq() -> list[dict]:
    return json.loads(config.FAQ_PATH.read_text(encoding="utf-8"))


def chave_cache(texto: str) -> str:
    """Mesma pergunta escrita de jeitos parecidos vira a mesma chave ("Piscina abre que horas??" == "piscina abre que horas")."""
    t = normalizar(texto)
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def buscar_faq(texto: str) -> dict | None:
    if len(texto) > TAMANHO_MAXIMO_FAQ:
        return None
    t = " " + chave_cache(texto) + " "
    if any(" " + s in t for s in SINAIS_DE_PROBLEMA):
        return None
    for item in carregar_faq():
        # Cada grupo precisa ter pelo menos uma palavra presente (no início de uma palavra da mensagem)
        if all(any(" " + palavra in t for palavra in grupo) for grupo in item["palavras_chave"]):
            return item
    return None


def analise_da_faq(item: dict, texto: str) -> AnaliseIA:
    return AnaliseIA(
        categoria="duvida",
        prioridade="baixa",
        setor=item["setor"],
        sentimento="neutro",
        resumo=f"Dúvida frequente ({item['id']}): {texto[:200]}",
        resposta_morador=item["resposta"],
        respondido_pelo_regimento=True,
        trecho_regimento=item["trecho_regimento"],
        transcricao_anexo=None,
        confianca=1.0,
    )
