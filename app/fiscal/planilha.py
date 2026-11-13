"""Exporta as locações confirmadas numa planilha de emissão em lote (colunas padrão).

É a ponte para a emissão REAL enquanto o emissor automático não está ligado: o responsável pela emissão
rodará o emissor com este arquivo. Endereço do tomador fica em branco (pessoa física não exige no Nacional).
"""
from __future__ import annotations

from datetime import date
from io import BytesIO

import openpyxl

from .. import db, regras

COLUNAS = ["Origem", "ID da venda", "Data da venda", "Tomador (nome)", "CPF/CNPJ", "E-mail", "Telefone",
           "Logradouro", "Número", "Complemento", "Bairro", "CEP", "Cidade", "UF", "Produto",
           "Descrição do serviço (NF)", "Valor pago pelo cliente (R$)", "Coparticipantes (R$)", "VALOR DA NF (R$)",
           "Observações (NF)", "Conferência interna (não vai na NF)", "Competência (NF)", "Emitir? (SIM/NÃO)"]


def exportar(ids: list[int] | None = None) -> bytes:
    cfg = db.config()
    with db.conexao() as c:
        q = ("SELECT a.*, qd.nome AS quadra FROM agendamentos a JOIN quadras qd ON qd.id = a.quadra_id "
             "WHERE a.status = 'confirmado' ")
        params: list = []
        if ids:
            q += f"AND a.id IN ({','.join('?' * len(ids))}) "
            params = list(ids)
        linhas = c.execute(q + "ORDER BY a.data, a.hora_ini", params).fetchall()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Notas Fiscais"
    ws.append([f"{cfg['empresa_razao']} – CNPJ {cfg['empresa_cnpj']} – Locações confirmadas para emissão de NFS-e"])
    ws.append([])
    ws.append(COLUNAS)
    for r in linhas:
        d = date.fromisoformat(r["data"])
        ws.append(["Agendador", f"AG-{r['id']:06d}", d.strftime("%d/%m/%Y"), r["nome"], regras.fmt_cpf(r["cpf"]), "",
                   r["telefone"], "", "", "", "", "", "", "", r["quadra"], cfg["descricao_servico"],
                   r["valor"], 0, r["valor"], "", f"{r['hora_ini']:02d}h–{r['hora_fim']:02d}h; {r['desconto_nome']}".strip("; "),
                   d.strftime("%d/%m/%Y"), "SIM"])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
