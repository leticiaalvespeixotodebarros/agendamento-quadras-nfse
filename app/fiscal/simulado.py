"""Emissor SIMULADO para a demonstração. NÃO gera documento fiscal: numeração e chave são marcadas como
simulação e nunca se parecem com uma NFS-e real."""
from __future__ import annotations

from .. import db
from .base import DadosNota, ErroEmissao, ResultadoEmissao


class EmissorSimulado:
    ambiente = "simulado"

    def emitir(self, dados: DadosNota) -> ResultadoEmissao:
        if dados.valor <= 0:
            raise ErroEmissao("Valor da nota deve ser maior que zero.")
        with db.conexao() as c:
            n = c.execute("SELECT COUNT(*) FROM notas WHERE ambiente = 'simulado' AND status = 'emitida'"
                          ).fetchone()[0] + 1
        return ResultadoEmissao(numero=f"SIMULACAO-{n:05d}", chave=f"SIMULACAO-SEM-VALOR-FISCAL-{dados.agendamento_id:08d}",
                                ambiente=self.ambiente)
