"""Lembrete semanal por e-mail ao dono: "há N locações para confirmar".

Sem SMTP configurado, o e-mail é gravado em dados/outbox/ (a demonstração mostra o texto).
Agendar toda semana:  python -m app.lembrete   (Agendador de Tarefas do Windows).
Variáveis: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM, PAINEL_URL.
"""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage

from . import db, fechamento, regras, relogio


def montar() -> tuple[str, str] | None:
    fid = fechamento.gerar()
    if fid is None:
        return None
    its = fechamento.itens(fid)
    if not its:
        return None
    cfg = db.config()
    url = os.environ.get("PAINEL_URL", "http://localhost:8000") + "/fechamento"
    total = regras.brl(sum(i["valor"] for i in its))
    corpo = (f"Olá, {cfg['dono_nome']}!\n\nHá {len(its)} locação(ões) da {cfg['empresa_nome']} aguardando a sua confirmação "
             f"({total} no total). As notas fiscais só são emitidas depois que você confirmar.\n\n"
             f"Confirme pelo painel: {url}\n"
             f"Ou, pelo WhatsApp do local, envie a palavra: fechamento\n")
    return f"Confirmar locações da semana ({len(its)} pendentes)", corpo


def enviar() -> str:
    m = montar()
    if m is None:
        return "Nada pendente: nenhum e-mail enviado."
    assunto, corpo = m
    cfg = db.config()
    destino = cfg["dono_email"]
    if os.environ.get("SMTP_HOST") and destino:
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = assunto, os.environ.get("SMTP_FROM", os.environ["SMTP_USER"]), destino
        msg.set_content(corpo)
        with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", "587"))) as s:
            s.starttls()
            s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            s.send_message(msg)
        return f"E-mail enviado para {destino}."
    pasta = db.CAMINHO.parent / "outbox"
    pasta.mkdir(parents=True, exist_ok=True)
    arq = pasta / f"lembrete_{relogio.agora():%Y%m%d_%H%M%S}.txt"
    arq.write_text(f"Para: {destino or '(e-mail do dono não cadastrado)'}\nAssunto: {assunto}\n\n{corpo}", encoding="utf-8")
    return f"SMTP/e-mail não configurado: lembrete gravado em {arq}"


if __name__ == "__main__":
    db.iniciar(com_exemplos=False)
    print(enviar())
