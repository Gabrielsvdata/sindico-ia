import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent))

from app import config  # noqa: E402


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
