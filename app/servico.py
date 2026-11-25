"""Regras de negócio: o que fazer com a análise da IA.

A IA interpreta a mensagem; a DECISÃO de ação é feita aqui, em código, de forma previsível.
"""

from . import config, db
from .ai import analisar_mensagem, modelo_usado, normalizar
from .faq import analise_da_faq, buscar_faq, carregar_faq, chave_cache
from .rag import buscar as buscar_na_base
from .schemas import AnaliseIA, Chamado, MensagemEntrada

ROTULO_PRIORIDADE = {"baixa": "Baixa", "media": "Média", "alta": "Alta", "critica": "Crítica"}
ROTULO_SETOR = {"zeladoria": "Zeladoria", "portaria": "Portaria", "administracao": "Administração", "sindico": "Síndico"}
ROTULO_CATEGORIA = {
    "manutencao": "manutenção", "barulho": "barulho", "duvida": "dúvida", "encomenda": "encomenda",
    "financeiro": "financeiro", "seguranca": "segurança", "reclamacao": "reclamação", "outros": "outros",
}
ROTULO_ORIGEM = {"faq": "perguntas frequentes (sem IA)", "cache": "resposta já dada antes (sem IA)", "ia": "IA"}


PERGUNTAS = {item["id"]: item["pergunta"] for item in carregar_faq()}


class LimiteIAAtingido(Exception):
    """A cota diária de chamadas à IA acabou."""


class ErroRegra(Exception):
    """Ação não permitida no estado atual do chamado."""

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
        f"{EMOJI_PRIORIDADE[chamado.prioridade]} Chamado #{chamado.id} — prioridade {chamado.prioridade.upper()}",
        f"Setor: {chamado.setor} | Categoria: {a.categoria}",
        f"Morador: {chamado.morador}{apto}",
        f"Resumo: {a.resumo}",
    ]
    if a.transcricao_anexo:
        linhas.append(f"Anexo: {a.transcricao_anexo}")
    return "\n".join(linhas)


def parece_emergencia(texto: str) -> bool:
    t = normalizar(texto)
    return any(p in t for p in PALAVRAS_EMERGENCIA)


def consumir_cota_ia() -> None:
    """Bloqueia novas chamadas à IA quando o limite diário é atingido (AI_LIMITE_DIARIO)."""
    if config.AI_PROVIDER == "mock" or config.AI_LIMITE_DIARIO <= 0:
        return
    if db.uso_ia_hoje() >= config.AI_LIMITE_DIARIO:
        raise LimiteIAAtingido(
            f"O limite de {config.AI_LIMITE_DIARIO} análises com IA por dia foi atingido. "
            "Dúvidas do FAQ continuam sendo respondidas; as demais voltam a funcionar amanhã."
        )
    db.registrar_uso_ia()


def validar_fontes(analise: AnaliseIA, trechos: list) -> tuple[AnaliseIA, list[str]]:
    """Anti-alucinação: a IA só pode citar entradas que o RAG entregou a ela.

    - Fontes que não estavam no contexto são descartadas.
    - Se a IA diz que respondeu a dúvida mas não citou nenhuma fonte válida, a resposta não é
      considerada resolvida: vira chamado para um humano conferir.
    - A citação mostrada ao morador vem do texto oficial do FAQ, nunca de algo escrito pela IA.
    """
    permitidas = {t.id: t for t in trechos}
    validas = [f for f in analise.fontes if f in permitidas]
    descartadas = [f for f in analise.fontes if f not in permitidas]
    mudancas = {"fontes": validas, "trecho_regimento": permitidas[validas[0]].trecho_regimento if validas else None}
    if analise.respondido_pelo_regimento and not validas:
        mudancas["respondido_pelo_regimento"] = False
    return analise.model_copy(update=mudancas), descartadas


def obter_analise(msg: MensagemEntrada) -> tuple[AnaliseIA, str, dict]:
    """Ordem: FAQ exato (sem IA) -> cache (sem IA) -> RAG + IA. Emergências e anexos vão direto para a IA."""
    if not parece_emergencia(msg.texto) and not msg.anexo_base64:
        item = buscar_faq(msg.texto)
        if item:
            return analise_da_faq(item, msg.texto), "faq", {"consultadas": [{"id": item["id"], "pergunta": item["pergunta"], "score": None}]}
        guardada = db.buscar_cache(chave_cache(msg.texto), config.CACHE_DIAS)
        if guardada:
            return guardada, "cache", {"consultadas": []}

    consumir_cota_ia()
    trechos = buscar_na_base(msg.texto)
    analise = analisar_mensagem(msg, trechos)
    analise, descartadas = validar_fontes(analise, trechos)
    rag = {
        "consultadas": [{"id": t.id, "pergunta": t.pergunta, "score": t.score} for t in trechos],
        "descartadas": descartadas,
    }
    return analise, "ia", rag


def processar_mensagem(msg: MensagemEntrada) -> dict:
    analise, origem, rag = obter_analise(msg)
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
    registrar_historico_inicial(chamado, origem, modelo_usado.get() if origem == "ia" else "", rag)
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


# ---------------------------------------------------------------- Histórico

