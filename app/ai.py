"""Comunicação com o modelo de IA.

Dois provedores:
- gemini: chama a API do Google Gemini (exige GEMINI_API_KEY)
- mock: regras simples por palavra-chave, para testar o fluxo sem chave e sem internet
"""

import json
import logging
from contextvars import ContextVar
import time
import unicodedata

import httpx
from pydantic import BaseModel, ValidationError

from . import config
from .prompts import PROMPT_RESUMO, montar_mensagem_usuario, montar_system_prompt
from .schemas import AnaliseIA, MensagemEntrada

log = logging.getLogger("sindico_ia.ai")

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
# Erros passageiros do Google: limite de uso (429), sobrecarga (500, 503) e tempo esgotado (504)
STATUS_TEMPORARIOS = {429, 500, 503, 504}


class RespostaTimeout:
    status_code = 504
    text = "O Gemini demorou demais para responder (tempo esgotado)."


# Qual modelo respondeu de fato a última chamada (o principal ou um reserva)
modelo_usado: ContextVar[str] = ContextVar("modelo_usado", default="")


class ErroIA(Exception):
    pass


class ResumoIA(BaseModel):
    resumo: str
    destaques: list[str]


def normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sem_acento.lower()


# ---------------------------------------------------------------- Gemini

def _chamar_gemini(system: str, partes: list[dict]) -> str:
    if not config.GEMINI_API_KEY:
        raise ErroIA("GEMINI_API_KEY não configurada. Defina no .env ou use AI_PROVIDER=mock.")

    corpo = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": partes}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
    }
    resp = None
    # Tenta o modelo principal e depois os reservas; em cada um, repete se o Google estiver sobrecarregado.
    for modelo in [config.GEMINI_MODEL, *config.GEMINI_MODELOS_RESERVA]:
        for tentativa in range(config.AI_TENTATIVAS_SOBRECARGA):
            try:
                resp = httpx.post(
                    GEMINI_URL.format(model=modelo),
                    headers={"x-goog-api-key": config.GEMINI_API_KEY},
                    json=corpo,
                    timeout=config.AI_TIMEOUT_SEGUNDOS,
                )
            except httpx.TimeoutException:
                # Modelo lento por sobrecarga: trata como erro passageiro (504)
                resp = RespostaTimeout()
            except httpx.HTTPError as e:
                raise ErroIA(f"Falha de rede ao chamar o Gemini: {e}") from e

            if resp.status_code not in STATUS_TEMPORARIOS:
                break
            espera = 2 ** (tentativa + 1)
            log.warning("Gemini %s respondeu %s; nova tentativa em %ss", modelo, resp.status_code, espera)
            if tentativa + 1 < config.AI_TENTATIVAS_SOBRECARGA:
                time.sleep(espera)

        if resp.status_code == 200 or resp.status_code not in STATUS_TEMPORARIOS:
            break
        log.warning("Modelo %s indisponível, tentando o próximo da lista", modelo)

    if resp.status_code != 200:
        raise ErroIA(f"Gemini respondeu {resp.status_code}: {resp.text[:300]}")

    modelo_usado.set(modelo)
    try:
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, ValueError) as e:
        raise ErroIA(f"Resposta inesperada do Gemini: {resp.text[:300]}") from e


def _gerar_validado(system: str, partes: list[dict], modelo: type[BaseModel]) -> BaseModel:
    """Pede o JSON à IA e valida com Pydantic. Se vier errado, devolve o erro à IA e tenta de novo."""
    ultimo_erro = ""
    for tentativa in range(1, config.AI_MAX_TENTATIVAS + 1):
        partes_tentativa = list(partes)
        if ultimo_erro:
            partes_tentativa.append({
                "text": f"Sua resposta anterior era inválida ({ultimo_erro}). "
                        "Corrija e devolva somente o JSON no formato pedido."
            })
        bruto = _chamar_gemini(system, partes_tentativa)
        try:
            return modelo.model_validate(json.loads(bruto))
        except (json.JSONDecodeError, ValidationError) as e:
            ultimo_erro = str(e).splitlines()[0][:300]
            log.warning("Tentativa %s: JSON inválido da IA: %s", tentativa, ultimo_erro)
    raise ErroIA(f"A IA não devolveu um JSON válido após {config.AI_MAX_TENTATIVAS} tentativas: {ultimo_erro}")


# ---------------------------------------------------------------- Mock

