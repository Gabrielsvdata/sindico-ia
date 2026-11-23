import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from . import config
from .schemas import AnaliseIA, Chamado

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
    analise_json TEXT NOT NULL
);
"""


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


def agora() -> datetime:
    return datetime.now().replace(microsecond=0)


def _para_chamado(row: sqlite3.Row) -> Chamado:
    return Chamado(
        id=row["id"],
        criado_em=datetime.fromisoformat(row["criado_em"]),
        morador=row["morador"],
        apartamento=row["apartamento"],
        canal=row["canal"],
        texto=row["texto"],
        acao=row["acao"],
        status=row["status"],
        analise=AnaliseIA.model_validate_json(row["analise_json"]),
        regra_seguranca_aplicada=bool(row["regra_seguranca"]),
    )


def criar_chamado(*, morador, apartamento, canal, texto, acao, status, analise: AnaliseIA, regra_seguranca: bool) -> Chamado:
    ts = agora().isoformat()
    with conexao() as con:
        cur = con.execute(
            """INSERT INTO chamados (criado_em, atualizado_em, morador, apartamento, canal, texto, acao, status,
                                     categoria, prioridade, setor, regra_seguranca, analise_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (ts, ts, morador, apartamento, canal, texto, acao, status,
             analise.categoria, analise.prioridade, analise.setor, int(regra_seguranca), analise.model_dump_json()),
        )
        row = con.execute("SELECT * FROM chamados WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _para_chamado(row)


def buscar(chamado_id: int) -> Chamado | None:
    with conexao() as con:
        row = con.execute("SELECT * FROM chamados WHERE id = ?", (chamado_id,)).fetchone()
    return _para_chamado(row) if row else None


def listar(status: str | None = None, prioridade: str | None = None, limite: int = 100) -> list[Chamado]:
    sql, args = "SELECT * FROM chamados WHERE 1=1", []
    if status:
        sql += " AND status = ?"
        args.append(status)
    if prioridade:
        sql += " AND prioridade = ?"
        args.append(prioridade)
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(limite)
    with conexao() as con:
        return [_para_chamado(r) for r in con.execute(sql, args).fetchall()]


def atualizar_status(chamado_id: int, status: str, responsavel: str | None) -> Chamado | None:
    with conexao() as con:
        con.execute(
            "UPDATE chamados SET status = ?, responsavel = COALESCE(?, responsavel), atualizado_em = ? WHERE id = ?",
            (status, responsavel, agora().isoformat(), chamado_id),
        )
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


def metricas() -> dict:
    with conexao() as con:
        total = con.execute("SELECT COUNT(*) FROM chamados").fetchone()[0]

        def agrupar(coluna: str) -> dict:
            return {r[0]: r[1] for r in con.execute(f"SELECT {coluna}, COUNT(*) FROM chamados GROUP BY {coluna}")}

        return {
            "total": total,
            "por_categoria": agrupar("categoria"),
            "por_prioridade": agrupar("prioridade"),
            "por_setor": agrupar("setor"),
            "por_status": agrupar("status"),
            "por_acao": agrupar("acao"),
        }
