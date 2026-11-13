"""Deterministic business rules: CPF, availability, price, discount and booking creation.

The conversation agent NEVER calculates prices or decides availability: it calls these functions.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from . import db, relogio

DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


class ErroRegra(Exception):
    """Business-rule error with a message that can be shown to the customer."""


# ---------- CPF / phone / formatting ----------
def so_digitos(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def cpf_valido(cpf: str) -> bool:
    n = so_digitos(cpf)
    if len(n) != 11 or n == n[0] * 11:
        return False
    for i in (9, 10):
        soma = sum(int(n[j]) * (i + 1 - j) for j in range(i))
        dig = (soma * 10 % 11) % 10
        if dig != int(n[i]):
            return False
    return True


def fmt_cpf(cpf: str) -> str:
    n = so_digitos(cpf)
    return f"{n[:3]}.{n[3:6]}.{n[6:9]}-{n[9:]}"


def brl(v: float) -> str:
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_data(d: str | date) -> str:
    d = date.fromisoformat(d) if isinstance(d, str) else d
    return f"{d.strftime('%d/%m/%Y')} ({DIAS[d.weekday()]})"


def interpretar_data(txt: str) -> date:
    """Accepts YYYY-MM-DD or DD/MM[/YYYY]."""
    t = txt.strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t):
            return date.fromisoformat(t)
        m = re.fullmatch(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", t)
        if m:
            h = relogio.hoje()
            ano = int(m.group(3)) if m.group(3) else h.year
            ano += 2000 if ano < 100 else 0
            d = date(ano, int(m.group(2)), int(m.group(1)))
            if not m.group(3) and d < h:
                d = date(ano + 1, d.month, d.day)
            return d
    except ValueError:
        pass
    raise ErroRegra(f"Não entendi a data “{txt}”. Use o formato DD/MM (ex.: 25/11).")


# ---------- Courts and availability ----------
def quadras_ativas() -> list[dict]:
    with db.conexao() as c:
        return [dict(r) for r in c.execute("SELECT * FROM quadras WHERE ativa = 1 ORDER BY id")]


def _limites(cfg: dict) -> tuple[int, int]:
    return int(cfg["abertura"]), int(cfg["fechamento_hora"])


def horas_livres(data: date) -> dict[int, list[int]]:
    """{quadra_id: [free start hours]} — already excludes past hours of today."""
    cfg = db.config()
    ab, fe = _limites(cfg)
    agora = relogio.agora()
    with db.conexao() as c:
        ocupadas: dict[int, set[int]] = {}
        for r in c.execute("SELECT quadra_id, hora_ini, hora_fim FROM agendamentos "
                           "WHERE data = ? AND status IN ('agendado','confirmado')", (data.isoformat(),)):
            ocupadas.setdefault(r["quadra_id"], set()).update(range(r["hora_ini"], r["hora_fim"]))
    livres = {}
    for q in quadras_ativas():
        h = [x for x in range(ab, fe + 1) if x not in ocupadas.get(q["id"], set())]
        if data == agora.date():
            h = [x for x in h if x > agora.hour]
        livres[q["id"]] = h
    return livres


def _faixas(horas: list[int]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for h in horas:
        if out and out[-1][1] == h:
            out[-1] = (out[-1][0], h + 1)
        else:
            out.append((h, h + 1))
    return out


def resumo_disponibilidade(data: date) -> list[dict]:
    nomes = {q["id"]: q["nome"] for q in quadras_ativas()}
    return [{"quadra_id": qid, "quadra": nomes[qid],
             "faixas_livres": [f"{a:02d}h às {b:02d}h" for a, b in _faixas(h)]}
            for qid, h in horas_livres(data).items()]


# ---------- Price and discount ----------
@dataclass
class Orcamento:
    horas: int
    bruto: float
    desconto: float = 0.0
    desconto_nome: str = ""
    avisos: list[str] = field(default_factory=list)

    @property
    def total(self) -> float:
        return round(self.bruto - self.desconto, 2)


def preco_hora(data: date, hora: int) -> float:
    with db.conexao() as c:
        for r in c.execute("SELECT * FROM precos ORDER BY id"):
            dias = [int(x) for x in r["dias"].split(",") if x != ""]
            if data.weekday() in dias and r["hora_ini"] <= hora < r["hora_fim"]:
                return float(r["valor_hora"])
    raise ErroRegra("Não há preço cadastrado para esse horário.")


def orcar(data: date, hora_ini: int, horas: int, cupom: str = "") -> Orcamento:
    if horas < 1:
        raise ErroRegra("A locação mínima é de 1 hora.")
    bruto = sum(preco_hora(data, h) for h in range(hora_ini, hora_ini + horas))
    cupom = (cupom or "").strip().upper()
    melhor, melhor_nome, avisos = 0.0, "", []
    with db.conexao() as c:
        for d in c.execute("SELECT * FROM descontos WHERE ativo = 1 ORDER BY id"):
            if horas < d["min_horas"]:
                continue
            if d["codigo"] and d["codigo"].upper() != cupom:
                continue
            v = bruto * d["valor"] / 100 if d["tipo"] == "percentual" else d["valor"] * horas
            if v > melhor:
                melhor, melhor_nome = round(min(v, bruto), 2), d["nome"]
        if cupom and not any(d["codigo"].upper() == cupom for d in
                             c.execute("SELECT codigo FROM descontos WHERE ativo = 1")):
            avisos.append(f"O cupom “{cupom}” não existe ou não está ativo.")
    return Orcamento(horas, round(bruto, 2), melhor, melhor_nome, avisos)


# ---------- Bookings ----------
def criar_agendamento(*, telefone: str, nome: str, cpf: str, data: date, hora_ini: int, horas: int,
                      quadra_id: int | None = None, cupom: str = "", origem: str = "whatsapp") -> dict:
    nome = " ".join((nome or "").split())
    if len(nome.split()) < 2:
        raise ErroRegra("Preciso do nome completo (nome e sobrenome) para a nota fiscal.")
    if not cpf_valido(cpf):
        raise ErroRegra("Esse CPF não parece válido. Pode conferir os números?")
    cfg = db.config()
    ab, fe = _limites(cfg)
    if data < relogio.hoje():
        raise ErroRegra("Essa data já passou.")
    if data > relogio.hoje() + timedelta(days=int(cfg["antecedencia_max_dias"])):
        raise ErroRegra(f"Agendamos com até {cfg['antecedencia_max_dias']} dias de antecedência.")
    if hora_ini < ab or hora_ini + horas - 1 > fe:
        raise ErroRegra(f"Funcionamos das {ab:02d}h às {fe + 1:02d}h.")
    if data == relogio.hoje() and hora_ini <= relogio.agora().hour:
        raise ErroRegra("Esse horário já passou.")
    livres = horas_livres(data)
    necessarias = set(range(hora_ini, hora_ini + horas))
    candidatas = [quadra_id] if quadra_id else list(livres)
    escolhida = next((q for q in candidatas if q in livres and necessarias <= set(livres[q])), None)
    if escolhida is None:
        raise ErroRegra("Esse horário não está mais disponível.")
    o = orcar(data, hora_ini, horas, cupom)
    with db.conexao() as c:
        # re-check inside the transaction (prevents two simultaneous bookings for the same slot)
        c.execute("BEGIN IMMEDIATE") if not c.in_transaction else None
        conflito = c.execute(
            "SELECT 1 FROM agendamentos WHERE quadra_id = ? AND data = ? AND status IN ('agendado','confirmado') "
            "AND hora_ini < ? AND hora_fim > ?", (escolhida, data.isoformat(), hora_ini + horas, hora_ini)).fetchone()
        if conflito:
            raise ErroRegra("Esse horário acabou de ser reservado por outra pessoa.")
        cur = c.execute(
            "INSERT INTO agendamentos(quadra_id, data, hora_ini, hora_fim, telefone, nome, cpf, valor_bruto, "
            "desconto, valor, desconto_nome, origem, criado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (escolhida, data.isoformat(), hora_ini, hora_ini + horas, so_digitos(telefone), nome, so_digitos(cpf),
             o.bruto, o.desconto, o.total, o.desconto_nome, origem, relogio.agora().isoformat(timespec="seconds")))
        ag_id = cur.lastrowid
    return detalhe_agendamento(ag_id)


def detalhe_agendamento(ag_id: int) -> dict:
    with db.conexao() as c:
        r = c.execute("SELECT a.*, q.nome AS quadra FROM agendamentos a JOIN quadras q ON q.id = a.quadra_id "
                      "WHERE a.id = ?", (ag_id,)).fetchone()
    if not r:
        raise ErroRegra("Agendamento não encontrado.")
    return dict(r)


def agendamentos_do_cliente(telefone: str) -> list[dict]:
    with db.conexao() as c:
        return [dict(r) for r in c.execute(
            "SELECT a.*, q.nome AS quadra FROM agendamentos a JOIN quadras q ON q.id = a.quadra_id "
            "WHERE a.telefone = ? AND a.status = 'agendado' AND a.data >= ? ORDER BY a.data, a.hora_ini",
            (so_digitos(telefone), relogio.hoje().isoformat()))]


def cancelar_agendamento(ag_id: int, telefone: str) -> dict:
    ag = detalhe_agendamento(ag_id)
    if ag["telefone"] != so_digitos(telefone):
        raise ErroRegra("Esse agendamento não está no seu número.")
    if ag["status"] != "agendado":
        raise ErroRegra("Esse agendamento não pode mais ser cancelado.")
    inicio = datetime.fromisoformat(ag["data"]) + timedelta(hours=ag["hora_ini"])
    if inicio - relogio.agora() < timedelta(hours=24):
        raise ErroRegra("Cancelamentos só são feitos com 24h de antecedência. "
                        "Vou chamar um atendente para ver o seu caso.")
    with db.conexao() as c:
        c.execute("UPDATE agendamentos SET status = 'cancelado' WHERE id = ?", (ag_id,))
    return detalhe_agendamento(ag_id)


def tabela_precos_texto() -> str:
    with db.conexao() as c:
        linhas = [f"• {r['descricao']}: {brl(r['valor_hora'])}/hora" for r in c.execute("SELECT * FROM precos ORDER BY id")]
        desc = [f"• {r['nome']}" for r in c.execute("SELECT nome FROM descontos WHERE ativo = 1 ORDER BY id")]
    return "\n".join(linhas) + ("\n\nDescontos:\n" + "\n".join(desc) if desc else "")
