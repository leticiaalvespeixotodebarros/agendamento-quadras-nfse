"""Conversation storage, bot/human mode, and routing of each incoming message."""
from __future__ import annotations

import json

from . import db, regras, relogio


def _agora() -> str:
    return relogio.agora().isoformat(timespec="seconds")


def registrar(telefone: str, autor: str, texto: str) -> None:
    tel = regras.so_digitos(telefone)
    with db.conexao() as c:
        c.execute("INSERT INTO mensagens(telefone, autor, texto, criado_em) VALUES (?,?,?,?)",
                  (tel, autor, texto, _agora()))
        c.execute("INSERT INTO conversas(telefone, atualizado_em) VALUES (?,?) "
                  "ON CONFLICT(telefone) DO UPDATE SET atualizado_em = excluded.atualizado_em", (tel, _agora()))


def historico(telefone: str, limite: int = 30) -> list[dict]:
    with db.conexao() as c:
        rows = c.execute("SELECT autor, texto, criado_em FROM mensagens WHERE telefone = ? ORDER BY id DESC LIMIT ?",
                         (regras.so_digitos(telefone), limite)).fetchall()
    return [dict(r) for r in reversed(rows)]


def modo(telefone: str) -> str:
    with db.conexao() as c:
        r = c.execute("SELECT modo FROM conversas WHERE telefone = ?", (regras.so_digitos(telefone),)).fetchone()
    return r["modo"] if r else "bot"


def passar_para_humano(telefone: str, motivo: str) -> None:
    tel = regras.so_digitos(telefone)
    with db.conexao() as c:
        c.execute("INSERT INTO conversas(telefone, modo, motivo, atualizado_em) VALUES (?, 'humano', ?, ?) "
                  "ON CONFLICT(telefone) DO UPDATE SET modo = 'humano', motivo = excluded.motivo, "
                  "atualizado_em = excluded.atualizado_em", (tel, motivo, _agora()))


def devolver_ao_bot(telefone: str) -> None:
    with db.conexao() as c:
        c.execute("UPDATE conversas SET modo = 'bot', motivo = '', estado = '{}' WHERE telefone = ?",
                  (regras.so_digitos(telefone),))


def estado(telefone: str) -> dict:
    with db.conexao() as c:
        r = c.execute("SELECT estado FROM conversas WHERE telefone = ?", (regras.so_digitos(telefone),)).fetchone()
    return json.loads(r["estado"]) if r else {}


def salvar_estado(telefone: str, est: dict) -> None:
    with db.conexao() as c:
        c.execute("UPDATE conversas SET estado = ? WHERE telefone = ?", (json.dumps(est), regras.so_digitos(telefone)))


def lista_conversas() -> list[dict]:
    with db.conexao() as c:
        return [dict(r) for r in c.execute(
            "SELECT cv.telefone, cv.modo, cv.motivo, cv.atualizado_em, "
            "(SELECT texto FROM mensagens m WHERE m.telefone = cv.telefone ORDER BY id DESC LIMIT 1) AS ultima "
            "FROM conversas cv ORDER BY (cv.modo = 'humano') DESC, cv.atualizado_em DESC")]


def responder_humano(telefone: str, texto: str) -> None:
    """Reply from the human agent via the dashboard; it goes out through the same business number."""
    from . import whatsapp
    registrar(telefone, "humano", texto)
    whatsapp.enviar(telefone, texto)


# ---------- routing ----------
def processar(telefone: str, texto: str) -> list[str]:
    """Handle an incoming message and return the replies already sent (and stored)."""
    from . import agente, whatsapp
    tel = regras.so_digitos(telefone)
    texto = (texto or "").strip()
    if not texto:
        return []
    registrar(tel, "cliente", texto)

    respostas: list[str] = []
    cfg = db.config()
    if tel == regras.so_digitos(cfg["dono_telefone"]):
        r = _fluxo_dono(tel, texto)
        if r is not None:
            respostas = [r]
    if not respostas and modo(tel) == "humano":
        return []                                   # a human took over: the bot stays silent
    if not respostas:
        respostas = agente.responder(tel, texto)
    for r in respostas:
        registrar(tel, "bot", r)
        whatsapp.enviar(tel, r)
    return respostas


def _fluxo_dono(tel: str, texto: str) -> str | None:
    """Owner commands: request the closing and answer the list. Returns None if it is not about the closing."""
    from . import fechamento
    t = texto.lower()
    est = estado(tel)
    if any(p in t for p in ("fechamento", "fechar semana", "fechar a semana")):
        fid = fechamento.gerar()
        if fid is None:
            return "Não há locações pendentes de confirmação. ✅"
        salvar_estado(tel, {**est, "fechamento": fid})
        return fechamento.texto_lista(fid)
    fid = est.get("fechamento")
    if fid:
        its = fechamento.itens(fid)
        if not its:
            salvar_estado(tel, {k: v for k, v in est.items() if k != "fechamento"})
            return None
        try:
            excl = fechamento.interpretar_resposta(texto, [i["numero"] for i in its])
        except fechamento.ErroResposta as e:
            if any(w in t for w in ("ok", "concordo", "confirmo", "menos", "exceto")):
                return str(e)
            return None                              # ordinary chat; goes on to the agent
        res = fechamento.concluir(fid, excl)
        salvar_estado(tel, {k: v for k, v in estado(tel).items() if k != "fechamento"})
        return res.texto()
    return None
