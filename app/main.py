"""Web app: owner/agent dashboard, WhatsApp simulator and Meta webhook.

Run:  .venv\\Scripts\\python -m uvicorn app.main:app --reload
Dashboard password: ADMIN_PASSWORD variable (user "admin"). Without it, the dashboard is open (local use only).
"""
from __future__ import annotations

import os
import secrets
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates

from . import agente, conversas, db, fechamento, lembrete, regras, relogio, whatsapp
from .fiscal import planilha

BASE = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE / "templates"))
templates.env.filters["brl"] = regras.brl
templates.env.filters["cpf"] = regras.fmt_cpf
templates.env.filters["dataf"] = regras.fmt_data
seguranca = HTTPBasic(auto_error=False)


@asynccontextmanager
async def ciclo(app: FastAPI):
    db.iniciar()
    yield


app = FastAPI(title="Espaço Esportivo Exemplo – Agendamento e NFS-e", lifespan=ciclo)


def login(cred: HTTPBasicCredentials | None = Depends(seguranca)):
    senha = os.environ.get("ADMIN_PASSWORD")
    if not senha:
        return
    ok = cred and secrets.compare_digest(cred.username, "admin") and secrets.compare_digest(cred.password, senha)
    if not ok:
        raise HTTPException(401, "Acesso restrito", headers={"WWW-Authenticate": "Basic"})


def pagina(request: Request, nome: str, **ctx) -> HTMLResponse:
    base = {"cfg": db.config(), "ia": agente.usa_ia(), "wa_real": whatsapp.modo_real(),
            "emissor": os.environ.get("QUADRAS_EMISSOR", "simulado")}
    return templates.TemplateResponse(request, nome, {**base, **ctx})


def voltar(rota: str, msg: str = "") -> RedirectResponse:
    from urllib.parse import quote
    return RedirectResponse(rota + (f"?msg={quote(msg)}" if msg else ""), status_code=303)


# ---------------- dashboard ----------------
@app.get("/", response_class=HTMLResponse, dependencies=[Depends(login)])
def painel(request: Request, msg: str = ""):
    h = relogio.hoje().isoformat()
    with db.conexao() as c:
        n = lambda sql, *a: c.execute(sql, a).fetchone()[0]  # noqa: E731
        resumo = {
            "hoje": n("SELECT COUNT(*) FROM agendamentos WHERE data = ? AND status IN ('agendado','confirmado')", h),
            "futuros": n("SELECT COUNT(*) FROM agendamentos WHERE data > ? AND status = 'agendado'", h),
            "pendentes": len(fechamento._elegiveis(c)),
            "notas": n("SELECT COUNT(*) FROM notas WHERE status = 'emitida'"),
            "erros": n("SELECT COUNT(*) FROM notas WHERE status = 'erro'"),
            "humano": n("SELECT COUNT(*) FROM conversas WHERE modo = 'humano'"),
        }
    return pagina(request, "painel.html", resumo=resumo, msg=msg)


# ---------------- WhatsApp simulator ----------------
@app.get("/simulador", response_class=HTMLResponse, dependencies=[Depends(login)])
def simulador(request: Request):
    return pagina(request, "simulador.html", dono=regras.so_digitos(db.config()["dono_telefone"]))


@app.get("/simulador/mensagens", dependencies=[Depends(login)])
def sim_mensagens(telefone: str):
    return [{"autor": m["autor"], "texto": m["texto"]} for m in conversas.historico(telefone, 200)]


@app.post("/simulador/enviar", dependencies=[Depends(login)])
def sim_enviar(telefone: str = Form(...), texto: str = Form(...)):
    conversas.processar(telefone, texto)
    return {"ok": True}


# ---------------- schedule ----------------
@app.get("/agenda", response_class=HTMLResponse, dependencies=[Depends(login)])
def agenda(request: Request, data: str = "", msg: str = ""):
    d = date.fromisoformat(data) if data else relogio.hoje()
    with db.conexao() as c:
        ags = [dict(r) for r in c.execute(
            "SELECT a.*, q.nome AS quadra FROM agendamentos a JOIN quadras q ON q.id = a.quadra_id "
            "WHERE a.data = ? ORDER BY a.hora_ini, a.quadra_id", (d.isoformat(),))]
    return pagina(request, "agenda.html", d=d, ags=ags, quadras=regras.quadras_ativas(), msg=msg,
                  ant=(d - timedelta(days=1)).isoformat(), prox=(d + timedelta(days=1)).isoformat())


@app.post("/agenda/novo", dependencies=[Depends(login)])
def agenda_novo(data: str = Form(...), quadra_id: int = Form(...), hora: int = Form(...), horas: int = Form(1),
                nome: str = Form(...), cpf: str = Form(...), telefone: str = Form("")):
    try:
        regras.criar_agendamento(telefone=telefone or "0", nome=nome, cpf=cpf, data=date.fromisoformat(data),
                                 hora_ini=hora, horas=horas, quadra_id=quadra_id, origem="painel")
        return voltar(f"/agenda?data={data}", "Reserva criada.")
    except regras.ErroRegra as e:
        return voltar(f"/agenda?data={data}", f"Não foi possível: {e}")


