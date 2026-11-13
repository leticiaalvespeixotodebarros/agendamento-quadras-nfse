from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol


class ErroEmissao(Exception):
    """Failure to issue an invoice (it is skipped and logged; the batch continues)."""


@dataclass(frozen=True)
class DadosNota:
    agendamento_id: int
    tomador_nome: str
    tomador_cpf: str            # digits only
    tomador_telefone: str
    descricao: str
    valor: float
    data_locacao: date
    competencia: date           # rental date (ISS service-tax competence month)


@dataclass(frozen=True)
class ResultadoEmissao:
    numero: str
    chave: str
    ambiente: str               # simulado | homologacao | producao


class Emissor(Protocol):
    ambiente: str

    def emitir(self, dados: DadosNota) -> ResultadoEmissao: ...
