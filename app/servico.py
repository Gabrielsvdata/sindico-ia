"""Regras de negócio: o que fazer com a análise da IA.

A IA interpreta a mensagem; a DECISÃO de ação é feita aqui, em código, de forma previsível.
"""

from . import config, db
from .ai import analisar_mensagem, normalizar
from .faq import analise_da_faq, buscar_faq, chave_cache
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


def parece_emergencia(texto: str) -> bool:
    t = normalizar(texto)
    return any(p in t for p in PALAVRAS_EMERGENCIA)


def obter_analise(msg: MensagemEntrada) -> tuple[AnaliseIA, str]:
    """Tenta responder sem IA (FAQ, depois cache). Emergências e anexos vão sempre para a IA."""
    if not parece_emergencia(msg.texto) and not msg.anexo_base64:
        item = buscar_faq(msg.texto)
        if item:
            return analise_da_faq(item, msg.texto), "faq"
        guardada = db.buscar_cache(chave_cache(msg.texto), config.CACHE_DIAS)
        if guardada:
            return guardada, "cache"
    return analisar_mensagem(msg), "ia"


def processar_mensagem(msg: MensagemEntrada) -> dict:
    analise, origem = obter_analise(msg)
    analise, regra = aplicar_guarda_corpo(msg.texto, analise)
    acao = decidir_acao(analise)
    status = "resolvido" if acao == "responder_automaticamente" else "aberto"

    # Só guarda no cache respostas genéricas, que servem para qualquer morador
    if origem == "ia" and acao == "responder_automaticamente" and not msg.anexo_base64:
        db.salvar_cache(chave_cache(msg.texto), analise)

    chamado = db.criar_chamado(
        morador=msg.morador,
        apartamento=msg.apartamento,
        canal=msg.canal,
        texto=msg.texto,
        acao=acao,
        status=status,
        analise=analise,
        regra_seguranca=regra,
        origem=origem,
    )
    return {
        **chamado.model_dump(mode="json"),
        # Campos "achatados" para facilitar o uso no n8n
        "prioridade": analise.prioridade,
        "setor": analise.setor,
        "categoria": analise.categoria,
        "resposta_morador": analise.resposta_morador,
        "origem": origem,
        "notificacao_setor": montar_notificacao(chamado),
    }
