"""RAG: a IA só responde dúvidas com base no FAQ, e só pode citar o que recebeu."""
import pytest

from app import prompts
from app.rag import buscar
from app.schemas import AnaliseIA
from conftest import enviar


@pytest.mark.parametrize("pergunta,esperado", [
    ("A piscina funciona segunda-feira?", "piscina_horario"),
    ("meu amigo vai vir hoje, como faço pra ele entrar?", "visitantes"),
    ("quanto pago se atrasar o condomínio?", "boleto"),
    ("que dia recolhem o reciclável?", "reciclavel"),
    ("o eletricista vem amanhã", "prestador_servico"),
    ("tem limite de velocidade na garagem?", "lavar_carro"),
    ("posso fazer churrasco no sábado?", "churrasqueira"),
])
def test_busca_encontra_a_entrada_certa_entre_as_primeiras(pergunta, esperado):
    assert esperado in [t.id for t in buscar(pergunta)]


@pytest.mark.parametrize("pergunta", ["tem wifi na área comum?", "o vizinho está com som alto"])
def test_busca_nao_inventa_contexto_para_assunto_fora_da_base(pergunta):
    assert buscar(pergunta) == []


def test_prompt_leva_so_as_entradas_recuperadas_e_nao_o_regimento_inteiro():
    trechos = buscar("A piscina funciona segunda-feira?")
    p = prompts.montar_system_prompt(trechos)
    assert "[piscina_horario]" in p
    assert "[mudanca]" not in p and "[boleto]" not in p
    assert "Regimento Interno — Condomínio" not in p
    assert "nenhuma entrada da base" in prompts.montar_system_prompt([])


def analise(**extra):
    base = dict(categoria="duvida", prioridade="baixa", setor="administracao", sentimento="neutro",
                resumo="x", resposta_morador="resposta", respondido_pelo_regimento=True, confianca=0.95)
    return AnaliseIA(**{**base, **extra})


def test_ia_que_cita_fonte_que_nao_recebeu_nao_encerra_o_chamado(client, monkeypatch):
    # Pergunta sobre piscina, mas a IA "cita" a regra de mudança, que não estava no contexto
    monkeypatch.setattr("app.servico.analisar_mensagem", lambda msg, trechos=None: analise(fontes=["mudanca"]))
    r = enviar(client, "Criança de 10 anos pode nadar sem os pais na piscina?")
    assert r["acao"] == "abrir_chamado" and r["status"] == "aberto"
    assert r["analise"]["fontes"] == [] and r["analise"]["respondido_pelo_regimento"] is False
    ev = client.get(f"/chamados/{r['id']}/eventos").json()[1]["dados"]
    assert ev["fontes_descartadas"] == ["mudanca"]
    assert "piscina_horario" in [b["id"] for b in ev["base_consultada"]]


def test_ia_que_responde_sem_citar_fonte_vira_chamado(client, monkeypatch):
    monkeypatch.setattr("app.servico.analisar_mensagem", lambda msg, trechos=None: analise(fontes=[]))
    r = enviar(client, "Criança de 10 anos pode nadar sem os pais na piscina?")
    assert r["acao"] == "abrir_chamado"


def test_citacao_mostrada_vem_do_texto_oficial_do_faq(client, monkeypatch):
    monkeypatch.setattr("app.servico.analisar_mensagem",
                        lambda msg, trechos=None: analise(fontes=["piscina_horario"], trecho_regimento="texto inventado"))
    r = enviar(client, "Criança de 10 anos pode nadar sem os pais na piscina?")
    assert r["acao"] == "responder_automaticamente"
    assert r["analise"]["trecho_regimento"].startswith("Piscina: aberta de terça a domingo")


def test_fluxo_rag_no_modo_mock(client):
    r = enviar(client, "meu amigo vai vir hoje, como faço pra ele entrar?")
    assert r["origem"] == "ia" and r["acao"] == "responder_automaticamente"
    assert r["analise"]["fontes"] == ["visitantes"]
    assert "autorização" in r["resposta_morador"]


def test_endpoint_de_busca_na_base(client):
    r = client.get("/base-conhecimento/buscar", params={"q": "a piscina abre segunda?"}).json()
    assert r[0]["id"] == "piscina_horario" and r[0]["score"] > 0
