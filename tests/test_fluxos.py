"""Fluxos completos: conversa → agendamento → fechamento do dono → notas."""
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

from app import conversas, db, fechamento, regras, relogio
from app.fiscal import DadosNota, ErroEmissao, EmissorSimulado, planilha
from conftest import CLIENTE, CPF_OK

DONO = "5511900000001"


def conversar(tel, *falas):
    return [conversas.processar(tel, f) for f in falas]


def reservar_pelo_chat(tel=CLIENTE, nome="Maria Souza", dia="18/11", hora="19", horas="1"):
    return conversar(tel, "oi", "1", dia, hora, horas, "não", nome, CPF_OK, "sim")


def test_conversa_completa_cria_reserva():
    r = reservar_pelo_chat()
    assert "Reservado" in r[-1][0]
    assert "Horários livres" in r[2][0]
    with db.conexao() as c:
        a = c.execute("SELECT * FROM agendamentos").fetchone()
    assert (a["nome"], a["cpf"], a["telefone"], a["valor"]) == ("Maria Souza", "52998224725", CLIENTE, 100.0)


def test_conversa_rejeita_cpf_invalido_e_pede_de_novo():
    r = conversar(CLIENTE, "1", "18/11", "19", "1", "não", "Maria Souza", "111.111.111-11")
    assert "não parece válido" in r[-1][0]
    assert conversas.estado(CLIENTE)["passo"] == "cpf"


def test_atendente_assume_e_bot_cala():
    conversar(CLIENTE, "4")
    assert conversas.modo(CLIENTE) == "humano"
    assert conversas.processar(CLIENTE, "alguém aí?") == []          # bot não responde
    conversas.responder_humano(CLIENTE, "Oi, aqui é o atendente!")
    conversas.devolver_ao_bot(CLIENTE)
    assert conversar(CLIENTE, "menu")[0][0].startswith("Olá!")
    autores = [m["autor"] for m in conversas.historico(CLIENTE)]
    assert "humano" in autores


def _tres_locacoes_passadas():
    ids = []
    for i, n in enumerate(["Maria Souza", "João Pedro Lima", "Ana Clara Dias"]):
        ids.append(regras.criar_agendamento(telefone=f"55119999900{i}", nome=n, cpf=CPF_OK, data=date(2026, 11, 18),
                                            hora_ini=19, horas=1)["id"])
    relogio.fixar(datetime(2026, 11, 20, 9, 0))                       # dias depois: as locações já aconteceram
    return ids


def test_interpretar_resposta():
    f = fechamento.interpretar_resposta
    assert f("OK", [1, 2, 3]) == set()
    assert f("concordo", [1, 2, 3]) == set()
    assert f("ok menos 3 e 7", [1, 2, 3, 7]) == {3, 7}
    assert f("Concordo, exceto 2", [1, 2, 3]) == {2}
    for ruim in ("talvez", "ok 2", "ok menos", "ok menos 9"):
        with pytest.raises(fechamento.ErroResposta):
            f(ruim, [1, 2, 3])


def test_fechamento_pelo_whatsapp_do_dono_emite_so_o_confirmado():
    _tres_locacoes_passadas()
    lista = conversas.processar(DONO, "fechamento")[0]
    assert "1)" in lista and "3)" in lista and "R$ 300,00" in lista
    assert "CPF 529.982.247-25" in lista
    res = conversas.processar(DONO, "ok menos 2")[0]
    assert "2 locação(ões) confirmada(s), 1 marcada(s)" in res and "2 nota(s)" in res
    with db.conexao() as c:
        st = {r["nome"]: r["status"] for r in c.execute("SELECT nome, status FROM agendamentos")}
        notas = c.execute("SELECT * FROM notas").fetchall()
    assert st == {"Maria Souza": "confirmado", "João Pedro Lima": "nao_realizado", "Ana Clara Dias": "confirmado"}
    assert len(notas) == 2 and all(n["numero"].startswith("SIMULACAO") for n in notas)
    assert notas[0]["competencia"] == "2026-11-18"                    # competência = data da locação
    assert "Não há locações pendentes" in conversas.processar(DONO, "fechamento")[0]   # nada duplica


