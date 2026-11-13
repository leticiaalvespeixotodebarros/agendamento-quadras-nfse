"""Tools the AI agent can call. Each returns a simple dictionary (turned into JSON for the model).

The customer's phone number comes from WhatsApp (it is never asked) and is fixed here, outside the model's control.
(The tool descriptions below stay in Portuguese: they are prompts for a Portuguese-speaking assistant.)
"""
from __future__ import annotations

from . import conversas, regras

DEFINICOES = [
    {"name": "consultar_horarios",
     "description": "Lista, por quadra, as faixas de horário livres em uma data. Use SEMPRE antes de oferecer um horário.",
     "input_schema": {"type": "object", "properties": {"data": {"type": "string", "description": "AAAA-MM-DD"}},
                      "required": ["data"]}},
    {"name": "calcular_preco",
     "description": "Calcula o valor de uma locação, já com os descontos aplicáveis. Nunca calcule preço por conta própria.",
     "input_schema": {"type": "object", "properties": {
         "data": {"type": "string", "description": "AAAA-MM-DD"},
         "hora_inicio": {"type": "integer", "description": "hora cheia de início, 0-23"},
         "horas": {"type": "integer", "description": "quantidade de horas"},
         "cupom": {"type": "string", "description": "cupom informado pelo cliente, se houver"}},
         "required": ["data", "hora_inicio", "horas"]}},
    {"name": "criar_agendamento",
     "description": ("Cria a reserva. Só chame depois de o cliente ter confirmado data, horário, duração e valor, "
                     "e de você ter o NOME COMPLETO e o CPF dele."),
     "input_schema": {"type": "object", "properties": {
         "data": {"type": "string"}, "hora_inicio": {"type": "integer"}, "horas": {"type": "integer"},
         "nome_completo": {"type": "string"}, "cpf": {"type": "string"}, "cupom": {"type": "string"}},
         "required": ["data", "hora_inicio", "horas", "nome_completo", "cpf"]}},
    {"name": "meus_agendamentos",
     "description": "Lista os agendamentos futuros deste cliente.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "cancelar_agendamento",
     "description": "Cancela um agendamento deste cliente (regra de antecedência é aplicada pelo sistema).",
     "input_schema": {"type": "object", "properties": {"agendamento_id": {"type": "integer"}},
                      "required": ["agendamento_id"]}},
    {"name": "chamar_atendente",
     "description": ("Passa a conversa para um atendente humano. Use quando o cliente pedir uma pessoa, em reclamações, "
                     "ou quando você não souber responder com segurança."),
     "input_schema": {"type": "object", "properties": {"motivo": {"type": "string"}}, "required": ["motivo"]}},
]


def executar(nome: str, args: dict, telefone: str) -> dict:
    try:
        if nome == "consultar_horarios":
            d = regras.interpretar_data(args["data"])
            return {"data": regras.fmt_data(d), "quadras": regras.resumo_disponibilidade(d)}
        if nome == "calcular_preco":
            d = regras.interpretar_data(args["data"])
            o = regras.orcar(d, int(args["hora_inicio"]), int(args["horas"]), args.get("cupom", ""))
            return {"valor_bruto": regras.brl(o.bruto), "desconto": regras.brl(o.desconto),
                    "desconto_aplicado": o.desconto_nome or "nenhum", "valor_total": regras.brl(o.total), "avisos": o.avisos}
        if nome == "criar_agendamento":
            ag = regras.criar_agendamento(
                telefone=telefone, nome=args["nome_completo"], cpf=args["cpf"],
                data=regras.interpretar_data(args["data"]), hora_ini=int(args["hora_inicio"]),
                horas=int(args["horas"]), cupom=args.get("cupom", ""))
            return {"ok": True, "agendamento_id": ag["id"], "quadra": ag["quadra"], "data": regras.fmt_data(ag["data"]),
                    "horario": f"{ag['hora_ini']:02d}h às {ag['hora_fim']:02d}h", "valor": regras.brl(ag["valor"]),
                    "pagamento": "no local, no dia da locação"}
        if nome == "meus_agendamentos":
            return {"agendamentos": [{"id": a["id"], "quadra": a["quadra"], "data": regras.fmt_data(a["data"]),
                                      "horario": f"{a['hora_ini']:02d}h às {a['hora_fim']:02d}h",
                                      "valor": regras.brl(a["valor"])}
                                     for a in regras.agendamentos_do_cliente(telefone)]}
        if nome == "cancelar_agendamento":
            a = regras.cancelar_agendamento(int(args["agendamento_id"]), telefone)
            return {"ok": True, "cancelado": a["id"]}
        if nome == "chamar_atendente":
            conversas.passar_para_humano(telefone, args.get("motivo", ""))
            return {"ok": True, "aviso": "Um atendente vai continuar a conversa. Avise o cliente."}
        return {"erro": f"Ferramenta desconhecida: {nome}"}
    except regras.ErroRegra as e:
        return {"erro": str(e)}
    except (KeyError, ValueError, TypeError) as e:
        return {"erro": f"Dados inválidos para {nome}: {e}"}
