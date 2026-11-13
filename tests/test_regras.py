from datetime import date

import pytest

from app import db, regras
from conftest import CLIENTE, CPF_OK

SEG, SAB = date(2026, 11, 18), date(2026, 11, 21)    # quarta e sábado


def test_cpf():
    assert regras.cpf_valido(CPF_OK)
    assert not regras.cpf_valido("111.111.111-11")
    assert not regras.cpf_valido("529.982.247-24")
    assert not regras.cpf_valido("123")


def test_preco_e_descontos():
    assert regras.orcar(SEG, 10, 1).total == 70.0                     # dia útil, dia
    assert regras.orcar(SEG, 19, 1).total == 100.0                    # dia útil, noite
    o = regras.orcar(SEG, 19, 2)                                      # 2h: 10% automático
    assert (o.bruto, o.desconto, o.total) == (200.0, 20.0, 180.0)
    assert regras.orcar(SAB, 10, 1).total == 120.0
    assert regras.orcar(SEG, 19, 1, "primeira").total == 90.0         # cupom R$10/h, sem diferenciar maiúscula
    assert regras.orcar(SEG, 19, 1, "XXXX").avisos                    # cupom inexistente avisa


def test_desconto_editavel_pelo_painel():
    with db.conexao() as c:
        c.execute("INSERT INTO descontos(nome, tipo, valor, min_horas) VALUES ('Promo 50%', 'percentual', 50, 1)")
    assert regras.orcar(SEG, 19, 1).total == 50.0                     # maior desconto prevalece


def test_reserva_e_conflito():
    ag = regras.criar_agendamento(telefone=CLIENTE, nome="Maria Souza", cpf=CPF_OK, data=SEG, hora_ini=19, horas=2)
    assert ag["valor"] == 180.0 and ag["status"] == "agendado"
    for _ in range(2):                                                # mais duas reservas lotam as 3 quadras
        regras.criar_agendamento(telefone="1", nome="Ana Lima", cpf=CPF_OK, data=SEG, hora_ini=19, horas=1)
    with pytest.raises(regras.ErroRegra, match="não está mais disponível"):
        regras.criar_agendamento(telefone="2", nome="Jo Silva", cpf=CPF_OK, data=SEG, hora_ini=19, horas=1)   # 3 quadras ocupadas às 19h
    assert regras.criar_agendamento(telefone="2", nome="Jo Silva", cpf=CPF_OK, data=SEG, hora_ini=20, horas=1)  # às 20h ainda há quadra


def test_validacoes():
    ok = dict(telefone=CLIENTE, data=SEG, hora_ini=19, horas=1)
    with pytest.raises(regras.ErroRegra, match="CPF"):
        regras.criar_agendamento(nome="Maria Souza", cpf="111.111.111-11", **ok)
    with pytest.raises(regras.ErroRegra, match="nome completo"):
        regras.criar_agendamento(nome="Maria", cpf=CPF_OK, **ok)
    with pytest.raises(regras.ErroRegra, match="passou"):
        regras.criar_agendamento(nome="Maria Souza", cpf=CPF_OK, telefone="1", data=date(2026, 11, 10), hora_ini=19, horas=1)
    with pytest.raises(regras.ErroRegra, match="Funcionamos"):
        regras.criar_agendamento(nome="Maria Souza", cpf=CPF_OK, telefone="1", data=SEG, hora_ini=5, horas=1)


def test_cancelamento_com_antecedencia():
    ag = regras.criar_agendamento(telefone=CLIENTE, nome="Maria Souza", cpf=CPF_OK, data=SEG, hora_ini=19, horas=1)
    with pytest.raises(regras.ErroRegra, match="não está no seu número"):
        regras.cancelar_agendamento(ag["id"], "999")
    assert regras.cancelar_agendamento(ag["id"], CLIENTE)["status"] == "cancelado"
    assert len(regras.horas_livres(SEG)[ag["quadra_id"]]) == 16       # horário liberado de novo
