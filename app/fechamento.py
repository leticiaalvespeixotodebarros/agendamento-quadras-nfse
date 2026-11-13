"""Closing ("fechamento"): numbered list of rentals for the owner to confirm, reading the reply, issuing the invoices.

Golden rule: the owner decides what happened. The system only records the decision and issues
invoices for the rentals the owner confirmed. Items that fail to issue are skipped and logged;
the rest continue (uninterrupted-batch rule).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from . import db, regras, relogio
from .fiscal import DadosNota, ErroEmissao, emissor_padrao


class ErroResposta(Exception):
    """The owner's reply could not be understood; the message explains what to send."""


def _elegiveis(c) -> list:
    agora = relogio.agora()
    return c.execute(
        "SELECT a.*, q.nome AS quadra FROM agendamentos a JOIN quadras q ON q.id = a.quadra_id "
        "WHERE a.status = 'agendado' AND (a.data < ? OR (a.data = ? AND a.hora_fim <= ?)) "
        "ORDER BY a.data, a.hora_ini, a.id", (agora.date().isoformat(), agora.date().isoformat(), agora.hour)).fetchall()


def gerar() -> int | None:
    """Create (or update) the open closing. Returns its id, or None if there is nothing to confirm."""
    with db.conexao() as c:
        aberto = c.execute("SELECT id FROM fechamentos WHERE status = 'aberto' ORDER BY id DESC LIMIT 1").fetchone()
        elegiveis = _elegiveis(c)
        if aberto:
            fid = aberto["id"]
            ja = {r[0] for r in c.execute("SELECT agendamento_id FROM fechamento_itens WHERE fechamento_id = ?", (fid,))}
        else:
            if not elegiveis:
                return None
            fid = c.execute("INSERT INTO fechamentos(criado_em) VALUES (?)",
                            (relogio.agora().isoformat(timespec="seconds"),)).lastrowid
            ja = set()
        prox = (c.execute("SELECT COALESCE(MAX(numero), 0) FROM fechamento_itens WHERE fechamento_id = ?", (fid,)).fetchone()[0])
        for r in elegiveis:
            if r["id"] not in ja:
                prox += 1
                c.execute("INSERT INTO fechamento_itens VALUES (?,?,?)", (fid, prox, r["id"]))
    return fid


def itens(fid: int, so_pendentes: bool = True) -> list[dict]:
    """Closing items with the rental data."""
    filtro = "AND a.status = 'agendado' " if so_pendentes else ""
    with db.conexao() as c:
        return [dict(r) for r in c.execute(
            "SELECT i.numero, a.*, q.nome AS quadra FROM fechamento_itens i "
            "JOIN agendamentos a ON a.id = i.agendamento_id JOIN quadras q ON q.id = a.quadra_id "
            f"WHERE i.fechamento_id = ? {filtro}ORDER BY i.numero", (fid,))]


def aviso_competencia(its: list[dict]) -> str:
    h = relogio.hoje()
    fora = [i for i in its if date.fromisoformat(i["data"]).strftime("%Y-%m") != h.strftime("%Y-%m")]
    if not fora:
        return ""
    return (f"Atenção: {len(fora)} locação(ões) são de mês anterior ao da emissão. "
            "A competência da nota será a data da locação; confira o fechamento do mês.")


def texto_lista(fid: int) -> str:
    its = itens(fid)
    if not its:
        return "Não há locações pendentes de confirmação. ✅"
    cfg = db.config()
    linhas = [f"*Fechamento – {cfg['empresa_nome']}*", "Confirme as locações que realmente aconteceram e foram pagas:", ""]
    for i in its:
        linhas.append(f"{i['numero']}) {date.fromisoformat(i['data']).strftime('%d/%m')} "
                      f"{i['hora_ini']:02d}h–{i['hora_fim']:02d}h · {i['quadra']} · {i['nome']} · "
                      f"CPF {regras.fmt_cpf(i['cpf'])} · {regras.brl(i['valor'])}")
    total = sum(i["valor"] for i in its)
    linhas += ["", f"Total: {regras.brl(total)} em {len(its)} locação(ões).", ""]
    av = aviso_competencia(its)
    if av:
        linhas += [av, ""]
    linhas += ["Responda *OK* para confirmar todas, ou *OK menos 3 e 7* para confirmar todas exceto as nº 3 e 7 "
               "(não houve locação, não foi pago ou há dado errado)."]
    return "\n".join(linhas)


# ---------- reading the owner's reply ----------
_CONFIRMA = re.compile(r"\b(ok|okay|concordo|confirmo|confirmado|confirmar|tudo certo|certo|sim)\b", re.I)
_EXCETO = re.compile(r"\b(menos|exceto|except[oa]|tirando|sem|nao|não)\b", re.I)


