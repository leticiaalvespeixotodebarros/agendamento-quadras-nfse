"""Relógio central (fuso de Brasília). Os testes trocam por um horário fixo."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

_FIXO: datetime | None = None
BRASILIA = timezone(timedelta(hours=-3))


def agora() -> datetime:
    return _FIXO if _FIXO else datetime.now(BRASILIA).replace(tzinfo=None)


def fixar(dt: datetime | None) -> None:
    global _FIXO
    _FIXO = dt


def hoje():
    return agora().date()
