# WhatsApp court booking + Brazilian NFS-e invoicing

[Leia em português](README.pt-BR.md)

A prototype (MVP) for sports-court rental businesses. Customers book a court by chatting on WhatsApp, the system collects
the data that Brazilian service invoices require (name and CPF) during the booking, and the owner periodically confirms
which rentals really happened. Invoices are issued only after that confirmation.

> **Demo project.** All data (business, prices, names, CPFs, phone numbers) is fictitious. Invoice issuing is simulated
> and has no tax value.

## The problem

In pay-per-hour rental businesses, customers arrange everything on WhatsApp and nobody records who rented the court.
At the end of the month the accountant cannot issue the invoices, because the customer's tax ID is missing.

## The solution

```
Customer ─ WhatsApp ─► Webhook (FastAPI) ─► Agent (AI with tools) ─► Rules (schedule, price, CPF)
                                                   │                          │
                  Owner/agent dashboard ◄──────────┴──────── SQLite ◄─────────┘
                                                   │
                 Weekly closing (numbered list) ─► Invoice issuer (pluggable interface)
```

- **WhatsApp conversation** (Claude with *tool use*): checks availability, calculates prices and discounts, collects the
  customer's name and CPF (validated with the check digits), and creates the booking. The AI **never** calculates prices or
  decides availability: it calls deterministic functions.
- **No-AI fallback:** a menu-guided script, used when there is no API key and in the tests.
- **Web dashboard:** schedule, prices/discounts/courts/texts editable without a developer, closing, invoices and an inbox.
- **Human takeover on the same number:** the customer asks for a person, the bot goes silent, the agent replies from the
  dashboard and hands the chat back.
- **Closing:** a numbered list of the rentals that already happened. The owner answers `OK` or `OK menos 3 e 7`
  ("OK except 3 and 7"), by WhatsApp or in the dashboard. Batch issuing **does not stop** when one invoice fails: it is
  skipped, logged and can be retried.
- **Weekly e-mail reminder** to the owner when there are rentals to confirm.
- **Decoupled tax module** (`Emissor` interface): today a simulated issuer plus a spreadsheet export; the real issuer plugs
  in without touching the rest.

## Brazilian terms used in this project

| Term | Meaning |
|---|---|
| **CPF** | Brazilian individual taxpayer ID (11 digits, the last two are check digits). |
| **CNPJ** | Brazilian company taxpayer ID. |
| **NFS-e** | *Nota Fiscal de Serviço eletrônica*: the electronic invoice for services. Brazilian businesses must issue one for each service sold. |
| **Emissor Nacional** | The national NFS-e issuing system (replacing city-by-city systems). Not included here; the real issuer would call it. |
| **Tomador** | The customer on the invoice (the one who "takes" the service). |
| **Competência** | The month the service was provided; it defines which month the service tax (ISS) belongs to. |
| **LGPD** | Brazil's data-protection law (similar to the EU's GDPR). The bot warns the customer before asking for the CPF. |
| **WhatsApp Cloud API** | Meta's official API for business WhatsApp numbers. |

## How to run

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m app.demo                      # fictitious data for the last week
.venv\Scripts\python -m uvicorn app.main:app          # http://localhost:8000
.venv\Scripts\python -m pytest -q                     # 17 tests
```

Demo script: **Simulador WhatsApp** (book as a customer) → **Configurações** (change a price or discount and see the
effect) → **Atendimento** (take over a chat) → **Fechamento** (confirm and issue) → **Notas**.
The interface is in Portuguese because the product is meant for a Brazilian business.

Optional variables in [.env.example](.env.example): `ANTHROPIC_API_KEY` (AI), `ADMIN_PASSWORD` (dashboard),
`WHATSAPP_*` (Meta Cloud API), `SMTP_*` (e-mail reminder).

## Structure

Module names are in Portuguese, the domain language of the project (`regras` = rules, `fechamento` = closing,
`conversas` = conversations, `agente` = agent).

| File | Role |
|---|---|
| `app/regras.py` | CPF, availability, price, discount, booking (deterministic) |
| `app/agente.py`, `app/ferramentas.py` | Claude agent + tools; no-AI script |
| `app/conversas.py` | history, bot/human mode, owner flow |
| `app/fechamento.py` | numbered list, reply parsing, batch issuing |
| `app/fiscal/` | `Emissor` interface, simulated issuer, spreadsheet export |
| `app/whatsapp.py`, `app/main.py` | WhatsApp channel (simulator / Cloud API) and web dashboard |
| `tests/` | 17 tests: rules, chat, closing, batch with a failure, dashboard, webhook |

## Known limitations

- The real Meta Cloud API integration and the AI assistant are implemented but **not tested against the real services**
  (the tests cover the menu script and every tool the AI uses).
- Real invoice issuing (national NFS-e system, company digital certificate) is not included.
- No multi-user support, online payments, recurring bookings or company (CNPJ) customers.

## Stack

Python · FastAPI · SQLite · Jinja2 · Anthropic API (tool use) · WhatsApp Cloud API · pytest

## License

All rights reserved ([LICENSE](LICENSE)). The code is published for viewing and evaluation only; it may not be copied,
used or sold without the author's written permission.
