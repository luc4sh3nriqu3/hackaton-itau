import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    monkeypatch.setenv("TRIAGEM_API_KEYS", "chave-teste")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    from fastapi.testclient import TestClient

    from triagem import api, armazenamento, config

    monkeypatch.setattr(config, "ARQUIVO_ENV", tmp_path / ".env")  # ignora o .env real
    api.armazenamento.cache_clear()
    monkeypatch.setattr(api, "armazenamento", lambda: _db)
    _db = armazenamento.Armazenamento(str(tmp_path / "teste.db"))
    c = TestClient(api.app)
    c.headers["X-API-Key"] = "chave-teste"
    return c
