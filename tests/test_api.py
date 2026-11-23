import json

import pytest
from fastapi.testclient import TestClient

from app import ai, config
from app.schemas import AnaliseIA


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "AI_PROVIDER", "mock")
    monkeypatch.setattr(config, "DATABASE_PATH", str(tmp_path / "teste.db"))
    from app.main import app

    with TestClient(app) as c:
        yield c


def enviar(client, texto, **extra):
    r = client.post("/mensagens", json={"texto": texto, "morador": "Ana", "apartamento": "302B", **extra})
    assert r.status_code == 200, r.text
    return r.json()


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_emergencia_vira_critica(client):
    r = enviar(client, "Socorro, tem cheiro de gás forte no corredor do 3º andar")
    assert r["prioridade"] == "critica"
    assert r["acao"] == "emergencia"
    assert r["status"] == "aberto"
    assert "193" in r["resposta_morador"]


def test_duvida_respondida_pelo_regimento(client):
    r = enviar(client, "Posso fazer mudança no domingo?")
    assert r["acao"] == "responder_automaticamente"
    assert r["status"] == "resolvido"
    assert r["analise"]["respondido_pelo_regimento"] is True


def test_manutencao_abre_chamado(client):
    r = enviar(client, "Tem água vazando do teto da garagem perto da vaga 12")
    assert r["acao"] == "abrir_chamado"
    assert r["setor"] == "zeladoria"
    assert "Chamado #" in r["notificacao_setor"]


def test_mensagem_vazia_e_rejeitada(client):
    assert client.post("/mensagens", json={"texto": ""}).status_code == 422


def test_guarda_corpo_corrige_ia(client, monkeypatch):
    """Mesmo que a IA classifique errado, palavras de emergência forçam prioridade crítica."""
    errada = AnaliseIA(
        categoria="outros", prioridade="baixa", setor="administracao", sentimento="neutro",
        resumo="x", resposta_morador="ok", respondido_pelo_regimento=False, confianca=0.9,
    )
    monkeypatch.setattr("app.servico.analisar_mensagem", lambda msg: errada)
    r = enviar(client, "Meu vizinho ficou preso no elevador")
    assert r["prioridade"] == "critica"
    assert r["regra_seguranca_aplicada"] is True


def test_fluxo_status_e_escalonamento(client):
    r = enviar(client, "Está saindo fumaça do quadro de luz")
    assert [c["id"] for c in client.get("/chamados/criticos-parados?minutos=0").json()] == [r["id"]]

    client.patch(f"/chamados/{r['id']}", json={"status": "em_andamento", "responsavel": "Zelador João"})
    assert client.get("/chamados/criticos-parados?minutos=0").json() == []


def test_resumo_e_metricas(client):
    enviar(client, "Chegou encomenda pra mim?")
    enviar(client, "Barulho de festa até 2h da manhã de novo!!")
    resumo = client.get("/resumo-diario").json()
    assert resumo["total_chamados"] == 2
    m = client.get("/metricas").json()
    assert m["total"] == 2
    assert m["por_categoria"]["barulho"] == 1


def test_retry_quando_ia_devolve_json_invalido(monkeypatch):
    """A IA errou o formato na 1ª vez; a API pede de novo e aceita a 2ª resposta."""
    valido = {
        "categoria": "duvida", "prioridade": "baixa", "setor": "administracao", "sentimento": "neutro",
        "resumo": "Dúvida sobre a piscina", "resposta_morador": "Abre às 8h.",
        "respondido_pelo_regimento": True, "trecho_regimento": "Piscina...", "transcricao_anexo": None,
        "confianca": 0.95,
    }
    respostas = iter(['{"categoria": "inventada"}', json.dumps(valido)])
    monkeypatch.setattr(ai, "_chamar_gemini", lambda system, partes: next(respostas))
    resultado = ai._gerar_validado("sys", [{"text": "oi"}], AnaliseIA)
    assert resultado.categoria == "duvida"
