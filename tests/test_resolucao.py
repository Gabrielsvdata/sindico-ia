"""Histórico da conversa e ações da equipe para resolver chamados."""
from datetime import timedelta

from conftest import enviar


def tipos(client, chamado_id):
    return [e["tipo"] for e in client.get(f"/chamados/{chamado_id}/eventos").json()]


def test_historico_de_um_chamado_mostra_a_conversa_inteira(client):
    c = enviar(client, "Tem água vazando do teto da garagem perto da vaga 12")
    eventos = client.get(f"/chamados/{c['id']}/eventos").json()

    assert [e["tipo"] for e in eventos] == ["mensagem_morador", "analise", "resposta_morador", "alerta_setor"]
    assert eventos[0]["texto"].startswith("Tem água vazando")
    assert eventos[0]["autor"] == "Ana (apto 302B)"
    assert eventos[1]["dados"]["origem"] == "ia" and eventos[1]["dados"]["modelo"] == "mock"
    assert eventos[3]["destino"] == "Zeladoria" and "Chamado #" in eventos[3]["texto"]


def test_emergencia_avisa_portaria_zelador_e_sindico(client):
    c = enviar(client, "Socorro, cheiro de gás no corredor")
    alertas = [e["destino"] for e in client.get(f"/chamados/{c['id']}/eventos").json() if e["tipo"] == "alerta_setor"]
    assert alertas == ["Portaria", "Zelador de plantão", "Síndico"]


def test_faq_fica_registrado_como_sem_ia_e_encerrado(client):
    c = enviar(client, "Que horas abre a piscina?")
    eventos = client.get(f"/chamados/{c['id']}/eventos").json()
    assert eventos[1]["dados"]["origem"] == "faq" and eventos[1]["dados"]["modelo"] is None
    assert eventos[-1]["tipo"] == "status" and eventos[-1]["dados"]["para"] == "resolvido"
    assert "alerta_setor" not in [e["tipo"] for e in eventos]


def test_ciclo_completo_de_resolucao(client):
    c = enviar(client, "Tem água vazando do teto da garagem")
    cid = c["id"]

    r = client.patch(f"/chamados/{cid}", json={"status": "em_andamento", "responsavel": "Zelador João"})
    assert r.json()["status"] == "em_andamento" and r.json()["responsavel"] == "Zelador João"

    client.post(f"/chamados/{cid}/interacoes", json={"tipo": "nota_interna", "autor": "Zelador João",
                                                    "texto": "Cano do 2º andar rompido, chamei o encanador."})
    client.post(f"/chamados/{cid}/interacoes", json={"tipo": "resposta_morador", "autor": "Zelador João",
                                                    "texto": "Já estamos no local, a água foi fechada."})

    sem_nota = client.patch(f"/chamados/{cid}", json={"status": "resolvido", "responsavel": "Zelador João"})
    assert sem_nota.status_code == 409

    r = client.patch(f"/chamados/{cid}", json={"status": "resolvido", "responsavel": "Zelador João",
                                              "nota": "Cano trocado e garagem seca."})
    assert r.json()["status"] == "resolvido" and r.json()["resolvido_em"]

    assert tipos(client, cid)[-4:] == ["status", "nota_interna", "resposta_morador", "status"]
    m = client.get("/metricas").json()
    assert m["tempo_medio_resolucao_min"] is not None


def test_morador_responde_e_reabre_chamado_resolvido(client):
    cid = enviar(client, "Tem água vazando do teto da garagem")["id"]
    client.patch(f"/chamados/{cid}", json={"status": "resolvido", "responsavel": "João", "nota": "Consertado"})
    r = client.post(f"/chamados/{cid}/interacoes", json={"tipo": "mensagem_morador", "autor": "Ana",
                                                        "texto": "Voltou a vazar!"})
    assert r.json()["status"] == "aberto" and r.json()["resolvido_em"] is None


def test_encaminhar_muda_setor_e_avisa_o_novo_setor(client):
    cid = enviar(client, "Tem água vazando do teto da garagem")["id"]
    r = client.post(f"/chamados/{cid}/encaminhar", json={"setor": "sindico", "autor": "Zelador",
                                                        "motivo": "Precisa contratar empresa"})
    assert r.json()["setor"] == "sindico"
    assert r.json()["analise"]["setor"] == "zeladoria"  # o que a IA sugeriu continua registrado
    ultimos = client.get(f"/chamados/{cid}/eventos").json()[-2:]
    assert ultimos[0]["tipo"] == "encaminhamento" and ultimos[1]["destino"] == "Síndico"
    assert client.get("/chamados?setor=sindico").json()[0]["id"] == cid
    assert client.post(f"/chamados/{cid}/encaminhar", json={"setor": "sindico", "autor": "x"}).status_code == 409


def test_mudar_prioridade_recalcula_prazo(client):
    c = enviar(client, "Lâmpada do hall queimada")
    antes = c["prazo_em"]
    r = client.post(f"/chamados/{c['id']}/prioridade", json={"prioridade": "alta", "autor": "Síndico"})
    assert r.json()["prioridade"] == "alta" and r.json()["prazo_em"] < antes


def test_chamado_fica_atrasado_depois_do_prazo(client, monkeypatch):
    from app import db
    cid = enviar(client, "Socorro, cheiro de gás no corredor")["id"]
    assert client.get(f"/chamados/{cid}").json()["atrasado"] is False

    real = db.agora
    monkeypatch.setattr(db, "agora", lambda: real() + timedelta(minutes=31))
    assert client.get(f"/chamados/{cid}").json()["atrasado"] is True
    caixas = client.get("/caixas").json()
    assert caixas["portaria"]["atrasados"] == 1 and caixas["portaria"]["criticos"] == 1


def test_acoes_em_chamado_inexistente_dao_404(client):
    assert client.get("/chamados/999/eventos").status_code == 404
    assert client.patch("/chamados/999", json={"status": "em_andamento"}).status_code == 404
    assert client.post("/chamados/999/encaminhar", json={"setor": "sindico", "autor": "x"}).status_code == 404
