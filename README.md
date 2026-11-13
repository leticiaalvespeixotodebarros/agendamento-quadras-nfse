# Agendamento de quadras por WhatsApp + emissão de NFS-e

Protótipo (MVP) para locadoras de quadras esportivas: o cliente agenda conversando no WhatsApp, o sistema já coleta
os dados exigidos para a nota fiscal de serviço (nome e CPF), e o dono confirma periodicamente o que realmente aconteceu.
Só depois dessa confirmação as notas são emitidas.

> **Projeto de demonstração.** Todos os dados (empresa, preços, nomes, CPFs, telefones) são fictícios. A emissão fiscal é
> simulada e não tem valor fiscal.

## O problema

Em negócios de locação por hora, o cliente combina tudo no WhatsApp e ninguém registra o CPF de quem alugou. No fim do mês a
contabilidade não consegue emitir as notas, porque falta o dado do tomador.

## A solução

```
Cliente ─ WhatsApp ─► Webhook (FastAPI) ─► Agente (IA com ferramentas) ─► Regras (agenda, preço, CPF)
                                                    │                          │
                    Painel do dono/atendente ◄──────┴──────── SQLite ◄─────────┘
                                                    │
                 Fechamento semanal (lista numerada) ─► Emissor fiscal (interface plugável)
```

- **Conversa no WhatsApp** (Claude com *tool use*): consulta horários, calcula preço e descontos, coleta nome e CPF (validado
  pelo dígito verificador) e cria a reserva. A IA **não** calcula preço nem decide disponibilidade: ela chama funções determinísticas.
- **Plano B sem IA:** roteiro guiado por menu, usado quando não há chave da API e nos testes.
- **Painel web:** agenda, preços/descontos/quadras/textos editáveis sem programador, fechamento, notas e caixa de atendimento.
- **Atendimento humano no mesmo número:** o cliente pede uma pessoa, o bot silencia, o atendente responde pelo painel e devolve.
- **Fechamento:** lista numerada das locações realizadas; o dono responde `OK` ou `OK menos 3 e 7` (por WhatsApp ou painel).
  Emissão em lote que **não para** quando uma nota falha: ela é pulada, registrada e pode ser retentada.
- **Lembrete semanal por e-mail** ao dono quando há locações a confirmar.
- **Módulo fiscal desacoplado** (`Emissor`): hoje simulado + exportação de planilha em lote; o emissor real entra sem mexer no resto.

## Como rodar

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m app.demo                      # dados fictícios da última semana
.venv\Scripts\python -m uvicorn app.main:app          # http://localhost:8000
.venv\Scripts\python -m pytest -q                     # 17 testes
```

Roteiro de demonstração: **Simulador WhatsApp** (agendar como cliente) → **Configurações** (mudar preço/desconto e ver o efeito)
→ **Atendimento** (assumir uma conversa) → **Fechamento** (confirmar e emitir) → **Notas**.

Variáveis opcionais em [.env.example](.env.example): `ANTHROPIC_API_KEY` (IA), `ADMIN_PASSWORD` (painel),
`WHATSAPP_*` (Cloud API da Meta), `SMTP_*` (lembrete por e-mail).

## Estrutura

| Arquivo | Papel |
|---|---|
| `app/regras.py` | CPF, disponibilidade, preço, desconto, reserva (determinístico) |
| `app/agente.py`, `app/ferramentas.py` | agente Claude + ferramentas; roteiro sem IA |
| `app/conversas.py` | histórico, modo bot/humano, fluxo do dono |
| `app/fechamento.py` | lista numerada, leitura da resposta, emissão em lote |
| `app/fiscal/` | interface `Emissor`, emissor simulado, exportação de planilha |
| `app/whatsapp.py`, `app/main.py` | canal WhatsApp (simulador / Cloud API) e painel web |
| `tests/` | 17 testes: regras, conversa, fechamento, lote com falha, painel, webhook |

## Limites conhecidos

- Integração real com a Cloud API da Meta e o assistente com IA estão implementados, mas **não foram testados contra os serviços reais**
  (os testes cobrem o roteiro e todas as ferramentas que a IA usa).
- Emissão fiscal real (Emissor Nacional de NFS-e, certificado A1) não está incluída.
- Sem multiusuário, pagamentos online, mensalistas ou cadastro de pessoa jurídica.

## Stack

Python · FastAPI · SQLite · Jinja2 · Anthropic API (tool use) · WhatsApp Cloud API · pytest

## Licença

Todos os direitos reservados ([LICENSE](LICENSE)). O código está publicado apenas para visualização e avaliação; não pode ser copiado, usado ou vendido sem autorização por escrito da autora.
