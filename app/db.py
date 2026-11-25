import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from . import config
from .schemas import AnaliseIA, Chamado, Evento

SCHEMA = """
CREATE TABLE IF NOT EXISTS chamados (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    criado_em TEXT NOT NULL,
    atualizado_em TEXT NOT NULL,
    morador TEXT NOT NULL,
    apartamento TEXT,
    canal TEXT NOT NULL,
    texto TEXT NOT NULL,
    acao TEXT NOT NULL,
    status TEXT NOT NULL,
    categoria TEXT NOT NULL,
    prioridade TEXT NOT NULL,
    setor TEXT NOT NULL,
    responsavel TEXT,
    regra_seguranca INTEGER NOT NULL DEFAULT 0,
    analise_json TEXT NOT NULL,
    origem TEXT NOT NULL DEFAULT 'ia',
    resolvido_em TEXT
);

CREATE TABLE IF NOT EXISTS eventos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chamado_id INTEGER NOT NULL REFERENCES chamados(id),
    criado_em TEXT NOT NULL,
    tipo TEXT NOT NULL,
    autor TEXT NOT NULL,
    destino TEXT,
    texto TEXT NOT NULL,
    dados_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_eventos_chamado ON eventos (chamado_id, id);

CREATE TABLE IF NOT EXISTS cache_respostas (
    chave TEXT PRIMARY KEY,
    analise_json TEXT NOT NULL,
    criado_em TEXT NOT NULL,
    usos INTEGER NOT NULL DEFAULT 0
);
"""

# Prazo de atendimento por prioridade
PRAZOS = {
    "critica": timedelta(minutes=30),
    "alta": timedelta(hours=4),
    "media": timedelta(hours=24),
    "baixa": timedelta(hours=72),
}


