"""Canal WhatsApp.

* Simulador (padrão): `enviar` não envia nada; a mensagem já fica gravada e aparece no painel.
* Real (WhatsApp Cloud API da Meta): ligue definindo WHATSAPP_TOKEN e WHATSAPP_PHONE_ID.
  ATENÇÃO: o trecho real NÃO foi testado contra a Meta (depende de conta/número aprovados).
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
    """(telefone, texto) das mensagens de TEXTO do webhook da Meta. Outros tipos (áudio, imagem) são ignorados."""
    out = []
    for entry in payload.get("entry", []):
        for ch in entry.get("changes", []):
            for m in ch.get("value", {}).get("messages", []):
                if m.get("type") == "text":
                    out.append((m["from"], m["text"]["body"]))
    return out