@app.post("/agenda/{ag_id}/cancelar", dependencies=[Depends(login)])
def agenda_cancelar(ag_id: int):
    ag = regras.detalhe_agendamento(ag_id)
    if ag["status"] == "agendado":
        with db.conexao() as c:
            c.execute("UPDATE agendamentos SET status = 'cancelado' WHERE id = ?", (ag_id,))
    return voltar(f"/agenda?data={ag['data']}", "Reserva cancelada.")


# ---------------- settings (prices, discounts, courts, texts) ----------------
@app.get("/config", response_class=HTMLResponse, dependencies=[Depends(login)])
def config_get(request: Request, msg: str = ""):
    with db.conexao() as c:
        dados = {t: [dict(r) for r in c.execute(f"SELECT * FROM {t} ORDER BY id")] for t in ("quadras", "precos", "descontos")}
    return pagina(request, "config.html", msg=msg, dias=regras.DIAS, **dados)


CAMPOS_CONFIG = ["empresa_nome", "endereco", "abertura", "fechamento_hora", "antecedencia_max_dias", "dono_nome",
                 "dono_telefone", "dono_email", "descricao_servico", "politica_cancelamento", "politica_pagamento",
                 "faq_extra", "aviso_lgpd"]


@app.post("/config/salvar", dependencies=[Depends(login)])
async def config_salvar(request: Request):
    f = await request.form()
    novos = {k: str(f[k]).strip() for k in CAMPOS_CONFIG if k in f}
    novos["dono_telefone"] = regras.so_digitos(novos.get("dono_telefone", ""))
    for k in ("abertura", "fechamento_hora", "antecedencia_max_dias"):
        if not novos.get(k, "").isdigit():
            return voltar("/config", f"Valor inválido em {k}.")
    db.salvar_config(novos)
    return voltar("/config", "Configurações salvas.")


@app.post("/config/precos/novo", dependencies=[Depends(login)])
async def preco_novo(request: Request):
    f = await request.form()
    dias = ",".join(sorted(f.getlist("dias")))
    if not dias:
        return voltar("/config", "Marque ao menos um dia da semana.")
    try:
        ini, fim, val = int(f["hora_ini"]), int(f["hora_fim"]), float(str(f["valor_hora"]).replace(",", "."))
    except ValueError:
        return voltar("/config", "Horas e valor devem ser números.")
    if not (0 <= ini < fim <= 24) or val <= 0:
        return voltar("/config", "Faixa de horas ou valor inválido.")
    with db.conexao() as c:
        c.execute("INSERT INTO precos(descricao, dias, hora_ini, hora_fim, valor_hora) VALUES (?,?,?,?,?)",
                  (str(f["descricao"]).strip() or "Preço", dias, ini, fim, val))
    return voltar("/config", "Preço adicionado.")


@app.post("/config/precos/{pid}/excluir", dependencies=[Depends(login)])
def preco_excluir(pid: int):
    with db.conexao() as c:
        c.execute("DELETE FROM precos WHERE id = ?", (pid,))
    return voltar("/config", "Preço removido.")


@app.post("/config/descontos/novo", dependencies=[Depends(login)])
def desconto_novo(nome: str = Form(...), tipo: str = Form(...), valor: str = Form(...),
                  min_horas: int = Form(1), codigo: str = Form("")):
    try:
        v = float(valor.replace(",", "."))
    except ValueError:
        return voltar("/config", "Valor do desconto inválido.")
    if tipo not in ("percentual", "fixo") or v <= 0 or (tipo == "percentual" and v > 100):
        return voltar("/config", "Desconto inválido.")
    with db.conexao() as c:
        c.execute("INSERT INTO descontos(nome, tipo, valor, min_horas, codigo) VALUES (?,?,?,?,?)",
                  (nome.strip(), tipo, v, max(1, min_horas), codigo.strip().upper()))
    return voltar("/config", "Desconto adicionado.")


@app.post("/config/descontos/{did}/alternar", dependencies=[Depends(login)])
def desconto_alternar(did: int):
    with db.conexao() as c:
        c.execute("UPDATE descontos SET ativo = 1 - ativo WHERE id = ?", (did,))
    return voltar("/config")


@app.post("/config/descontos/{did}/excluir", dependencies=[Depends(login)])
def desconto_excluir(did: int):
    with db.conexao() as c:
        c.execute("DELETE FROM descontos WHERE id = ?", (did,))
    return voltar("/config", "Desconto removido.")


