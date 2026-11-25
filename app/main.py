import logging
from contextlib import asynccontextmanager
from datetime import date
from typing import Optional

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import config, db
from .ai import ErroIA, resumir_chamados
from .prompts import PROMPT_VERSAO
from .schemas import (
    AtualizarStatus, Chamado, Encaminhar, Evento, MensagemEntrada, MudarPrioridade, NovaInteracao, Prioridade,
    ResumoDiario, Setor, Status,
)
from . import servico
from .rag import buscar as buscar_na_base
from .servico import ErroRegra, LimiteIAAtingido, consumir_cota_ia, processar_mensagem

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.iniciar()
    yield


app = FastAPI(
    title="Síndico IA",
    description="Central inteligente de atendimento para condomínios: classifica, prioriza, "
                "responde dúvidas pelo regimento e resume o dia para o síndico.",
    version="1.0.0",
    lifespan=lifespan,
)


STATIC_DIR = Path(__file__).parent / "static"
app.mount("/painel", StaticFiles(directory=STATIC_DIR, html=True), name="painel")


@app.get("/", include_in_schema=False)
def raiz():
    return RedirectResponse("/painel/")


@app.get("/health", tags=["sistema"])
def health():
    return {
        "status": "ok", "provedor_ia": config.AI_PROVIDER, "modelo": config.GEMINI_MODEL, "prompt": PROMPT_VERSAO,
        "n8n_webhook_url": config.N8N_WEBHOOK_URL,
        "uso_ia_hoje": db.uso_ia_hoje(), "limite_ia_diario": config.AI_LIMITE_DIARIO or None,
    }


@app.post("/mensagens", tags=["atendimento"], summary="Recebe a mensagem de um morador e analisa com IA")
def receber_mensagem(msg: MensagemEntrada):
    try:
        return processar_mensagem(msg)
    except LimiteIAAtingido as e:
        raise HTTPException(status_code=429, detail=str(e)) from e
    except ErroIA as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@app.get("/chamados", tags=["chamados"], response_model=list[Chamado])
def listar_chamados(
    status: Optional[Status] = None,
    prioridade: Optional[Prioridade] = None,
    setor: Optional[Setor] = None,
    limite: int = Query(100, ge=1, le=500),
):
    return db.listar(status, prioridade, setor, limite)


@app.get("/base-conhecimento/buscar", tags=["base de conhecimento"],
         summary="O que o RAG recuperaria da base de perguntas frequentes para um texto")
def buscar_base(q: str = Query(..., min_length=2, max_length=500)):
    return [t.__dict__ for t in buscar_na_base(q)]


@app.get("/caixas", tags=["chamados"], summary="Quantos chamados cada setor tem para atender agora")
def caixas():
    return db.caixas()


@app.get("/chamados/criticos-parados", tags=["chamados"], response_model=list[Chamado],
         summary="Chamados críticos ainda abertos há mais de N minutos (usado no escalonamento)")
def criticos_parados(minutos: int = Query(30, ge=0)):
    return db.criticos_parados(minutos)


@app.get("/chamados/{chamado_id}", tags=["chamados"], response_model=Chamado)
def obter_chamado(chamado_id: int):
    chamado = db.buscar(chamado_id)
    if not chamado:
        raise HTTPException(404, "Chamado não encontrado")
    return chamado


def _executar(acao, *args):
    """Traduz erros de regra de negócio para respostas HTTP."""
    try:
        return acao(*args)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except ErroRegra as e:
        raise HTTPException(409, str(e)) from e


@app.get("/chamados/{chamado_id}/eventos", tags=["chamados"], response_model=list[Evento],
         summary="Histórico completo: mensagem, análise, respostas, alertas e ações da equipe")
def eventos(chamado_id: int):
    if not db.buscar(chamado_id):
        raise HTTPException(404, "Chamado não encontrado")
    return db.listar_eventos(chamado_id)


@app.patch("/chamados/{chamado_id}", tags=["chamados"], response_model=Chamado,
           summary="Assumir, resolver (com descrição do que foi feito) ou reabrir")
def mudar_status(chamado_id: int, body: AtualizarStatus):
    return _executar(servico.mudar_status, chamado_id, body.status, body.responsavel, body.nota)


@app.post("/chamados/{chamado_id}/interacoes", tags=["chamados"], response_model=Chamado,
          summary="Responder ao morador, registrar nota interna ou nova mensagem do morador")
def interagir(chamado_id: int, body: NovaInteracao):
    return _executar(servico.registrar_interacao, chamado_id, body.tipo, body.autor, body.texto)


@app.post("/chamados/{chamado_id}/encaminhar", tags=["chamados"], response_model=Chamado,
          summary="Passar o chamado para outro setor (o novo setor é avisado)")
def encaminhar(chamado_id: int, body: Encaminhar):
    return _executar(servico.encaminhar, chamado_id, body.setor, body.autor, body.motivo)


@app.post("/chamados/{chamado_id}/prioridade", tags=["chamados"], response_model=Chamado,
          summary="Corrigir a prioridade definida pela IA")
def mudar_prioridade(chamado_id: int, body: MudarPrioridade):
    return _executar(servico.mudar_prioridade, chamado_id, body.prioridade, body.autor, body.motivo)


@app.get("/resumo-diario", tags=["relatórios"], response_model=ResumoDiario,
         summary="Resumo do dia gerado pela IA para o síndico")
def resumo_diario(dia: Optional[date] = None):
    dia_str = (dia or date.today()).isoformat()
    chamados = db.do_dia(dia_str)
    compactos = [
        {
            "id": c.id,
            "categoria": c.analise.categoria,
            "prioridade": c.prioridade,
            "setor": c.setor,
            "status": c.status,
            "resumo": c.analise.resumo,
        }
        for c in chamados
    ]
    try:
        if compactos:
            consumir_cota_ia()
        r = resumir_chamados(compactos)
    except LimiteIAAtingido as e:
        raise HTTPException(status_code=429, detail=str(e)) from e
    except ErroIA as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return ResumoDiario(
        data=dia_str,
        total_chamados=len(chamados),
        resumo=r.resumo,
        destaques=r.destaques,
        pendencias_criticas=sum(1 for c in chamados if c.prioridade == "critica" and c.status != "resolvido"),
    )


@app.get("/metricas", tags=["relatórios"])
def metricas():
    m = db.metricas()
    sem_ia = m["por_origem"].get("faq", 0) + m["por_origem"].get("cache", 0)
    m["chamadas_ia_economizadas"] = sem_ia
    m["percentual_sem_ia"] = round(100 * sem_ia / m["total"], 1) if m["total"] else 0.0
    return m
