"""WhatsApp channel.

* Simulator (default): `enviar` sends nothing; the message is already stored and shown in the dashboard.
* Real (Meta WhatsApp Cloud API): turn on by setting WHATSAPP_TOKEN and WHATSAPP_PHONE_ID.
  WARNING: the real part was NOT tested against Meta (it needs an approved account/number).
"""
from __future__ import annotations

import os

import httpx

GRAPH = "https://graph.facebook.com/v21.0"


def modo_real() -> bool:
    return bool(os.environ.get("WHATSAPP_TOKEN") and os.environ.get("WHATSAPP_PHONE_ID"))


def enviar(telefone: str, texto: str) -> None:
    if not modo_real():
        return
    r = httpx.post(f"{GRAPH}/{os.environ['WHATSAPP_PHONE_ID']}/messages", timeout=20,
                   headers={"Authorization": f"Bearer {os.environ['WHATSAPP_TOKEN']}"},
                   json={"messaging_product": "whatsapp", "to": telefone, "type": "text", "text": {"body": texto}})
    r.raise_for_status()


def extrair_mensagens(payload: dict) -> list[tuple[str, str]]:
    """(phone, text) of the TEXT messages in the Meta webhook. Other types (audio, image) are ignored."""
    out = []
    for entry in payload.get("entry", []):
        for ch in entry.get("changes", []):
            for m in ch.get("value", {}).get("messages", []):
                if m.get("type") == "text":
                    out.append((m["from"], m["text"]["body"]))
    return out
