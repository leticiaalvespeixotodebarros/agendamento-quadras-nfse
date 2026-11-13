"""Tax module. The rest of the system only knows the `Emissor` interface; swapping the issuer affects nothing else.

MVP: `EmissorSimulado` (no tax value) and a spreadsheet export for a batch invoice issuer (`planilha.exportar`).
Production: an issuer that calls Brazil's national NFS-e system (Sefin Nacional).
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