def _analisar_mock(msg: MensagemEntrada, trechos: list) -> AnaliseIA:
    t = normalizar(msg.texto)

    def tem(*palavras: str) -> bool:
        return any(p in t for p in palavras)

    if tem("gas", "fogo", "incendio", "fumaca", "preso no elevador", "curto"):
        cat, pri, setor = "seguranca", "critica", "portaria"
        resposta = "Isso é uma emergência! Ligue agora para a portaria (ramal 9) e, se houver risco à vida, para os bombeiros (193). O zelador de plantão já foi acionado."
    elif tem("vazamento", "vazando", "infiltra", "goteira", "elevador", "sem agua", "portao"):
        cat, pri, setor = "manutencao", "alta", "zeladoria"
        resposta = "Recebemos seu aviso e abrimos um chamado para a zeladoria com prioridade alta."
    elif tem("barulho", "som alt", "festa", "musica", "gritaria"):
        cat, pri, setor = "barulho", "media", "sindico"
        resposta = "Registramos sua reclamação de barulho. O horário de silêncio é das 22h às 8h (dom. a qui.) e das 23h às 9h (sex., sáb. e vésperas de feriado). O síndico foi informado."
    elif tem("boleto", "taxa", "cobranca", "multa", "pagamento"):
        cat, pri, setor = "financeiro", "media", "administracao"
        resposta = "A taxa condominial vence no dia 10. A segunda via está no aplicativo ou na administração (seg. a sex., 9h às 17h)."
    elif tem("encomenda", "pacote", "entrega"):
        cat, pri, setor = "encomenda", "baixa", "portaria"
        resposta = "Encomendas ficam na portaria por até 7 dias. Passe lá para retirar."
    elif tem("?", "posso", "pode", "horario", "como faco", "qual"):
        cat, pri, setor = "duvida", "baixa", "administracao"
        resposta = "Encaminhamos sua dúvida para a administração, que vai responder em breve."
    else:
        cat, pri, setor = "outros", "baixa", "administracao"
        resposta = "Recebemos sua mensagem e encaminhamos para a administração."

    # Simula o RAG: se é uma dúvida e a busca achou uma entrada bem parecida, responde com ela
    respondido, fontes = False, []
    if cat in ("duvida", "outros", "encomenda") and trechos and trechos[0].score >= 4:
        cat, pri, setor = "duvida", "baixa", trechos[0].setor
        respondido, fontes, resposta = True, [trechos[0].id], trechos[0].resposta

    sentimento = "negativo" if tem("absurdo", "!!", "inaceitavel", "de novo", "cansad") else "neutro"

    return AnaliseIA(
        categoria=cat,
        prioridade=pri,
        setor=setor,
        sentimento=sentimento,
        resumo=msg.texto[:280],
        resposta_morador=resposta,
        respondido_pelo_regimento=respondido,
        fontes=fontes,
        trecho_regimento=None,
        transcricao_anexo=None,
        confianca=0.8 if respondido else 0.6,
    )


# ---------------------------------------------------------------- API pública

def analisar_mensagem(msg: MensagemEntrada, trechos: list | None = None) -> AnaliseIA:
    """Classifica a mensagem. `trechos` são as entradas do FAQ recuperadas pelo RAG (única base permitida)."""
    trechos = trechos or []
    if config.AI_PROVIDER == "mock":
        modelo_usado.set("mock")
        return _analisar_mock(msg, trechos)

    partes: list[dict] = [{"text": montar_mensagem_usuario(msg.texto, msg.morador, msg.apartamento)}]
    if msg.anexo_base64 and msg.anexo_mime:
        partes.append({"inlineData": {"mimeType": msg.anexo_mime, "data": msg.anexo_base64}})
    return _gerar_validado(montar_system_prompt(trechos), partes, AnaliseIA)


def resumir_chamados(chamados: list[dict]) -> ResumoIA:
    if not chamados:
        return ResumoIA(resumo="Nenhum chamado registrado hoje.", destaques=[])

    if config.AI_PROVIDER == "mock":
        criticos = [c for c in chamados if c["prioridade"] == "critica"]
        return ResumoIA(
            resumo=f"Hoje foram registrados {len(chamados)} chamado(s), sendo {len(criticos)} crítico(s).",
            destaques=[f"[{c['prioridade']}] {c['resumo']}" for c in chamados[:5]],
        )

    texto = PROMPT_RESUMO.format(chamados=json.dumps(chamados, ensure_ascii=False, indent=1))
    return _gerar_validado("Você resume chamados de condomínio. Responda só em JSON.", [{"text": texto}], ResumoIA)
