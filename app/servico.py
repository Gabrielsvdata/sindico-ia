"""Regras de negócio: o que fazer com a análise da IA.

A IA interpreta a mensagem; a DECISÃO de ação é feita aqui, em código, de forma previsível.
"""

from . import db
from .ai import analisar_mensagem, normalizar
from .schemas import AnaliseIA, Chamado, MensagemEntrada

# Guarda-corpo: se a mensagem tiver estes termos, é emergência mesmo que a IA erre.
PALAVRAS_EMERGENCIA = (
    "vazamento de gas", "cheiro de gas", "vazando gas", "incendio", "pegando fogo", "fumaca",
    "preso no elevador", "presa no elevador", "presos no elevador", "curto-circuito", "curto circuito",
    "choque eletrico", "desmaiou", "invasao", "invadiu", "assalto",
)

EMOJI_PRIORIDADE = {"baixa": "🟢", "media": "🟡", "alta": "🟠", "critica": "🔴"}


def aplicar_guarda_corpo(texto: str, analise: AnaliseIA) -> tuple[AnaliseIA, bool]:
    t = normalizar(texto)
    if analise.prioridade != "critica" and any(p in t for p in PALAVRAS_EMERGENCIA):
        corrigida = analise.model_copy(update={"prioridade": "critica", "setor": "portaria"})
        return corrigida, True
    return analise, False


def decidir_acao(analise: AnaliseIA) -> str:
    if analise.prioridade == "critica":
        return "emergencia"
    if analise.respondido_pelo_regimento and analise.categoria == "duvida" and analise.confianca >= 0.6:
        return "responder_automaticamente"
    return "abrir_chamado"


def montar_notificacao(chamado: Chamado) -> str:
    a = chamado.analise
    apto = f" (apto {chamado.apartamento})" if chamado.apartamento else ""
    linhas = [
        f"{EMOJI_PRIORIDADE[a.prioridade]} Chamado #{chamado.id} — prioridade {a.prioridade.upper()}",
        f"Setor: {a.setor} | Categoria: {a.categoria}",
        f"Morador: {chamado.morador}{apto}",
        f"Resumo: {a.resumo}",
    ]
    if a.transcricao_anexo:
        linhas.append(f"Anexo: {a.transcricao_anexo}")
    return "\n".join(linhas)


def processar_mensagem(msg: MensagemEntrada) -> dict:
    analise = analisar_mensagem(msg)
    analise, regra = aplicar_guarda_corpo(msg.texto, analise)
    acao = decidir_acao(analise)
    status = "resolvido" if acao == "responder_automaticamente" else "aberto"

    chamado = db.criar_chamado(
        morador=msg.morador,
        apartamento=msg.apartamento,
        canal=msg.canal,
        texto=msg.texto,
        acao=acao,
        status=status,
        analise=analise,
        regra_seguranca=regra,
    )
    return {
        **chamado.model_dump(mode="json"),
        # Campos "achatados" para facilitar o uso no n8n
        "prioridade": analise.prioridade,
        "setor": analise.setor,
        "categoria": analise.categoria,
        "resposta_morador": analise.resposta_morador,
        "notificacao_setor": montar_notificacao(chamado),
    }
