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
from .schemas import AtualizarStatus, Chamado, MensagemEntrada, Prioridade, ResumoDiario, Status
from .servico import processar_mensagem

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
    return {"status": "ok", "provedor_ia": config.AI_PROVIDER, "modelo": config.GEMINI_MODEL, "prompt": PROMPT_VERSAO}


@app.post("/mensagens", tags=["atendimento"], summary="Recebe a mensagem de um morador e analisa com IA")
def receber_mensagem(msg: MensagemEntrada):
    try:
        return processar_mensagem(msg)
    except ErroIA as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@app.get("/chamados", tags=["chamados"], response_model=list[Chamado])
def listar_chamados(
    status: Optional[Status] = None,
    prioridade: Optional[Prioridade] = None,
    limite: int = Query(100, ge=1, le=500),
):
    return db.listar(status, prioridade, limite)


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


@app.patch("/chamados/{chamado_id}", tags=["chamados"], response_model=Chamado)
def mudar_status(chamado_id: int, body: AtualizarStatus):
    chamado = db.atualizar_status(chamado_id, body.status, body.responsavel)
    if not chamado:
        raise HTTPException(404, "Chamado não encontrado")
    return chamado


@app.get("/resumo-diario", tags=["relatórios"], response_model=ResumoDiario,
         summary="Resumo do dia gerado pela IA para o síndico")
def resumo_diario(dia: Optional[date] = None):
    dia_str = (dia or date.today()).isoformat()
    chamados = db.do_dia(dia_str)
    compactos = [
        {
            "id": c.id,
            "categoria": c.analise.categoria,
            "prioridade": c.analise.prioridade,
            "setor": c.analise.setor,
            "status": c.status,
            "resumo": c.analise.resumo,
        }
        for c in chamados
    ]
    try:
        r = resumir_chamados(compactos)
    except ErroIA as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return ResumoDiario(
        data=dia_str,
        total_chamados=len(chamados),
        resumo=r.resumo,
        destaques=r.destaques,
        pendencias_criticas=sum(1 for c in chamados if c.analise.prioridade == "critica" and c.status != "resolvido"),
    )


@app.get("/metricas", tags=["relatórios"])
def metricas():
    m = db.metricas()
    sem_ia = m["por_origem"].get("faq", 0) + m["por_origem"].get("cache", 0)
    m["chamadas_ia_economizadas"] = sem_ia
    m["percentual_sem_ia"] = round(100 * sem_ia / m["total"], 1) if m["total"] else 0.0
    return m
