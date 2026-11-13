import os
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.pop("ANTHROPIC_API_KEY", None)        # testes sempre usam o roteiro (sem IA, sem custo)
os.environ.pop("WHATSAPP_TOKEN", None)
os.environ.pop("ADMIN_PASSWORD", None)

from app import db, relogio  # noqa: E402

CLIENTE = "5511999990001"
CPF_OK = "529.982.247-25"      # CPF de teste válido (dígitos verificadores corretos)


@pytest.fixture(autouse=True)
def banco(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "CAMINHO", tmp_path / "teste.db")
    relogio.fixar(datetime(2026, 11, 16, 10, 0))      # segunda-feira
    db.iniciar()
    yield
    relogio.fixar(None)
