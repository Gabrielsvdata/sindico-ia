import json

import pytest

from app import ai, config
from app.schemas import AnaliseIA


from conftest import enviar


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
    monkeypatch.setattr("app.servico.analisar_mensagem", lambda msg, trechos=None: errada)
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


class RespostaFalsa:
    def __init__(self, status, corpo):
        self.status_code = status
        self.text = json.dumps(corpo)
        self._corpo = corpo

    def json(self):
        return self._corpo


def test_repete_quando_gemini_sobrecarregado(monkeypatch):
    """503 na 1ª chamada: a API espera e tenta de novo, sem devolver erro ao n8n."""
    ok = {"candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}]}
    respostas = iter([RespostaFalsa(503, {"error": "high demand"}), RespostaFalsa(200, ok)])
    monkeypatch.setattr(config, "GEMINI_API_KEY", "teste")
    monkeypatch.setattr(ai.time, "sleep", lambda s: None)
    monkeypatch.setattr(ai.httpx, "post", lambda *a, **k: next(respostas))
    assert ai._chamar_gemini("sys", [{"text": "oi"}]) == '{"ok": true}'


def test_usa_modelo_reserva(monkeypatch):
    ok = {"candidates": [{"content": {"parts": [{"text": "{}"}]}}]}
    usados = []

    def post(url, **k):
        usados.append(url.split("/models/")[1].split(":")[0])
        return RespostaFalsa(200, ok) if "reserva" in url else RespostaFalsa(503, {})

    monkeypatch.setattr(config, "GEMINI_API_KEY", "teste")
    monkeypatch.setattr(config, "GEMINI_MODEL", "principal")
    monkeypatch.setattr(config, "GEMINI_MODELOS_RESERVA", ["reserva"])
    monkeypatch.setattr(ai.time, "sleep", lambda s: None)
    monkeypatch.setattr(ai.httpx, "post", post)
    ai._chamar_gemini("sys", [{"text": "oi"}])
    assert usados == ["principal"] * config.AI_TENTATIVAS_SOBRECARGA + ["reserva"]


def test_erro_definitivo_nao_repete(monkeypatch):
    chamadas = []
    monkeypatch.setattr(config, "GEMINI_API_KEY", "teste")
    monkeypatch.setattr(ai.httpx, "post", lambda *a, **k: chamadas.append(1) or RespostaFalsa(400, {"error": "key"}))
    with pytest.raises(ai.ErroIA, match="400"):
        ai._chamar_gemini("sys", [{"text": "oi"}])
    assert len(chamadas) == 1


def test_timeout_passa_para_modelo_reserva(monkeypatch):
    ok = {"candidates": [{"content": {"parts": [{"text": "{}"}]}}]}

    def post(url, **k):
        if "reserva" in url:
            return RespostaFalsa(200, ok)
        raise ai.httpx.ReadTimeout("timed out")

    monkeypatch.setattr(config, "GEMINI_API_KEY", "teste")
    monkeypatch.setattr(config, "GEMINI_MODEL", "principal")
    monkeypatch.setattr(config, "GEMINI_MODELOS_RESERVA", ["reserva"])
    monkeypatch.setattr(ai.time, "sleep", lambda s: None)
    monkeypatch.setattr(ai.httpx, "post", post)
    assert ai._chamar_gemini("sys", [{"text": "oi"}]) == "{}"


# ---------------------------------------------------------------- FAQ e cache (respostas sem IA)

def proibir_ia(monkeypatch):
    def falhar(msg, trechos=None):
        raise AssertionError("A IA não deveria ter sido chamada")
    monkeypatch.setattr("app.servico.analisar_mensagem", falhar)


def test_faq_responde_sem_chamar_ia(client, monkeypatch):
    proibir_ia(monkeypatch)
    r = enviar(client, "Que horas a piscina abre?")
    assert r["origem"] == "faq"
    assert r["acao"] == "responder_automaticamente"
    assert "terça a domingo" in r["resposta_morador"]


def test_reclamacao_nao_cai_no_faq(client):
    r = enviar(client, "Meu boleto veio errado, onde resolvo isso?")
    assert r["origem"] == "ia"


def test_emergencia_nunca_usa_atalho(client):
    # Fala de piscina e horário, mas tem fumaça: precisa ir para a IA e virar crítica
    r = enviar(client, "Está saindo fumaça da casa de máquinas da piscina, que horas o zelador chega?")
    assert r["origem"] == "ia"
    assert r["prioridade"] == "critica"


def test_cache_reaproveita_resposta_da_ia(client, monkeypatch):
    chamadas = []
    resposta = AnaliseIA(
        categoria="duvida", prioridade="baixa", setor="administracao", sentimento="neutro",
        resumo="Dúvida sobre visitas", resposta_morador="Visitantes precisam ser autorizados pelo morador.",
        respondido_pelo_regimento=True, fontes=["visitantes"], confianca=0.9,
    )
    monkeypatch.setattr("app.servico.analisar_mensagem", lambda msg, trechos=None: chamadas.append(1) or resposta)

    primeira = enviar(client, "Meu amigo vem hoje, como ele entra no prédio?")
    segunda = enviar(client, "meu amigo vem HOJE como ele entra no predio")

    assert (primeira["origem"], segunda["origem"]) == ("ia", "cache")
    assert len(chamadas) == 1
    m = client.get("/metricas").json()
    assert m["chamadas_ia_economizadas"] == 1
    assert m["percentual_sem_ia"] == 50.0


def test_chamado_nao_vai_para_cache(client, monkeypatch):
    """Problemas (ex.: vazamento) são específicos de cada morador: nunca reaproveitar."""
    enviar(client, "Tem água vazando do teto da garagem")
    r = enviar(client, "Tem água vazando do teto da garagem")
    assert r["origem"] == "ia"


@pytest.mark.parametrize("texto", [
    "O vizinho fez festa até 3h, como pode isso?",
    "meu vizinho reformando às 7h da manhã de domingo, pode isso?",
    "a piscina está suja de novo",
    "a academia está com a esteira quebrada",
    "Chegou encomenda pra mim?",
])
def test_reclamacoes_e_pedidos_vao_para_ia(texto):
    from app.faq import buscar_faq
    assert buscar_faq(texto) is None


@pytest.mark.parametrize("texto,esperado", [
    ("Que horas abre a piscina?", "piscina_horario"),
    ("vou me mudar sabado, precisa agendar?", "mudanca"),
    ("Posso furar a parede no domingo?", "obra_horario"),
    ("Quanto custa o salão de festas?", "salao_festas"),
    ("onde tiro segunda via do boleto?", "boleto"),
    ("qual dia passa a coleta de reciclável?", "reciclavel"),
])
def test_perguntas_frequentes_reconhecidas(texto, esperado):
    from app.faq import buscar_faq
    assert buscar_faq(texto)["id"] == esperado


def test_painel_e_servido(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307) and r.headers["location"] == "/painel/"
    pagina = client.get("/painel/")
    assert pagina.status_code == 200 and "Síndico IA" in pagina.text
    assert client.get("/painel/app.js").status_code == 200


def test_limite_diario_de_ia(client, monkeypatch):
    monkeypatch.setattr(config, "AI_PROVIDER", "gemini")
    monkeypatch.setattr(config, "AI_LIMITE_DIARIO", 1)
    monkeypatch.setattr("app.servico.analisar_mensagem", lambda msg, trechos=None: ai._analisar_mock(msg, trechos or []))
    assert client.post("/mensagens", json={"texto": "Tem água vazando na garagem"}).status_code == 200
    r = client.post("/mensagens", json={"texto": "O portão da garagem quebrou"})
    assert r.status_code == 429 and "limite" in r.json()["detail"]
    # Perguntas do FAQ não gastam IA e continuam funcionando
    assert client.post("/mensagens", json={"texto": "Que horas abre a piscina?"}).status_code == 200
    assert client.get("/health").json()["uso_ia_hoje"] == 1
