"""Módulo fiscal. O resto do sistema só conhece a interface `Emissor`; trocar o emissor não afeta mais nada.

MVP: `EmissorSimulado` (sem valor fiscal) e `exportar_planilha` (gera a planilha no formato do emissor
um emissor de NFS-e em lote). Produção: um emissor que chame o Emissor Nacional (Sefin Nacional).
"""
import os

from .base import DadosNota, Emissor, ErroEmissao, ResultadoEmissao
from .simulado import EmissorSimulado


def emissor_padrao() -> Emissor:
    modo = os.environ.get("QUADRAS_EMISSOR", "simulado")
    if modo == "simulado":
        return EmissorSimulado()
    raise RuntimeError(f"Emissor “{modo}” ainda não implementado (previsto: nacional).")


__all__ = ["DadosNota", "Emissor", "ErroEmissao", "ResultadoEmissao", "EmissorSimulado", "emissor_padrao"]
