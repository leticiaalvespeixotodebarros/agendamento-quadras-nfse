from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol


class ErroEmissao(Exception):
    """Falha ao emitir uma nota (a nota é pulada e registrada; o lote continua)."""


@dataclass(frozen=True)
class DadosNota:
    agendamento_id: int
    tomador_nome: str
    tomador_cpf: str            # só dígitos
    tomador_telefone: str
    descricao: str
    valor: float
    data_locacao: date
    competencia: date           # data da locação (competência do ISS)


@dataclass(frozen=True)
class ResultadoEmissao:
    numero: str
    chave: str
    ambiente: str               # simulado | homologacao | producao


class Emissor(Protocol):
    ambiente: str

    def emitir(self, dados: DadosNota) -> ResultadoEmissao: ...