def registrar_historico_inicial(chamado: Chamado, origem: str, modelo: str, rag: dict | None = None) -> None:
    """Grava a conversa: o que chegou, o que foi entendido, o que foi respondido e quem foi avisado."""
    a = chamado.analise
    apto = f" (apto {chamado.apartamento})" if chamado.apartamento else ""
    db.registrar_evento(chamado.id, "mensagem_morador", f"{chamado.morador}{apto}", chamado.texto,
                        dados={"canal": chamado.canal})

    fonte = ROTULO_ORIGEM[origem] + (f" (modelo {modelo})" if modelo else "")
    db.registrar_evento(
        chamado.id, "analise", "Síndico IA",
        f"Classificado como {ROTULO_CATEGORIA[a.categoria]}, prioridade {ROTULO_PRIORIDADE[a.prioridade].lower()}, "
        f"para {ROTULO_SETOR[a.setor]}.",
        dados={
            "origem": origem, "fonte": fonte, "modelo": modelo or None, "confianca": a.confianca,
            "sentimento": a.sentimento, "trecho_regimento": a.trecho_regimento,
            "guarda_corpo": chamado.regra_seguranca_aplicada, "resumo": a.resumo,
            "transcricao_anexo": a.transcricao_anexo,
            "fontes": [{"id": f, "pergunta": PERGUNTAS.get(f, f)} for f in a.fontes],
            "base_consultada": (rag or {}).get("consultadas", []),
            "fontes_descartadas": (rag or {}).get("descartadas", []),
        },
    )
    db.registrar_evento(chamado.id, "resposta_morador", "Síndico IA (automática)", a.resposta_morador,
                        destino=chamado.morador)

    if chamado.acao == "responder_automaticamente":
        db.registrar_evento(chamado.id, "status", "Síndico IA", "Encerrado: dúvida respondida com o regimento.",
                            dados={"de": "aberto", "para": "resolvido"})
        return

    destinos = [ROTULO_SETOR[a.setor]]
    if chamado.acao == "emergencia":
        destinos = ["Portaria", "Zelador de plantão", "Síndico"]
    for destino in destinos:
        db.registrar_evento(chamado.id, "alerta_setor", "n8n", montar_notificacao(chamado), destino=destino)


# ---------------------------------------------------------------- Ações da equipe

def _obter(chamado_id: int) -> Chamado:
    chamado = db.buscar(chamado_id)
    if not chamado:
        raise LookupError("Chamado não encontrado")
    return chamado


def mudar_status(chamado_id: int, status: str, autor: str | None, nota: str | None) -> Chamado:
    atual = _obter(chamado_id)
    if atual.status == status:
        raise ErroRegra(f"O chamado já está {status.replace('_', ' ')}.")
    if status == "resolvido" and not (nota and nota.strip()):
        raise ErroRegra("Descreva o que foi feito para resolver o chamado.")

    autor = autor or "Equipe"
    textos = {
        "em_andamento": f"{autor} assumiu o chamado." if atual.status == "aberto" else f"{autor} reabriu o chamado.",
        "resolvido": f"Resolvido por {autor}.",
        "aberto": f"{autor} reabriu o chamado.",
    }
    chamado = db.atualizar_status(chamado_id, status, autor)
    db.registrar_evento(chamado_id, "status", autor, textos[status] + (f" {nota.strip()}" if nota else ""),
                        dados={"de": atual.status, "para": status, "nota": nota})
    return chamado


def registrar_interacao(chamado_id: int, tipo: str, autor: str, texto: str) -> Chamado:
    chamado = _obter(chamado_id)
    destino = chamado.morador if tipo == "resposta_morador" else None
    db.registrar_evento(chamado_id, tipo, autor, texto.strip(), destino=destino)
    # Morador voltou a escrever num chamado encerrado: reabre
    if tipo == "mensagem_morador" and chamado.status == "resolvido":
        db.atualizar_status(chamado_id, "aberto", None)
        db.registrar_evento(chamado_id, "status", "Síndico IA", "Reaberto: o morador enviou uma nova mensagem.",
                            dados={"de": "resolvido", "para": "aberto"})
    return _obter(chamado_id)


def encaminhar(chamado_id: int, setor: str, autor: str, motivo: str | None) -> Chamado:
    atual = _obter(chamado_id)
    if atual.setor == setor:
        raise ErroRegra(f"O chamado já está com {ROTULO_SETOR[setor]}.")
    chamado = db.atualizar_campo(chamado_id, "setor", setor)
    texto = f"Encaminhado de {ROTULO_SETOR[atual.setor]} para {ROTULO_SETOR[setor]}."
    db.registrar_evento(chamado_id, "encaminhamento", autor, texto + (f" Motivo: {motivo.strip()}" if motivo else ""),
                        destino=ROTULO_SETOR[setor], dados={"de": atual.setor, "para": setor})
    db.registrar_evento(chamado_id, "alerta_setor", "n8n", montar_notificacao(chamado), destino=ROTULO_SETOR[setor])
    return chamado


def mudar_prioridade(chamado_id: int, prioridade: str, autor: str, motivo: str | None) -> Chamado:
    atual = _obter(chamado_id)
    if atual.prioridade == prioridade:
        raise ErroRegra("O chamado já tem essa prioridade.")
    chamado = db.atualizar_campo(chamado_id, "prioridade", prioridade)
    texto = f"Prioridade alterada de {ROTULO_PRIORIDADE[atual.prioridade]} para {ROTULO_PRIORIDADE[prioridade]}."
    db.registrar_evento(chamado_id, "prioridade", autor, texto + (f" Motivo: {motivo.strip()}" if motivo else ""),
                        dados={"de": atual.prioridade, "para": prioridade})
    return chamado
