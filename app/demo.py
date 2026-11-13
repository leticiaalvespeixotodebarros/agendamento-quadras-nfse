"""Populates the database with FICTITIOUS rentals from the last week, so the demo can show the closing.

  python -m app.demo          (resets the demo database and recreates the data)

Names and CPFs are invented (CPFs are generated with valid check digits only). Do not use with real data.
"""
from __future__ import annotations

import random
from datetime import timedelta

from . import db, regras, relogio


def _cpf_ficticio(semente: int) -> str:
    r = random.Random(semente)
    n = [r.randint(0, 9) for _ in range(9)]
    for i in (9, 10):
        s = sum(d * (i + 1 - j) for j, d in enumerate(n))
        n.append((s * 10 % 11) % 10)
    return "".join(map(str, n))


NOMES = ["Carlos Eduardo Ribeiro", "Fernanda Alves Moreira", "Rafael Duarte Nunes", "Juliana Costa Barreto",
         "Marcos Vinícius Teixeira", "Patrícia Gomes Lopes", "Thiago Henrique Martins", "Luciana Prado Siqueira"]


def popular() -> int:
    if db.CAMINHO.exists():
        db.CAMINHO.unlink()
    db.iniciar()
    hoje = relogio.hoje()
    n = 0
    with db.conexao() as c:
        quadras = [r[0] for r in c.execute("SELECT id FROM quadras ORDER BY id")]
        for i, nome in enumerate(NOMES):
            dia = hoje - timedelta(days=1 + i % 6)
            hora = (18, 19, 20, 21, 9, 10)[i % 6]
            horas = 1 + (i % 2)
            o = regras.orcar(dia, hora, horas)
            c.execute(
                "INSERT INTO agendamentos(quadra_id, data, hora_ini, hora_fim, telefone, nome, cpf, valor_bruto, desconto, "
                "valor, desconto_nome, origem, criado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (quadras[(i // 6 + i) % len(quadras)], dia.isoformat(), hora, hora + horas, f"55119{9000000 + i:07d}", nome,
                 _cpf_ficticio(i), o.bruto, o.desconto, o.total, o.desconto_nome, "whatsapp",
                 (relogio.agora() - timedelta(days=8)).isoformat(timespec="seconds")))
            n += 1
        # two future bookings so the schedule is not empty
        for k, nome in enumerate(("Beatriz Andrade Lemos", "Gustavo Farias Neto")):
            dia = hoje + timedelta(days=2 + k)
            o = regras.orcar(dia, 19, 2)
            c.execute(
                "INSERT INTO agendamentos(quadra_id, data, hora_ini, hora_fim, telefone, nome, cpf, valor_bruto, desconto, "
                "valor, desconto_nome, origem, criado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (quadras[k], dia.isoformat(), 19, 21, f"55119{9100000 + k:07d}", nome, _cpf_ficticio(100 + k),
                 o.bruto, o.desconto, o.total, o.desconto_nome, "whatsapp", relogio.agora().isoformat(timespec="seconds")))
            n += 1
    return n


if __name__ == "__main__":
    print(f"{popular()} reservas fictícias criadas em {db.CAMINHO}")