@contextmanager
def conexao():
    Path(config.DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.DATABASE_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def iniciar():
    with conexao() as con:
        con.executescript(SCHEMA)
        # Bancos criados por versões anteriores do projeto
        colunas = {r["name"] for r in con.execute("PRAGMA table_info(chamados)")}
        if "origem" not in colunas:
            con.execute("ALTER TABLE chamados ADD COLUMN origem TEXT NOT NULL DEFAULT 'ia'")
        if "resolvido_em" not in colunas:
            con.execute("ALTER TABLE chamados ADD COLUMN resolvido_em TEXT")


def agora() -> datetime:
    return datetime.now().replace(microsecond=0)


def _para_chamado(row: sqlite3.Row) -> Chamado:
    criado = datetime.fromisoformat(row["criado_em"])
    prazo = criado + PRAZOS[row["prioridade"]]
    return Chamado(
        id=row["id"],
        criado_em=criado,
        atualizado_em=datetime.fromisoformat(row["atualizado_em"]),
        morador=row["morador"],
        apartamento=row["apartamento"],
        canal=row["canal"],
        texto=row["texto"],
        acao=row["acao"],
        status=row["status"],
        analise=AnaliseIA.model_validate_json(row["analise_json"]),
        regra_seguranca_aplicada=bool(row["regra_seguranca"]),
        origem=row["origem"],
        setor=row["setor"],
        prioridade=row["prioridade"],
        responsavel=row["responsavel"],
        resolvido_em=datetime.fromisoformat(row["resolvido_em"]) if row["resolvido_em"] else None,
        prazo_em=prazo,
        atrasado=row["status"] != "resolvido" and agora() > prazo,
    )


def _para_evento(row: sqlite3.Row) -> Evento:
    return Evento(
        id=row["id"],
        chamado_id=row["chamado_id"],
        criado_em=datetime.fromisoformat(row["criado_em"]),
        tipo=row["tipo"],
        autor=row["autor"],
        destino=row["destino"],
        texto=row["texto"],
        dados=json.loads(row["dados_json"] or "{}"),
    )


def criar_chamado(*, morador, apartamento, canal, texto, acao, status, analise: AnaliseIA, regra_seguranca: bool,
                  origem: str = "ia") -> Chamado:
    ts = agora().isoformat()
    with conexao() as con:
        cur = con.execute(
            """INSERT INTO chamados (criado_em, atualizado_em, morador, apartamento, canal, texto, acao, status,
                                     categoria, prioridade, setor, regra_seguranca, analise_json, origem, resolvido_em)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (ts, ts, morador, apartamento, canal, texto, acao, status,
             analise.categoria, analise.prioridade, analise.setor, int(regra_seguranca), analise.model_dump_json(),
             origem, ts if status == "resolvido" else None),
        )
        row = con.execute("SELECT * FROM chamados WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _para_chamado(row)


def registrar_evento(chamado_id: int, tipo: str, autor: str, texto: str, destino: str | None = None,
                     dados: dict | None = None) -> Evento:
    with conexao() as con:
        cur = con.execute(
            "INSERT INTO eventos (chamado_id, criado_em, tipo, autor, destino, texto, dados_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (chamado_id, agora().isoformat(), tipo, autor, destino, texto, json.dumps(dados or {}, ensure_ascii=False)),
        )
        con.execute("UPDATE chamados SET atualizado_em = ? WHERE id = ?", (agora().isoformat(), chamado_id))
        row = con.execute("SELECT * FROM eventos WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _para_evento(row)


def listar_eventos(chamado_id: int) -> list[Evento]:
    with conexao() as con:
        rows = con.execute("SELECT * FROM eventos WHERE chamado_id = ? ORDER BY id", (chamado_id,)).fetchall()
    return [_para_evento(r) for r in rows]


def buscar(chamado_id: int) -> Chamado | None:
    with conexao() as con:
        row = con.execute("SELECT * FROM chamados WHERE id = ?", (chamado_id,)).fetchone()
    return _para_chamado(row) if row else None


def listar(status: str | None = None, prioridade: str | None = None, setor: str | None = None,
           limite: int = 100) -> list[Chamado]:
    sql, args = "SELECT * FROM chamados WHERE 1=1", []
    for coluna, valor in (("status", status), ("prioridade", prioridade), ("setor", setor)):
        if valor:
            sql += f" AND {coluna} = ?"
            args.append(valor)
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(limite)
    with conexao() as con:
        return [_para_chamado(r) for r in con.execute(sql, args).fetchall()]


def atualizar_status(chamado_id: int, status: str, responsavel: str | None) -> Chamado | None:
    ts = agora().isoformat()
    with conexao() as con:
        con.execute(
            """UPDATE chamados SET status = ?, responsavel = COALESCE(?, responsavel), atualizado_em = ?,
                      resolvido_em = CASE WHEN ? = 'resolvido' THEN ? ELSE NULL END
               WHERE id = ?""",
            (status, responsavel, ts, status, ts, chamado_id),
        )
    return buscar(chamado_id)


def atualizar_campo(chamado_id: int, coluna: str, valor: str) -> Chamado | None:
    assert coluna in ("setor", "prioridade")
    with conexao() as con:
        con.execute(f"UPDATE chamados SET {coluna} = ?, atualizado_em = ? WHERE id = ?",
                    (valor, agora().isoformat(), chamado_id))
    return buscar(chamado_id)


def criticos_parados(minutos: int) -> list[Chamado]:
    limite = (agora() - timedelta(minutes=minutos)).isoformat()
    with conexao() as con:
        rows = con.execute(
            "SELECT * FROM chamados WHERE prioridade = 'critica' AND status = 'aberto' AND criado_em <= ? ORDER BY id",
            (limite,),
        ).fetchall()
    return [_para_chamado(r) for r in rows]


def do_dia(dia: str) -> list[Chamado]:
    with conexao() as con:
        rows = con.execute("SELECT * FROM chamados WHERE substr(criado_em, 1, 10) = ? ORDER BY id", (dia,)).fetchall()
    return [_para_chamado(r) for r in rows]


def buscar_cache(chave: str, dias: int) -> AnaliseIA | None:
    if dias <= 0:
        return None
    limite = (agora() - timedelta(days=dias)).isoformat()
    with conexao() as con:
        row = con.execute(
            "SELECT analise_json FROM cache_respostas WHERE chave = ? AND criado_em >= ?", (chave, limite)
        ).fetchone()
        if not row:
            return None
        con.execute("UPDATE cache_respostas SET usos = usos + 1 WHERE chave = ?", (chave,))
    return AnaliseIA.model_validate_json(row["analise_json"])


def salvar_cache(chave: str, analise: AnaliseIA) -> None:
    with conexao() as con:
        con.execute(
            """INSERT INTO cache_respostas (chave, analise_json, criado_em) VALUES (?, ?, ?)
               ON CONFLICT(chave) DO UPDATE SET analise_json = excluded.analise_json, criado_em = excluded.criado_em""",
            (chave, analise.model_dump_json(), agora().isoformat()),
        )


def caixas() -> dict:
    """O que cada setor tem para atender agora."""
    pendentes = [c for c in listar(limite=10_000) if c.status != "resolvido"]
    resultado = {}
    for setor in ("portaria", "zeladoria", "administracao", "sindico"):
        do_setor = [c for c in pendentes if c.setor == setor]
        resultado[setor] = {
            "pendentes": len(do_setor),
            "abertos": sum(c.status == "aberto" for c in do_setor),
            "em_andamento": sum(c.status == "em_andamento" for c in do_setor),
            "atrasados": sum(c.atrasado for c in do_setor),
            "criticos": sum(c.prioridade == "critica" for c in do_setor),
        }
    return resultado


def metricas() -> dict:
    with conexao() as con:
        total = con.execute("SELECT COUNT(*) FROM chamados").fetchone()[0]

        def agrupar(coluna: str) -> dict:
            return {r[0]: r[1] for r in con.execute(f"SELECT {coluna}, COUNT(*) FROM chamados GROUP BY {coluna}")}

        # Tempo médio entre abertura e resolução, só dos chamados resolvidos pela equipe
        minutos = con.execute(
            """SELECT AVG((julianday(resolvido_em) - julianday(criado_em)) * 1440) FROM chamados
               WHERE resolvido_em IS NOT NULL AND acao != 'responder_automaticamente'"""
        ).fetchone()[0]

        return {
            "total": total,
            "por_categoria": agrupar("categoria"),
            "por_prioridade": agrupar("prioridade"),
            "por_setor": agrupar("setor"),
            "por_status": agrupar("status"),
            "por_acao": agrupar("acao"),
            "por_origem": agrupar("origem"),
            "atrasados": sum(c.atrasado for c in listar(limite=10_000)),
            "tempo_medio_resolucao_min": round(minutos, 1) if minutos is not None else None,
        }