@app.post("/config/quadras/nova", dependencies=[Depends(login)])
def quadra_nova(nome: str = Form(...)):
    with db.conexao() as c:
        c.execute("INSERT INTO quadras(nome) VALUES (?)", (nome.strip(),))
    return voltar("/config", "Quadra adicionada.")


@app.post("/config/quadras/{qid}/alternar", dependencies=[Depends(login)])
def quadra_alternar(qid: int):
    with db.conexao() as c:
        c.execute("UPDATE quadras SET ativa = 1 - ativa WHERE id = ?", (qid,))
    return voltar("/config")


# ---------------- closing and invoices ----------------
@app.get("/fechamento", response_class=HTMLResponse, dependencies=[Depends(login)])
def fechamento_get(request: Request, msg: str = ""):
    fid = fechamento.gerar()
    its = fechamento.itens(fid) if fid else []
    return pagina(request, "fechamento.html", fid=fid, its=its, msg=msg, aviso=fechamento.aviso_competencia(its))


@app.post("/fechamento/concluir", dependencies=[Depends(login)])
async def fechamento_concluir(request: Request):
    f = await request.form()
    fid = int(f["fid"])
    excl = {int(x) for x in f.getlist("excluir")}
    res = fechamento.concluir(fid, excl)
    return voltar("/fechamento", res.texto().replace("\n", " "))


@app.post("/fechamento/reemitir", dependencies=[Depends(login)])
def fechamento_reemitir():
    res = fechamento.reemitir_com_erro()
    return voltar("/notas", f"{res.notas_emitidas} nota(s) emitida(s); {len(res.falhas)} falha(s).")


@app.post("/fechamento/lembrete", dependencies=[Depends(login)])
def fechamento_lembrete():
    return voltar("/fechamento", lembrete.enviar())


@app.get("/notas", response_class=HTMLResponse, dependencies=[Depends(login)])
def notas(request: Request, msg: str = ""):
    with db.conexao() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT n.*, a.nome, a.cpf, a.data, a.hora_ini, a.hora_fim, q.nome AS quadra FROM notas n "
            "JOIN agendamentos a ON a.id = n.agendamento_id JOIN quadras q ON q.id = a.quadra_id ORDER BY n.id DESC")]
    return pagina(request, "notas.html", notas=rows, msg=msg)


@app.get("/notas/exportar.xlsx", dependencies=[Depends(login)])
def notas_exportar():
    return Response(planilha.exportar(), headers={"Content-Disposition": 'attachment; filename="locacoes_confirmadas.xlsx"'},
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ---------------- inbox (human agent) ----------------
@app.get("/inbox", response_class=HTMLResponse, dependencies=[Depends(login)])
def inbox(request: Request, tel: str = ""):
    convs = conversas.lista_conversas()
    tel = regras.so_digitos(tel) or (convs[0]["telefone"] if convs else "")
    atual = next((c for c in convs if c["telefone"] == tel), None)
    return pagina(request, "inbox.html", convs=convs, tel=tel, atual=atual, msgs=conversas.historico(tel, 100) if tel else [])


@app.post("/inbox/{tel}/responder", dependencies=[Depends(login)])
def inbox_responder(tel: str, texto: str = Form(...)):
    if texto.strip():
        conversas.passar_para_humano(tel, "Atendente assumiu")
        conversas.responder_humano(tel, texto.strip())
    return voltar(f"/inbox?tel={tel}")


@app.post("/inbox/{tel}/devolver", dependencies=[Depends(login)])
def inbox_devolver(tel: str):
    conversas.devolver_ao_bot(tel)
    return voltar(f"/inbox?tel={tel}")


# ---------------- Meta webhook (WhatsApp Cloud API) ----------------
@app.get("/webhook")
def webhook_verificar(request: Request):
    q = request.query_params
    esperado = os.environ.get("WHATSAPP_VERIFY_TOKEN", "")
    if esperado and q.get("hub.mode") == "subscribe" and q.get("hub.verify_token") == esperado:
        return PlainTextResponse(q.get("hub.challenge", ""))
    raise HTTPException(403)


@app.post("/webhook")
async def webhook_receber(request: Request):
    corpo = await request.body()
    segredo = os.environ.get("WHATSAPP_APP_SECRET")
    if segredo:                                      # Meta signature: stops third parties from injecting messages
        import hashlib
        import hmac
        esperado = "sha256=" + hmac.new(segredo.encode(), corpo, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(esperado, request.headers.get("X-Hub-Signature-256", "")):
            raise HTTPException(403, "Assinatura inválida")
    import json
    payload = json.loads(corpo or b"{}")
    for tel, texto in whatsapp.extrair_mensagens(payload):
        try:
            conversas.processar(tel, texto)
        except Exception:                            # noqa: BLE001 - one error does not drop the other messages
            import traceback
            traceback.print_exc()
    return JSONResponse({"ok": True})   # Meta requires a fast 200, otherwise it resends