def interpretar_resposta(texto: str, numeros: list[int]) -> set[int]:
    """Return the set of EXCLUDED numbers (not confirmed). Raises ErroResposta if ambiguous."""
    t = texto.strip()
    if not _CONFIRMA.search(t):
        raise ErroResposta("Não entendi. Responda *OK* para confirmar todas, ou *OK menos 3 e 7* "
                           "para tirar a 3 e a 7.")
    m = _EXCETO.search(t)
    if not m:
        if re.search(r"\d", t):
            raise ErroResposta("Para tirar alguma, escreva por exemplo *OK menos 3 e 7*. "
                               "Para confirmar todas, responda só *OK*.")
        return set()
    excl = {int(x) for x in re.findall(r"\d+", t[m.end():])}
    invalidos = sorted(excl - set(numeros))
    if invalidos:
        raise ErroResposta(f"O(s) número(s) {', '.join(map(str, invalidos))} não existe(m) nesta lista "
                           f"(vai de {min(numeros)} a {max(numeros)}).")
    if not excl:
        raise ErroResposta("Diga quais números tirar, ex.: *OK menos 3 e 7*.")
    return excl


@dataclass
class Resultado:
    confirmadas: int = 0
    nao_realizadas: int = 0
    notas_emitidas: int = 0
    falhas: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    def texto(self) -> str:
        t = [f"Pronto! {self.confirmadas} locação(ões) confirmada(s), {self.nao_realizadas} marcada(s) como não realizada(s).",
             f"{self.notas_emitidas} nota(s) fiscal(is) emitida(s)."]
        if self.falhas:
            t.append(f"⚠️ {len(self.falhas)} nota(s) não saíram e ficam para nova tentativa: " + "; ".join(self.falhas))
        t += self.avisos
        return "\n".join(t)


def concluir(fid: int, excluidos: set[int], emissor=None) -> Resultado:
    emissor = emissor or emissor_padrao()
    res = Resultado()
    its = itens(fid)
    agora = relogio.agora()
    with db.conexao() as c:
        for i in its:
            if i["numero"] in excluidos:
                c.execute("UPDATE agendamentos SET status = 'nao_realizado', confirmado_em = ? WHERE id = ?",
                          (agora.isoformat(timespec="seconds"), i["id"]))
                res.nao_realizadas += 1
            else:
                c.execute("UPDATE agendamentos SET status = 'confirmado', confirmado_em = ? WHERE id = ?",
                          (agora.isoformat(timespec="seconds"), i["id"]))
                res.confirmadas += 1
    av = aviso_competencia([i for i in its if i["numero"] not in excluidos])
    if av:
        res.avisos.append(av)
    _emitir_pendentes(emissor, res, [i["id"] for i in its if i["numero"] not in excluidos])
    with db.conexao() as c:
        pend = c.execute("SELECT COUNT(*) FROM fechamento_itens i JOIN agendamentos a ON a.id = i.agendamento_id "
                         "WHERE i.fechamento_id = ? AND a.status = 'agendado'", (fid,)).fetchone()[0]
        if not pend and not res.falhas:
            c.execute("UPDATE fechamentos SET status = 'concluido' WHERE id = ?", (fid,))
    return res


def reemitir_com_erro(emissor=None) -> Resultado:
    """Retry the invoices that failed before (confirmed booking without an issued invoice)."""
    res = Resultado()
    with db.conexao() as c:
        ids = [r[0] for r in c.execute(
            "SELECT a.id FROM agendamentos a LEFT JOIN notas n ON n.agendamento_id = a.id "
            "WHERE a.status = 'confirmado' AND (n.id IS NULL OR n.status = 'erro') ORDER BY a.id")]
    _emitir_pendentes(emissor or emissor_padrao(), res, ids)
    return res


def _emitir_pendentes(emissor, res: Resultado, ag_ids: list[int]) -> None:
    desc = db.config()["descricao_servico"]
    for ag_id in ag_ids:                              # an error NEVER stops the batch
        ag = regras.detalhe_agendamento(ag_id)
        comp = date.fromisoformat(ag["data"])
        try:
            r = emissor.emitir(DadosNota(
                agendamento_id=ag_id, tomador_nome=ag["nome"], tomador_cpf=ag["cpf"], tomador_telefone=ag["telefone"],
                descricao=f"{desc} – {ag['quadra']}, {ag['hora_ini']:02d}h às {ag['hora_fim']:02d}h",
                valor=ag["valor"], data_locacao=comp, competencia=comp))
            _gravar_nota(ag_id, ag["valor"], comp, r.numero, r.chave, r.ambiente, "emitida", "")
            res.notas_emitidas += 1
        except Exception as e:                        # noqa: BLE001 - log it and go on to the next one
            _gravar_nota(ag_id, ag["valor"], comp, None, None, getattr(emissor, "ambiente", "?"), "erro", str(e))
            res.falhas.append(f"{ag['nome']} ({comp.strftime('%d/%m')}): {e}")


def _gravar_nota(ag_id, valor, comp, numero, chave, ambiente, status, erro) -> None:
    with db.conexao() as c:
        c.execute(
            "INSERT INTO notas(agendamento_id, numero, chave, ambiente, emitida_em, competencia, valor, status, erro) "
            "VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(agendamento_id) DO UPDATE SET numero = excluded.numero, "
            "chave = excluded.chave, ambiente = excluded.ambiente, emitida_em = excluded.emitida_em, "
            "status = excluded.status, erro = excluded.erro",
            (ag_id, numero, chave, ambiente, relogio.agora().isoformat(timespec="seconds"), comp.isoformat(), valor, status, erro))
