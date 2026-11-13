"""Banco SQLite do MVP: esquema, acesso e dados de exemplo.

Os dados de exemplo (3 quadras, preços e descontos) são FICTÍCIOS, só para a demonstração.
Em uso real, tudo é editado pelo painel (aba Configurações).
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO = Path(os.environ.get("QUADRAS_DB", RAIZ / "dados" / "quadras.db"))

ESQUEMA = """
CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS quadras (
  id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, ativa INTEGER NOT NULL DEFAULT 1);

-- dias: lista de 0 (segunda) a 6 (domingo) separada por vírgula; horas inteiras [hora_ini, hora_fim)
CREATE TABLE IF NOT EXISTS precos (
  id INTEGER PRIMARY KEY AUTOINCREMENT, descricao TEXT NOT NULL, dias TEXT NOT NULL,
  hora_ini INTEGER NOT NULL, hora_fim INTEGER NOT NULL, valor_hora REAL NOT NULL);

-- tipo: percentual | fixo (R$ por hora). codigo vazio = automático quando atingir min_horas
CREATE TABLE IF NOT EXISTS descontos (
  id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, tipo TEXT NOT NULL,
  valor REAL NOT NULL, min_horas INTEGER NOT NULL DEFAULT 1, codigo TEXT NOT NULL DEFAULT '',
  ativo INTEGER NOT NULL DEFAULT 1);

CREATE TABLE IF NOT EXISTS agendamentos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  quadra_id INTEGER NOT NULL REFERENCES quadras(id),
  data TEXT NOT NULL, hora_ini INTEGER NOT NULL, hora_fim INTEGER NOT NULL,
  telefone TEXT NOT NULL, nome TEXT NOT NULL, cpf TEXT NOT NULL,
  valor_bruto REAL NOT NULL, desconto REAL NOT NULL DEFAULT 0, valor REAL NOT NULL,
  desconto_nome TEXT NOT NULL DEFAULT '',
  -- agendado | cancelado | confirmado | nao_realizado
  status TEXT NOT NULL DEFAULT 'agendado',
  origem TEXT NOT NULL DEFAULT 'whatsapp',
  criado_em TEXT NOT NULL, confirmado_em TEXT);
CREATE INDEX IF NOT EXISTS ix_ag_data ON agendamentos(data, quadra_id);

CREATE TABLE IF NOT EXISTS conversas (
  telefone TEXT PRIMARY KEY, modo TEXT NOT NULL DEFAULT 'bot', motivo TEXT NOT NULL DEFAULT '',
  estado TEXT NOT NULL DEFAULT '{}', atualizado_em TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS mensagens (
  id INTEGER PRIMARY KEY AUTOINCREMENT, telefone TEXT NOT NULL,
  autor TEXT NOT NULL,            -- cliente | bot | humano
  texto TEXT NOT NULL, criado_em TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_msg_tel ON mensagens(telefone, id);

CREATE TABLE IF NOT EXISTS fechamentos (
  id INTEGER PRIMARY KEY AUTOINCREMENT, criado_em TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'aberto');            -- aberto | concluido
CREATE TABLE IF NOT EXISTS fechamento_itens (
  fechamento_id INTEGER NOT NULL REFERENCES fechamentos(id), numero INTEGER NOT NULL,
  agendamento_id INTEGER NOT NULL REFERENCES agendamentos(id),
  PRIMARY KEY (fechamento_id, numero));

CREATE TABLE IF NOT EXISTS notas (
  id INTEGER PRIMARY KEY AUTOINCREMENT, agendamento_id INTEGER NOT NULL UNIQUE REFERENCES agendamentos(id),
  numero TEXT, chave TEXT, ambiente TEXT NOT NULL, emitida_em TEXT NOT NULL,
  competencia TEXT NOT NULL, valor REAL NOT NULL,
  status TEXT NOT NULL,           -- emitida | erro
  erro TEXT NOT NULL DEFAULT '');
"""

CONFIG_PADRAO = {
    "empresa_nome": "Espaço Esportivo Exemplo",
    "empresa_razao": "ESPACO ESPORTIVO EXEMPLO LTDA",
    "empresa_cnpj": "00.000.000/0001-00",
    "endereco": "Cidade/UF (endereço completo a preencher)",
    "abertura": "8",                      # hora de abertura
    "fechamento_hora": "23",              # última hora de término
    "antecedencia_max_dias": "30",
    "dono_nome": "Sócio",
    "dono_telefone": "5511900000001",     # telefone do dono (autoriza fechamento por WhatsApp)
    "dono_email": "",
    "descricao_servico": "Locação de quadra poliesportiva",
    "politica_cancelamento": "Cancelamentos com pelo menos 24 horas de antecedência, sem custo.",
    "politica_pagamento": "O pagamento é feito no local, no dia, por cartão, PIX ou dinheiro.",
    "faq_extra": "Temos quadras para vôlei, futevôlei, futsal e outros esportes de quadra.",
    "aviso_lgpd": ("Para emitir a nota fiscal da locação, usamos seu nome e CPF apenas para esse fim, "
                   "conforme a LGPD."),
}


def _agora_iso() -> str:
    from . import relogio
    return relogio.agora().isoformat(timespec="seconds")


@contextmanager
def conexao():
    CAMINHO.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(CAMINHO, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def iniciar(com_exemplos: bool = True) -> None:
    with conexao() as c:
        c.executescript(ESQUEMA)
        for k, v in CONFIG_PADRAO.items():
            c.execute("INSERT OR IGNORE INTO config(chave, valor) VALUES (?, ?)", (k, v))
        if com_exemplos and c.execute("SELECT COUNT(*) FROM quadras").fetchone()[0] == 0:
            _exemplos(c)


def _exemplos(c: sqlite3.Connection) -> None:
    for nome in ("Quadra 1", "Quadra 2", "Quadra 3"):
        c.execute("INSERT INTO quadras(nome) VALUES (?)", (nome,))
    c.executemany("INSERT INTO precos(descricao, dias, hora_ini, hora_fim, valor_hora) VALUES (?,?,?,?,?)", [
        ("Dia útil - manhã/tarde", "0,1,2,3,4", 8, 18, 70.0),
        ("Dia útil - noite", "0,1,2,3,4", 18, 24, 100.0),
        ("Fim de semana", "5,6", 8, 24, 120.0),
    ])
    c.executemany("INSERT INTO descontos(nome, tipo, valor, min_horas, codigo) VALUES (?,?,?,?,?)", [
        ("2 horas ou mais: 10% de desconto", "percentual", 10.0, 2, ""),
        ("Cupom PRIMEIRA: R$ 10 por hora", "fixo", 10.0, 1, "PRIMEIRA"),
    ])


def config() -> dict[str, str]:
    with conexao() as c:
        return {r["chave"]: r["valor"] for r in c.execute("SELECT chave, valor FROM config")}


def salvar_config(valores: dict[str, str]) -> None:
    with conexao() as c:
        for k, v in valores.items():
            c.execute("INSERT INTO config(chave, valor) VALUES (?, ?) "
                      "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor", (k, v))