def test_locacao_futura_nao_entra_no_fechamento():
    regras.criar_agendamento(telefone="1", nome="Maria Souza", cpf=CPF_OK, data=date(2026, 11, 25), hora_ini=19, horas=1)
    assert fechamento.gerar() is None


def test_lote_nao_para_quando_uma_nota_falha():
    _tres_locacoes_passadas()

    class Quebrado(EmissorSimulado):
        def emitir(self, d: DadosNota):
            if d.tomador_nome.startswith("João"):
                raise ErroEmissao("CPF recusado pelo Sefin")
            return super().emitir(d)

    fid = fechamento.gerar()
    res = fechamento.concluir(fid, set(), Quebrado())
    assert res.notas_emitidas == 2 and len(res.falhas) == 1 and "João" in res.falhas[0]
    with db.conexao() as c:
        assert c.execute("SELECT status FROM fechamentos WHERE id = ?", (fid,)).fetchone()[0] == "aberto"
    retry = fechamento.reemitir_com_erro()                             # nova tentativa só do que falhou
    assert retry.notas_emitidas == 1 and not retry.falhas
    with db.conexao() as c:
        assert c.execute("SELECT COUNT(*) FROM notas WHERE status = 'emitida'").fetchone()[0] == 3


def test_aviso_de_competencia_de_mes_anterior():
    regras.criar_agendamento(telefone="1", nome="Maria Souza", cpf=CPF_OK, data=date(2026, 11, 18), hora_ini=19, horas=1)
    relogio.fixar(datetime(2026, 12, 2, 9, 0))
    fid = fechamento.gerar()
    assert "mês anterior" in fechamento.texto_lista(fid)


def test_planilha_no_formato_do_emissor():
    import io, openpyxl
    _tres_locacoes_passadas()
    fechamento.concluir(fechamento.gerar(), {2})
    ws = openpyxl.load_workbook(io.BytesIO(planilha.exportar())).active
    cab = [c.value for c in ws[3]]
    assert cab[:5] == ["Origem", "ID da venda", "Data da venda", "Tomador (nome)", "CPF/CNPJ"] and cab[-1] == "Emitir? (SIM/NÃO)"
    dados = [[c.value for c in r] for r in ws.iter_rows(min_row=4)]
    assert len(dados) == 2 and dados[0][4] == "529.982.247-25" and dados[0][-2] == "18/11/2026"


def test_painel_web_abre_todas_as_telas():
    from app.main import app
    _tres_locacoes_passadas()
    with TestClient(app) as cli:
        for rota in ["/", "/agenda", "/agenda?data=2026-11-18", "/config", "/fechamento", "/notas", "/inbox", "/simulador"]:
            r = cli.get(rota)
            assert r.status_code == 200, (rota, r.status_code)
        r = cli.post("/simulador/enviar", data={"telefone": CLIENTE, "texto": "oi"})
        assert r.json()["ok"]
        assert cli.get("/simulador/mensagens", params={"telefone": CLIENTE}).json()[-1]["autor"] == "bot"
        r = cli.post("/config/precos/novo", data={"descricao": "Teste", "dias": ["0"], "hora_ini": "8", "hora_fim": "9",
                                                  "valor_hora": "55,5"}, follow_redirects=False)
        assert r.status_code == 303
        assert cli.get("/notas/exportar.xlsx").status_code == 200


def test_webhook_meta_recebe_mensagem_e_ignora_audio():
    from app.main import app
    payload = {"entry": [{"changes": [{"value": {"messages": [
        {"from": CLIENTE, "type": "text", "text": {"body": "oi"}},
        {"from": CLIENTE, "type": "audio", "audio": {"id": "x"}}]}}]}]}
    with TestClient(app) as cli:
        assert cli.post("/webhook", json=payload).status_code == 200
    assert [m["autor"] for m in conversas.historico(CLIENTE)] == ["cliente", "bot"]
