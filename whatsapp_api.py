import os
import re
from datetime import date
from functools import wraps
from flask import Flask, request, jsonify

from finconecta import database as db
from finconecta.qualidade import numero_br

app = Flask(__name__)
API_TOKEN = os.environ.get("FINCONECTA_API_TOKEN", "")
ALLOWED_PHONES = {
    re.sub(r"\D", "", item)
    for item in os.environ.get("FINCONECTA_ALLOWED_PHONES", "").split(",")
    if item.strip()
}

def only_digits(value):
    return re.sub(r"\D", "", str(value or ""))

def money(value):
    return f"R$ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def require_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        supplied = request.headers.get("X-API-Key", "")

        if not API_TOKEN or supplied != API_TOKEN:
            return jsonify({"error": "Não autorizado."}), 401

        return fn(*args, **kwargs)

    return wrapper




# Confirmações pendentes ficam em memória durante a execução da API.
# Se a API reiniciar, a confirmação pendente é descartada sem gravar a operação.
PENDING_ACTIONS = {}


def _categoria_id(tipo, nome):
    nome = (nome or "").strip()
    if not nome or nome == "-":
        return None
    for item in db.listar_categorias(tipo):
        if str(item["nome"]).casefold() == nome.casefold():
            return item["id"]
    raise ValueError(f"Categoria '{nome}' não encontrada. Consulte as categorias no aplicativo.")


def _confirmacao(phone, action, description):
    PENDING_ACTIONS[phone] = action
    return (
        "⚠️ *CONFIRME A OPERAÇÃO*\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"{description}\n\n"
        "Responda *SIM* para confirmar ou *NÃO* para cancelar.\n"
        "A alteração só será gravada após sua confirmação."
    )


def _executar_acao(action):
    op = action["op"]
    if op == "nova_movimentacao":
        db.inserir_movimento(
            action["tipo"], action["descricao"], action["valor"],
            action["data"], action["categoria_id"], action.get("observacao", ""),
            action.get("recorrencia", "Variável"), action.get("status", "Pago"),
            action.get("vencimento"), action.get("forma_pagamento", ""),
            action.get("parcela_atual"), action.get("total_parcelas")
        )
        return f"✅ *{action['tipo'].upper()} CADASTRADA!*\n{action['descricao']} — {money(action['valor'])}"

    if op == "editar_movimentacao":
        db.salvar_edicao_movimento(
            action["tipo"], action["id"], action["descricao"], action["valor"],
            action["data"], action["categoria_id"], action["observacao"],
            action["recorrencia"], action["status"], action["vencimento"],
            action["forma_pagamento"], action["parcela_atual"], action["total_parcelas"]
        )
        return f"✅ *LANÇAMENTO ATUALIZADO!*\n{action['descricao']} — {money(action['valor'])}"

    if op == "excluir_movimentacao":
        db.excluir_movimento(action["tipo"], action["id"])
        return f"✅ *LANÇAMENTO EXCLUÍDO!*\nCódigo: #{action['id']}"

    if op == "nova_divida":
        db.inserir_divida(action["credor"], action["descricao"], action["valor"], action["vencimento"])
        return f"✅ *DÍVIDA CADASTRADA!*\nCredor: {action['credor']}\nDescrição: {action['descricao']}\nValor: {money(action['valor'])}"

    if op == "pagar_divida":
        db.registrar_pagamento(action["id"], action["valor"], date.today().isoformat(),
                               "Pagamento registrado via WhatsApp")
        debt = next((x for x in db.listar_dividas() if x["id"] == action["id"]), None)
        remaining = debt["saldo"] if debt else 0
        return f"✅ *PAGAMENTO REGISTRADO!*\nDívida: #{action['id']}\nPago: {money(action['valor'])}\nSaldo restante: {money(remaining)}"

    raise ValueError("Operação pendente inválida.")


# Estado de conversas: mantém os dados entre as mensagens enquanto a API estiver ligada.
CONVERSATION_STATES = {}
MENU_CONTEXTS = {}


def _categorias_texto(tipo):
    cats = db.listar_categorias(tipo)
    if not cats:
        return "Não há categorias cadastradas para esse tipo no aplicativo. Cadastre uma categoria e tente novamente."
    linhas = ["Escolha uma categoria:"]
    linhas.extend(f"{i}️⃣ {item['nome']}" for i, item in enumerate(cats, start=1))
    linhas.extend(["", "0️⃣ Voltar ao menu principal"])
    return "\n".join(linhas)


def _validar_categoria(tipo, nome):
    nome = (nome or "").strip()
    for item in db.listar_categorias(tipo):
        if str(item['nome']).casefold() == nome.casefold():
            return item['id'], item['nome']
    return None, None


def _iniciar_confirmacao(phone, action):
    PENDING_ACTIONS[phone] = action
    CONVERSATION_STATES.pop(phone, None)
    if action['op'] == 'nova_movimentacao':
        resumo = (f"Confirma a {action['tipo']}?\n\nDescrição: {action['descricao']}\n"
                  f"Valor: {money(action['valor'])}\nCategoria: {action['categoria_nome']}\n"
                  f"Data: {date.fromisoformat(action['data']):%d/%m/%Y}")
    elif action['op'] == 'nova_divida':
        resumo = (f"Confirma a dívida?\n\nCredor: {action['credor']}\nDescrição: {action['descricao']}\n"
                  f"Valor: {money(action['valor'])}\nVencimento: {action['vencimento'] or 'Não informado'}")
    elif action['op'] == 'pagar_divida':
        resumo = (f"Confirma o pagamento?\n\nDívida: #{action['id']} — {action['credor']}\n"
                  f"Valor: {money(action['valor'])}\nSaldo atual: {money(action['saldo'])}")
    elif action['op'] == 'excluir_movimentacao':
        resumo = (f"Confirma a exclusão?\n\n{action['tipo'].title()} #{action['id']}\n"
                  f"{action['descricao']} — {money(action['valor'])}")
    elif action['op'] == 'excluir_divida':
        resumo = (f"Confirma a exclusão da dívida #{action['id']}?\n"
                  f"Credor: {action['credor']}\nDescrição: {action['descricao']}\n"
                  f"Valor: {money(action['valor'])}")
    elif action['op'] == 'editar_campo':
        resumo = (f"Confirma a alteração?\n\n{action['tipo'].title()}: {action['descricao']}\n"
                  f"Campo: {action['campo']}\nNovo valor: {action['novo_valor']}")
    else:
        resumo = "Confirma esta operação?"
    return resumo + "\n\nResponda *SIM* para confirmar ou *NÃO* para cancelar."


def _executar_acao(action):
    op = action['op']
    if op == 'nova_movimentacao':
        db.inserir_movimento(action['tipo'], action['descricao'], action['valor'], action['data'],
            action['categoria_id'], 'Cadastrado via WhatsApp', 'Variável', 'Pago')
        return f"✅ {action['tipo'].title()} cadastrada!\n{action['descricao']} — {money(action['valor'])}\n\n0️⃣ Voltar ao menu principal"
    if op == 'nova_divida':
        db.inserir_divida(action['credor'], action['descricao'], action['valor'], action['vencimento'])
        return f"✅ Dívida cadastrada!\n{action['credor']} — {action['descricao']} — {money(action['valor'])}\n\n0️⃣ Voltar ao menu principal"
    if op == 'pagar_divida':
        db.registrar_pagamento(action['id'], action['valor'], date.today().isoformat(), 'Pagamento via WhatsApp')
        debt = next((x for x in db.listar_dividas() if int(x['id']) == action['id']), None)
        return f"✅ Pagamento registrado!\nDívida #{action['id']}\nSaldo restante: {money(debt['saldo'] if debt else 0)}\n\n0️⃣ Voltar ao menu principal"
    if op == 'excluir_movimentacao':
        db.excluir_movimento(action['tipo'], action['id'])
        return f"✅ {action['tipo'].title()} #{action['id']} excluída.\n\n0️⃣ Voltar ao menu principal"
    if op == 'excluir_divida':
        with db.conectar() as con:
            pagamentos = con.execute('SELECT COUNT(*) FROM pagamentos WHERE divida_id=?', (action['id'],)).fetchone()[0]
            if pagamentos:
                raise ValueError('Esta dívida possui pagamentos registrados. Para preservar o histórico financeiro, ela não pode ser excluída pelo WhatsApp.')
            cur = con.execute('DELETE FROM dividas WHERE id=?', (action['id'],))
            if cur.rowcount == 0:
                raise ValueError('Dívida não encontrada.')
        return f"✅ Dívida #{action['id']} excluída.\n\n0️⃣ Voltar ao menu principal"
    if op == 'editar_campo':
        c = action['registro']
        tipo = action['tipo']
        descricao = action.get('descricao', c['descricao'])
        valor = action.get('valor', c['valor'])
        data_mov = action.get('data', c['data'])
        categoria_id = action.get('categoria_id', c['categoria_id'])
        db.salvar_edicao_movimento(tipo, action['id'], descricao, valor, data_mov, categoria_id,
            c['observacao'] or '', c['tipo_recorrencia'] or 'Variável', c['status'] or 'Pago',
            c['vencimento'], c['forma_pagamento'] or '', c['parcela_atual'], c['total_parcelas'])
        return f"✅ {tipo.title()} #{action['id']} atualizada.\n\n0️⃣ Voltar ao menu principal"
    raise ValueError('Operação não reconhecida.')


def _continuar_conversa(phone, answer):
    state = CONVERSATION_STATES.get(phone)
    if not state:
        return None
    step = state['step']
    tipo = state.get('tipo')
    data = state['data']

    # Fluxo guiado de cadastro de receita/despesa iniciado pelo submenu.
    if state.get('flow') == 'movimento' and step == 'descricao_movimento':
        if len(answer.strip()) < 2:
            return 'Informe uma descrição com pelo menos 2 caracteres.'
        data['descricao'] = answer.strip()
        state['step'] = 'valor_movimento'
        return 'Qual é o valor? Exemplo: 250,00'

    if state.get('flow') == 'movimento' and step == 'valor_movimento':
        try:
            value = numero_br(answer)
            if value <= 0:
                raise ValueError()
        except Exception:
            return 'Valor inválido. Informe um valor maior que zero. Exemplo: 250,00'
        data['valor'] = value
        state['step'] = 'categoria'
        return _categorias_texto(tipo)

    if step == 'categoria':
        # Aceita tanto o número exibido na lista quanto o nome da categoria.
        cats = db.listar_categorias(tipo)
        if answer.strip().isdigit():
            pos = int(answer.strip())
            if 1 <= pos <= len(cats):
                cid, nome = cats[pos - 1]['id'], cats[pos - 1]['nome']
            else:
                cid, nome = None, None
        else:
            cid, nome = _validar_categoria(tipo, answer)
        if cid is None:
            return "Opção inválida. Escolha um número da lista ou informe o nome da categoria.\n\n" + _categorias_texto(tipo)
        data['categoria_id'], data['categoria_nome'] = cid, nome
        action = {'op':'nova_movimentacao', 'tipo':tipo, 'descricao':data['descricao'],
                  'valor':data['valor'], 'data':date.today().isoformat(), 'categoria_id':cid,
                  'categoria_nome':nome}
        return _iniciar_confirmacao(phone, action)

    if step == 'credor':
        if len(answer) < 2:
            return 'Informe o nome do credor para continuar.'
        data['credor'] = answer
        state['step'] = 'descricao'
        return 'Qual é a descrição da dívida?'
    if step == 'descricao':
        if len(answer) < 2:
            return 'Informe uma descrição para continuar.'
        data['descricao'] = answer
        state['step'] = 'valor'
        return 'Qual é o valor da dívida? Exemplo: 1500,00'
    if step == 'valor':
        try:
            v = numero_br(answer)
            if v <= 0: raise ValueError()
        except Exception:
            return 'Valor inválido. Informe somente um valor maior que zero. Exemplo: 1500,00'
        data['valor'] = v
        state['step'] = 'vencimento'
        return 'Qual é o vencimento? Envie no formato DD/MM/AAAA ou responda *sem vencimento*.'
    if step == 'vencimento':
        if answer.casefold() in ('sem vencimento', 'não', 'nao', '-'):
            due = None
        else:
            try:
                due = date.fromisoformat(answer).isoformat() if re.fullmatch(r'\d{4}-\d{2}-\d{2}', answer) else date.strptime(answer, '%d/%m/%Y').isoformat()
            except Exception:
                try:
                    from datetime import datetime
                    due = datetime.strptime(answer, '%d/%m/%Y').date().isoformat()
                except Exception:
                    return 'Data inválida. Informe DD/MM/AAAA ou responda *sem vencimento*.'
        return _iniciar_confirmacao(phone, {'op':'nova_divida', **data, 'vencimento':due})

    if step == 'id_divida':
        try: debt_id = int(answer)
        except Exception: return 'ID inválido. Informe somente o número da dívida.'
        debt = next((x for x in db.listar_dividas() if int(x['id']) == debt_id), None)
        if debt is None: return 'Dívida não encontrada. Informe novamente o ID.'
        state['step'] = 'pagamento_valor'
        state['data'] = {'id': debt_id, 'credor': debt['credor'], 'saldo': float(debt['saldo'])}
        return f"Qual valor deseja pagar? Saldo atual: {money(debt['saldo'])}."

    if step == 'pagamento_valor':
        try:
            v = numero_br(answer)
            if v <= 0 or v > float(data['saldo']) + 0.00001: raise ValueError()
        except Exception:
            return f"Valor inválido. Informe um valor maior que zero e até {money(data['saldo'])}."
        return _iniciar_confirmacao(phone, {'op':'pagar_divida','id':data['id'],'credor':data['credor'],'valor':v,'saldo':data['saldo']})

    if step == 'editar_campo':
        field = answer.casefold().strip()
        if field in ('descrição','descricao','nome'):
            state['step'] = 'editar_descricao'
            return 'Envie a nova descrição.'
        if field in ('valor','preço','preco'):
            state['step'] = 'editar_valor'
            return 'Envie o novo valor. Exemplo: 890,00'
        if field in ('categoria','categoria'):
            state['step'] = 'editar_categoria'
            return _categorias_texto(tipo)
        if field in ('data',):
            state['step'] = 'editar_data'
            return 'Envie a nova data no formato DD/MM/AAAA.'
        return 'Qual campo deseja alterar? Responda: descrição, valor, categoria ou data.'
    if step == 'editar_descricao':
        if len(answer) < 2: return 'A descrição não pode ficar vazia. Envie novamente.'
        state['action']['descricao'] = answer
        state['action']['campo'] = 'Descrição'
        state['action']['novo_valor'] = answer
        return _iniciar_confirmacao(phone, state['action'])
    if step == 'editar_valor':
        try:
            v = numero_br(answer)
            if v <= 0: raise ValueError()
        except Exception:
            return 'Valor inválido. Informe um valor maior que zero.'
        state['action']['valor'] = v
        state['action']['campo'] = 'Valor'
        state['action']['novo_valor'] = money(v)
        return _iniciar_confirmacao(phone, state['action'])
    if step == 'editar_categoria':
        cid, name = _validar_categoria(tipo, answer)
        if cid is None: return 'Categoria não encontrada.\n\n' + _categorias_texto(tipo)
        state['action']['categoria_id'] = cid
        state['action']['campo'] = 'Categoria'
        state['action']['novo_valor'] = name
        return _iniciar_confirmacao(phone, state['action'])
    if step == 'editar_data':
        try:
            from datetime import datetime
            d = datetime.strptime(answer, '%d/%m/%Y').date().isoformat()
        except Exception:
            return 'Data inválida. Envie no formato DD/MM/AAAA.'
        state['action']['data'] = d
        state['action']['campo'] = 'Data'
        state['action']['novo_valor'] = answer
        return _iniciar_confirmacao(phone, state['action'])
    return 'Não consegui continuar. Digite *menu* para recomeçar.'



def _menu_principal():
    return (
        "💙 *FinConecta*\n\n"
        "👋 Olá! Seja bem-vindo ao FinConecta!\n\n"
        "Seu assistente financeiro está pronto para ajudar.\n\n"
        "📊 *CONSULTAS*\n\n"
        "1️⃣ Resumo financeiro\n"
        "2️⃣ Receitas\n"
        "3️⃣ Despesas\n"
        "4️⃣ Dívidas\n\n"
        "📈 *ANÁLISES E CONHECIMENTO*\n\n"
        "8️⃣ Planejamento financeiro\n"
        "9️⃣ Relatórios\n"
        "🔟 Educação financeira\n"
        "1️⃣1️⃣ Dicas inteligentes\n\n"
        "⚙️ *OUTRAS OPÇÕES*\n\n"
        "1️⃣2️⃣ Backup\n\n"
        "0️⃣ Ajuda / Menu principal"
    )


def _menu_secao(tipo):
    menus = {
        "receita": "💰 *GERENCIAR RECEITAS*\n\n1️⃣ Consultar receitas\n2️⃣ Cadastrar receita\n3️⃣ Editar receita\n4️⃣ Excluir receita\n\n0️⃣ Voltar ao menu principal",
        "despesa": "💸 *GERENCIAR DESPESAS*\n\n1️⃣ Consultar despesas\n2️⃣ Cadastrar despesa\n3️⃣ Editar despesa\n4️⃣ Excluir despesa\n\n0️⃣ Voltar ao menu principal",
        "divida": "📋 *GERENCIAR DÍVIDAS*\n\n1️⃣ Consultar dívidas\n2️⃣ Cadastrar dívida\n3️⃣ Editar dívida\n4️⃣ Excluir dívida\n\n0️⃣ Voltar ao menu principal",
    }
    return menus[tipo]


def _menu_modulo(nome, opcoes):
    return f"*{nome.upper()}*\n\n{opcoes}\n\n0️⃣ Voltar ao menu principal"


def _voltar_menu(tipo=None):
    if tipo:
        nome = {"receita": "Receitas", "despesa": "Despesas", "divida": "Dívidas"}[tipo]
        return f"\n\n━━━━━━━━━━━━━━━━━━\n0 — Voltar para {nome}"
    return "\n\n━━━━━━━━━━━━━━━━━━\n0 — Voltar ao menu"


def _formatar_data(valor):
    try:
        return date.fromisoformat(str(valor)[:10]).strftime("%d/%m/%Y")
    except Exception:
        return str(valor or "Data não informada")


def _consulta_resumo(today):
    receitas, despesas, dividas, pendentes = db.resumo_mes(today.year, today.month)
    saldo = float(receitas) - float(despesas)
    return (
        f"📊 *RESUMO FINANCEIRO — {today:%m/%Y}*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"💰 Receitas do mês: {money(receitas)}\n"
        f"💸 Despesas do mês: {money(despesas)}\n"
        f"📈 Saldo do mês: {money(saldo)}\n"
        f"⏳ Despesas pendentes: {money(pendentes)}\n"
        f"📋 Dívidas em aberto: {money(dividas)}"
        + _voltar_menu()
    )


def _consulta_movimentacoes(tipo, today):
    rows = db.listar_movimentos(tipo, today.month, today.year)
    titulo = "RECEITAS" if tipo == "receita" else "DESPESAS"
    emoji = "💰" if tipo == "receita" else "💸"

    if not rows:
        return f"{emoji} *{titulo} — {today:%m/%Y}*\nNenhuma movimentação encontrada neste mês." + _voltar_menu(tipo)

    # Total efetivamente recebido: considera como recebido o que estiver marcado como Pago.
    if tipo == "receita":
        pagas = [x for x in rows if str(x["status"]).casefold() == "pago"] if "status" in rows[0].keys() else rows
        total = sum(float(x["valor"]) for x in pagas)
        label_total = "Total recebido"
    else:
        total = sum(float(x["valor"]) for x in rows)
        label_total = "Total gasto"

    linhas = [
        f"{emoji} *{titulo} — {today:%m/%Y}*",
        "━━━━━━━━━━━━━━━━━━",
        f"*{label_total}: {money(total)}*",
        "",
        "*Últimas movimentações:*"
    ]

    for item in rows[:5]:
        linhas.append(
            f"• {item['descricao']} — {money(item['valor'])}\n"
            f"  { _formatar_data(item['data'])} | {item['categoria']}"
        )

    if len(rows) > 5:
        linhas.append(f"\nMostrando 5 de {len(rows)} movimentações.")
    return "\n".join(linhas) + _voltar_menu(tipo)



def _consulta_dividas():
    debts = db.listar_dividas()
    if not debts:
        return "📋 *DÍVIDAS*\nVocê não possui dívidas cadastradas." + _voltar_menu('divida')

    saldo_total = sum(float(x["saldo"]) for x in debts)
    linhas = [
        "📋 *SUAS DÍVIDAS*",
        "━━━━━━━━━━━━━━━━━━",
        f"*Total pendente: {money(saldo_total)}*",
        "",
        "*Detalhamento:*"
    ]
    for item in debts[:10]:
        linhas.append(
            f"• *{item['credor']}* — {item['descricao']}\n"
            f"  Saldo: {money(item['saldo'])}"
        )
        # Exibe parcelas somente se esses campos estiverem disponíveis no retorno do banco.
        chaves = item.keys() if hasattr(item, "keys") else ()
        quantidade = item["quantidade_parcelas"] if "quantidade_parcelas" in chaves else None
        valor_parcela = item["valor_parcela"] if "valor_parcela" in chaves else None
        pago = float(item["pago"]) if "pago" in chaves else 0
        if quantidade:
            linhas.append(f"  Parcelamento: {quantidade} parcelas")
            if valor_parcela:
                linhas.append(f"  Valor da parcela: {money(valor_parcela)}")
        if pago > 0:
            linhas.append(f"  Já pago: {money(pago)}")
        if "vencimento" in chaves and item["vencimento"]:
            linhas.append(f"  Vencimento: {_formatar_data(item['vencimento'])}")

    if len(debts) > 10:
        linhas.append(f"\nMostrando 10 de {len(debts)} dívidas.")
    return "\n".join(linhas) + _voltar_menu('divida')



def _mes_atual():
    hoje = date.today()
    return hoje.year, hoje.month


def _planejamento_financeiro():
    ano, mes = _mes_atual()
    receitas, despesas, dividas, pendentes = db.resumo_mes(ano, mes)
    saldo = receitas - despesas
    necessidades = receitas * 0.50
    desejos = receitas * 0.30
    objetivos = receitas * 0.20

    linhas = [
        f"📈 *PLANEJAMENTO FINANCEIRO — {mes:02d}/{ano}*",
        "━━━━━━━━━━━━━━━━━━",
        f"Receitas do mês: *{money(receitas)}*",
        f"Despesas do mês: *{money(despesas)}*",
        f"Saldo do mês: *{money(saldo)}*",
        "",
        "🎯 *REGRA 50/30/20*",
        f"50% Necessidades: {money(necessidades)}",
        f"30% Desejos: {money(desejos)}",
        f"20% Objetivos: {money(objetivos)}",
        "",
    ]
    if receitas <= 0:
        linhas.append("Cadastre suas receitas para calcular os limites sugeridos da regra 50/30/20.")
    else:
        pct = despesas / receitas * 100
        linhas.append(f"Despesas representam *{pct:.1f}%* das receitas do mês.")
        if pct > 80:
            linhas.append("⚠️ Atenção: suas despesas estão acima de 80% das receitas.")
        elif pct > 50:
            linhas.append("💡 Acompanhe os gastos para manter espaço para desejos e objetivos.")
        else:
            linhas.append("✅ Suas despesas estão dentro de 50% das receitas neste mês.")
    linhas.extend([
        f"Dívidas em aberto: {money(dividas)}",
        f"Despesas pendentes: {money(pendentes)}",
        "",
        "Os percentuais são referências calculadas sobre as receitas registradas no mês."
    ])
    return _menu_modulo("📈 Planejamento financeiro", "\n".join(linhas))


def _relatorio_financeiro():
    ano, mes = _mes_atual()
    receitas, despesas, dividas, pendentes = db.resumo_mes(ano, mes)
    saldo = receitas - despesas
    linhas = [
        f"📑 *RELATÓRIO FINANCEIRO — {mes:02d}/{ano}*",
        "━━━━━━━━━━━━━━━━━━",
        f"Total de receitas: *{money(receitas)}*",
        f"Total de despesas: *{money(despesas)}*",
        f"Resultado do mês: *{money(saldo)}*",
        f"Despesas pendentes: *{money(pendentes)}*",
        f"Saldo de dívidas: *{money(dividas)}*",
        "",
        "🏷️ *DESPESAS POR CATEGORIA*"
    ]
    categorias = db.totais_categoria(ano, mes)
    if categorias:
        for item in categorias[:10]:
            linhas.append(f"• {item['categoria']}: {money(item['total'])}")
    else:
        linhas.append("Não há despesas registradas neste mês.")
    linhas.extend([
        "",
        "📌 Este relatório considera os lançamentos com data dentro do mês atual."
    ])
    return _menu_modulo("📑 Relatórios", "\n".join(linhas))


def _educacao_financeira():
    return _menu_modulo(
        "📚 Educação financeira",
        "Escolha um assunto:\n\n"
        "1️⃣ Regra 50/30/20\n"
        "2️⃣ Reserva de emergência\n"
        "3️⃣ Juros e dívidas\n"
        "4️⃣ Organização do orçamento\n\n"
        "Digite o número do assunto ou 0 para voltar."
    )


def _conteudo_educacao(opcao):
    conteudos = {
        "1": ("🎯 *REGRA 50/30/20*",
              "Use a renda líquida como referência: até 50% para necessidades, 30% para desejos e 20% para objetivos financeiros. Ajuste os percentuais à sua realidade."),
        "2": ("🛟 *RESERVA DE EMERGÊNCIA*",
              "A reserva serve para despesas inesperadas. Comece com depósitos pequenos e regulares, priorizando um valor que você consiga manter. O tamanho ideal depende da estabilidade da renda e dos gastos essenciais."),
        "3": ("💳 *JUROS E DÍVIDAS*",
              "Antes de contratar crédito, confira o Custo Efetivo Total (CET), os juros e o valor final. Para negociar dívidas, compare propostas e priorize entender quais têm maior custo."),
        "4": ("🧾 *ORGANIZAÇÃO DO ORÇAMENTO*",
              "Registre receitas e despesas, confira os gastos periodicamente e separe despesas fixas, variáveis e compromissos futuros. Um orçamento realista precisa considerar datas de vencimento.")
    }
    titulo, texto = conteudos[opcao]
    return f"{titulo}\n\n{texto}\n\n0️⃣ Voltar ao menu principal"


def _dicas_inteligentes():
    ano, mes = _mes_atual()
    receitas, despesas, dividas, pendentes = db.resumo_mes(ano, mes)
    dicas = ["💡 *DICAS INTELIGENTES*"]
    if receitas <= 0 and despesas <= 0:
        dicas.append("Cadastre suas receitas e despesas para receber orientações baseadas na sua movimentação.")
    else:
        if receitas > 0:
            percentual = despesas / receitas * 100
            if percentual >= 100:
                dicas.append("⚠️ Seus gastos registrados alcançaram ou ultrapassaram suas receitas neste mês. Revise despesas e compromissos antes de assumir novos custos.")
            elif percentual >= 80:
                dicas.append("📉 Seus gastos já representam pelo menos 80% das receitas. Confira despesas variáveis e veja onde pode ajustar.")
            else:
                dicas.append("✅ Até agora, seus gastos estão abaixo de 80% das receitas registradas no mês.")
        if pendentes > 0:
            dicas.append(f"⏰ Você tem {money(pendentes)} em despesas pendentes. Confira os vencimentos.")
        if dividas > 0:
            dicas.append(f"💳 Seu saldo de dívidas registrado é {money(dividas)}. Acompanhe pagamentos e encargos.")
        if receitas > despesas:
            dicas.append(f"🎯 Resultado parcial positivo no mês: {money(receitas - despesas)}. Considere direcionar parte para seus objetivos.")
    dicas.append("\nAs dicas usam somente os lançamentos registrados no FinConecta e não substituem orientação financeira profissional.")
    return _menu_modulo("💡 Dicas inteligentes", "\n\n".join(dicas))


def _executar_backup_whatsapp():
    try:
        destino = db.backup_banco()
        return (
            "✅ *BACKUP CONCLUÍDO!*\n\n"
            "Uma cópia de segurança do banco de dados foi salva no servidor da API.\n"
            f"Arquivo: *{destino.name}*\n\n"
            "O arquivo não foi enviado pelo WhatsApp.\n"
            "0️⃣ Voltar ao menu principal"
        )
    except Exception as exc:
        return f"⚠️ Não foi possível realizar o backup: {exc}\n\n0️⃣ Voltar ao menu principal"


def process_command(phone, message):
    today = date.today()
    text = (message or '').strip()
    low = text.casefold()

    # Zero sempre retorna ao menu principal, inclusive durante cadastros,
    # seleções e confirmações pendentes.
    if low == '0':
        CONVERSATION_STATES.pop(phone, None)
        PENDING_ACTIONS.pop(phone, None)
        MENU_CONTEXTS.pop(phone, None)
        return _menu_principal()

    if low in ('sim','confirmar','confirmo'):
        action = PENDING_ACTIONS.pop(phone, None)
        if not action: return 'Não há nenhuma operação aguardando confirmação.'
        try: return _executar_acao(action)
        except Exception as exc: return f'⚠️ Não foi possível concluir: {exc}'
    if low in ('não','nao','cancelar','cancela'):
        if PENDING_ACTIONS.pop(phone, None): return '❎ Operação cancelada. Nenhuma alteração foi realizada.\n\n0️⃣ Voltar ao menu principal'
        if CONVERSATION_STATES.pop(phone, None): return '❎ Cadastro cancelado. Nenhuma alteração foi realizada.\n\n0️⃣ Voltar ao menu principal'
        return 'Não há operação para cancelar.'
    if phone in PENDING_ACTIONS:
        return 'Existe uma operação aguardando confirmação. Responda *SIM* ou *NÃO*.'

    # "menu" retorna à primeira tela; 0 volta conforme a seção atual.
    if low in ('menu', 'início', 'inicio'):
        CONVERSATION_STATES.pop(phone, None)
        PENDING_ACTIONS.pop(phone, None)
        MENU_CONTEXTS.pop(phone, None)
        return _menu_principal()

    # Seleção numerada: a API resolve o ID real internamente.
    selection = CONVERSATION_STATES.get(phone)
    if selection and selection.get("step") == "selecionar_registro":
        if not text.isdigit():
            return "Digite apenas o número do lançamento que deseja selecionar."
        pos = int(text)
        registros = selection.get("registros", [])
        if pos < 1 or pos > len(registros):
            return f"Opção inválida. Escolha um número entre 1 e {len(registros)}."
        current = registros[pos - 1]
        tipo, acao = selection["tipo"], selection["acao"]
        real_id = int(current["id"])
        CONVERSATION_STATES.pop(phone, None)

        if tipo in ("receita", "despesa"):
            if acao == "editar":
                action = {
                    "op": "editar_campo", "tipo": tipo, "id": real_id,
                    "registro": current, "descricao": current["descricao"],
                    "valor": float(current["valor"]), "data": current["data"],
                    "categoria_id": current["categoria_id"],
                    "campo": "a definir", "novo_valor": ""
                }
                CONVERSATION_STATES[phone] = {
                    "flow": "edicao", "step": "editar_campo",
                    "tipo": tipo, "data": {}, "action": action
                }
                return f"Selecionado: *{current['descricao']}* — {money(current['valor'])}.\nO que deseja alterar? Responda: *descrição*, *valor*, *categoria* ou *data*."
            return _iniciar_confirmacao(phone, {
                "op": "excluir_movimentacao", "tipo": tipo, "id": real_id,
                "descricao": current["descricao"], "valor": float(current["valor"])
            })

        if tipo == "divida":
            if acao == "editar":
                return "A edição de dívidas ainda não está disponível."
            return _iniciar_confirmacao(phone, {
                "op": "excluir_divida", "id": real_id,
                "credor": current["credor"], "descricao": current["descricao"],
                "valor": float(current["valor_total"])
            })

    # Escolhas do submenu de Educação Financeira.
    if MENU_CONTEXTS.get(phone) == 'educacao' and low in ('1', '2', '3', '4'):
        MENU_CONTEXTS.pop(phone, None)
        return _conteudo_educacao(low)

    # Respostas de etapas em andamento são processadas antes de novos comandos.
    if phone in CONVERSATION_STATES:
        result = _continuar_conversa(phone, text)
        if result is not None: return result

    # Opções do submenu da seção atualmente aberta.
    section = MENU_CONTEXTS.get(phone)
    if section and low in ('1', '2', '3', '4'):
        if low == '1':
            if section == 'receita':
                return _consulta_movimentacoes('receita', today)
            if section == 'despesa':
                return _consulta_movimentacoes('despesa', today)
            return _consulta_dividas()
        if low == '2' and section in ('receita', 'despesa'):
            CONVERSATION_STATES[phone] = {
                'flow': 'movimento', 'step': 'descricao_movimento',
                'tipo': section, 'data': {}
            }
            titulo = 'receita' if section == 'receita' else 'despesa'
            return f'Vamos cadastrar uma {titulo}.\n\nQual é a descrição?'

        if section == 'divida' and low == '2':
            CONVERSATION_STATES[phone] = {'flow': 'divida', 'step': 'credor', 'data': {}}
            return 'Vamos cadastrar uma dívida.\n\nQuem é o credor?'
        if section == 'divida' and low in ('3', '4'):
            acao = 'editar' if low == '3' else 'excluir'
            registros = db.listar_dividas()
            titulo = 'DÍVIDAS'
        elif section in ('receita', 'despesa') and low in ('3', '4'):
            acao = 'editar' if low == '3' else 'excluir'
            registros = db.listar_movimentos(section)
            titulo = 'RECEITAS' if section == 'receita' else 'DESPESAS'
        else:
            registros = None
            titulo = ''

        if registros is not None:

            if not registros:
                return 'Não há lançamentos cadastrados.\n\n' + _menu_secao(section)

            linhas = [f'📋 *{titulo} — SELECIONE O LANÇAMENTO*', '━━━━━━━━━━━━━━━━━━']
            for indice, item in enumerate(registros[:15], start=1):
                if section == 'divida':
                    linhas.append(f"{indice}️⃣ *{item['credor']}* — {item['descricao']}\n   Saldo: {money(item['saldo'])}")
                else:
                    linhas.append(f"{indice}️⃣ *{item['descricao']}* — {money(item['valor'])}\n   {_formatar_data(item['data'])}")
            linhas.extend(['', 'Digite o número do lançamento desejado.', '0️⃣ Voltar para ' + titulo.title()])
            CONVERSATION_STATES[phone] = {
                'flow': 'selecao_registro', 'step': 'selecionar_registro',
                'tipo': section, 'acao': acao, 'registros': registros[:15]
            }
            return '\n'.join(linhas)

    # Navegação do menu principal.
    if low in ('oi','olá','ola','menu','ajuda','início','inicio'):
        return _menu_principal()

    opcoes_principais = {
        '1': 'resumo', '2': 'receitas', '3': 'despesas', '4': 'dívidas',
        '5': 'cadastrar_receita', '6': 'cadastrar_despesa',
        '7': 'cadastrar_divida', '8': 'planejamento', '9': 'relatorios',
        '10': 'educacao', '11': 'dicas', '12': 'backup'
    }
    low = opcoes_principais.get(low, low)

    if low in ('resumo','saldo','meu resumo'):
        return _consulta_resumo(today) + "\n\n0️⃣ Voltar ao menu principal"

    if low in ('receitas','despesas','dívidas','dividas','minhas dívidas','minhas dividas'):
        tipo = 'receita' if low == 'receitas' else ('despesa' if low == 'despesas' else 'divida')
        MENU_CONTEXTS[phone] = tipo
        return _menu_secao(tipo)

    if low in ('cadastrar_receita', 'cadastrar_despesa', 'cadastrar_divida'):
        if low == 'cadastrar_divida':
            CONVERSATION_STATES[phone] = {'flow': 'divida', 'step': 'credor', 'data': {}}
            return 'Vamos cadastrar uma dívida.\n\nQuem é o credor?'
        tipo = 'receita' if low == 'cadastrar_receita' else 'despesa'
        MENU_CONTEXTS[phone] = tipo
        CONVERSATION_STATES[phone] = {'flow': 'movimento', 'step': 'descricao_movimento', 'tipo': tipo, 'data': {}}
        return f'Vamos cadastrar uma {tipo}.\n\nQual é a descrição?'

    if low == 'planejamento':
        return _planejamento_financeiro()
    if low == 'relatorios':
        return _relatorio_financeiro()
    if low == 'educacao':
        MENU_CONTEXTS[phone] = 'educacao'
        return _educacao_financeira()
    if low == 'dicas':
        return _dicas_inteligentes()
    if low == 'backup':
        return _executar_backup_whatsapp()

    # Cadastro simples: despesa 890 manutenção do carro / receita 3500 salário.
    m = re.match(r'^(despesa|receita)\s+([\d.,]+)\s+(.+)$', text, re.I)
    if m:
        tipo, raw, desc = m.group(1).casefold(), m.group(2), m.group(3).strip()
        try:
            value=numero_br(raw)
            if value <= 0: raise ValueError()
        except Exception: return 'Valor inválido. Exemplo: *despesa 890 manutenção do carro*.'
        if not desc: return 'Informe a descrição da movimentação.'
        CONVERSATION_STATES[phone]={'flow':'movimento','step':'categoria','tipo':tipo,'data':{'descricao':desc,'valor':value}}
        return f"Qual é a categoria dessa {tipo}?\n\n" + _categorias_texto(tipo)

    # Início de cadastro de dívida, com perguntas em sequência.
    if low in ('dívida','divida','nova dívida','nova divida'):
        CONVERSATION_STATES[phone]={'flow':'divida','step':'credor','data':{}}
        return 'Quem é o credor da dívida?'

    # Pagamento: pagar 12 250,00 ou apenas pagar para iniciar a conversa.
    m = re.match(r'^pagar(?:\s+(\d+))?(?:\s+([\d.,]+))?$', text, re.I)
    if m:
        if not m.group(1):
            CONVERSATION_STATES[phone]={'flow':'pagamento','step':'id_divida','data':{}}
            return 'Qual é o número (ID) da dívida?'
        debt_id=int(m.group(1)); debt=next((x for x in db.listar_dividas() if int(x['id'])==debt_id),None)
        if not debt: return 'Não encontrei essa dívida. Confira o ID e tente novamente.'
        data={'id':debt_id,'credor':debt['credor'],'saldo':float(debt['saldo'])}
        if m.group(2):
            try: value=numero_br(m.group(2))
            except Exception: return 'Valor inválido. Exemplo: *pagar 12 250,00*.'
            if value<=0 or value>data['saldo']+0.00001: return f"Informe um valor entre R$ 0,01 e {money(data['saldo'])}."
            return _iniciar_confirmacao(phone,{'op':'pagar_divida',**data,'valor':value})
        CONVERSATION_STATES[phone]={'flow':'pagamento','step':'pagamento_valor','data':data}
        return f"Qual valor deseja pagar? Saldo atual: {money(data['saldo'])}."

    # Exclusão de dívida: somente quando ainda não há pagamentos vinculados.
    m=re.match(r'^excluir\s+(?:dívida|divida)\s+(\d+)$',text,re.I)
    if m:
        debt_id=int(m.group(1))
        debt=next((x for x in db.listar_dividas() if int(x['id'])==debt_id),None)
        if debt is None: return f'Não encontrei a dívida #{debt_id}.'
        return _iniciar_confirmacao(phone,{'op':'excluir_divida','id':debt_id,'credor':debt['credor'],'descricao':debt['descricao'],'valor':float(debt['valor_total'])})

    # Edição de um único campo por conversa; demais dados permanecem iguais.
    m=re.match(r'^editar\s+(receita|despesa)\s+(\d+)$',text,re.I)
    if m:
        tipo, mid=m.group(1).casefold(),int(m.group(2))
        current=next((x for x in db.listar_movimentos(tipo) if int(x['id'])==mid),None)
        if current is None: return f'Não encontrei o lançamento #{mid}.'
        action={'op':'editar_campo','tipo':tipo,'id':mid,'registro':current,
                'descricao':current['descricao'],'valor':float(current['valor']),'data':current['data'],
                'categoria_id':current['categoria_id'],'campo':'a definir','novo_valor':''}
        CONVERSATION_STATES[phone]={'flow':'edicao','step':'editar_campo','tipo':tipo,'data':{},'action':action}
        return 'O que deseja alterar? Responda: *descrição*, *valor*, *categoria* ou *data*.'

    # Exclusão de receita/despesa por ID.
    m=re.match(r'^excluir\s+(receita|despesa)\s+(\d+)$',text,re.I)
    if m:
        tipo,mid=m.group(1).casefold(),int(m.group(2))
        current=next((x for x in db.listar_movimentos(tipo) if int(x['id'])==mid),None)
        if current is None: return f'Não encontrei o lançamento #{mid}.'
        return _iniciar_confirmacao(phone,{'op':'excluir_movimentacao','tipo':tipo,'id':mid,'descricao':current['descricao'],'valor':float(current['valor'])})

    # Compatibilidade com comandos antigos separados por ponto e vírgula.
    parts=[x.strip() for x in text.split(';')]
    if len(parts)==5 and parts[0].casefold() in ('nova receita','nova despesa'):
        tipo='receita' if parts[0].casefold()=='nova receita' else 'despesa'
        try:
            value=numero_br(parts[2]); d=date.fromisoformat(parts[3]); cid,name=_validar_categoria(tipo,parts[4])
            if not cid: return 'Categoria não encontrada.\n\n'+_categorias_texto(tipo)
            return _iniciar_confirmacao(phone,{'op':'nova_movimentacao','tipo':tipo,'descricao':parts[1],'valor':value,'data':d.isoformat(),'categoria_id':cid,'categoria_nome':name})
        except Exception as exc: return f'Dados inválidos: {exc}'

    return 'Não entendi. Digite *menu* para ver os comandos ou envie, por exemplo: *despesa 890 manutenção do carro*.'

@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "FinConecta API"})

@app.post("/api/whatsapp/command")
@require_auth
def whatsapp_command():
    data = request.get_json(silent=True) or {}
    phone = only_digits(data.get("phone"))
    message = str(data.get("message") or "").strip()
    if not phone or not message:
        return jsonify({"error": "Telefone e mensagem são obrigatórios."}), 400
    if phone not in ALLOWED_PHONES:
        return jsonify({"error": "Este número não está autorizado a acessar o FinConecta."}), 403
    try:
        reply = process_command(phone, message)
        return jsonify({"phone": phone, "reply": reply})
    except (ValueError, TypeError) as exc:
        return jsonify({"phone": phone, "reply": f"Não foi possível concluir: {exc}"}), 200
    except Exception:
        app.logger.exception("Erro ao processar comando WhatsApp")
        return jsonify({"phone": phone, "reply": "Ocorreu um erro interno. Nenhuma confirmação foi gerada; tente novamente mais tarde."}), 500


def _avaliar_alerta_painel():
    """Replica as regras de situação financeira usadas no painel do FinConecta."""
    hoje = date.today()
    receitas, despesas, dividas, pendentes = db.resumo_mes(hoje.year, hoje.month)
    saldo = receitas - despesas
    saldo_atual = receitas - (despesas - pendentes)

    if receitas <= 0 and despesas <= 0:
        nivel = "neutro"
        mensagem = (
            "👋 Ainda não há movimentações suficientes para avaliar seu orçamento. "
            "Registre suas receitas e despesas no FinConecta para acompanhar sua situação financeira."
        )
    elif saldo_atual <= 0:
        nivel = "critico"
        mensagem = (
            "🚨 *Atenção: suas despesas já passaram das receitas.*\n\n"
            f"Até agora, suas despesas pagas somam mais do que suas receitas em *{money(abs(saldo_atual))}*.\n"
            "Confira seus lançamentos, priorize despesas essenciais e evite assumir novos compromissos financeiros."
        )
    elif saldo <= 0:
        nivel = "preventivo"
        mensagem = (
            "⚠️ *Atenção aos pagamentos que ainda faltam.*\n\n"
            f"Depois das contas já pagas, restam *{money(saldo_atual)}*; ainda existem "
            f"*{money(pendentes)}* em despesas pendentes.\n"
            f"Se todas forem pagas, o saldo projetado será *{money(saldo)}*.\n"
            "Confira os vencimentos e evite assumir novas parcelas."
        )
    elif receitas > 0 and saldo <= receitas * 0.20:
        nivel = "preventivo"
        mensagem = (
            "⚠️ *Sua margem para o restante do mês está pequena.*\n\n"
            f"Depois das despesas registradas, sobraram *{money(saldo)}*, "
            "menos de 20% do que você recebeu neste mês.\n"
            "Vale revisar os próximos gastos e evitar comprometer o restante da renda."
        )
    else:
        nivel = "saudavel"
        mensagem = (
            "🟢 *Seu orçamento voltou a uma situação saudável.*\n\n"
            f"Depois das despesas registradas, sobraram *{money(saldo)}* neste mês. "
            "Continue acompanhando as contas que ainda vão vencer."
        )

    return nivel, mensagem, hoje.strftime("%Y-%m")


def _garantir_tabela_alertas():
    with db.conectar() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS whatsapp_alertas_estado (
                phone TEXT PRIMARY KEY,
                last_nivel TEXT,
                last_periodo TEXT,
                pending_nivel TEXT,
                pending_periodo TEXT,
                atualizado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)


@app.get("/api/whatsapp/alerta")
@require_auth
def consultar_alerta_whatsapp():
    """Endpoint consultado periodicamente pelo n8n."""
    _garantir_tabela_alertas()
    phone = next(iter(sorted(ALLOWED_PHONES)), None)
    if not phone:
        return jsonify({"should_send": False, "reason": "Nenhum telefone autorizado."}), 200

    nivel, mensagem, periodo = _avaliar_alerta_painel()

    with db.conectar() as con:
        row = con.execute(
            "SELECT * FROM whatsapp_alertas_estado WHERE phone = ?", (phone,)
        ).fetchone()

        # Situação saudável/neutra atualiza a referência sem gerar mensagem.
        if nivel not in ("preventivo", "critico"):
            con.execute("""
                INSERT INTO whatsapp_alertas_estado
                    (phone, last_nivel, last_periodo, pending_nivel, pending_periodo, atualizado_em)
                VALUES (?, ?, ?, NULL, NULL, CURRENT_TIMESTAMP)
                ON CONFLICT(phone) DO UPDATE SET
                    last_nivel=excluded.last_nivel,
                    last_periodo=excluded.last_periodo,
                    pending_nivel=NULL,
                    pending_periodo=NULL,
                    atualizado_em=CURRENT_TIMESTAMP
            """, (phone, nivel, periodo))
            return jsonify({
                "should_send": False,
                "phone": phone,
                "nivel": nivel,
                "periodo": periodo
            }), 200

        if row and row["last_nivel"] == nivel and row["last_periodo"] == periodo \
                and not row["pending_nivel"]:
            return jsonify({
                "should_send": False,
                "phone": phone,
                "nivel": nivel,
                "periodo": periodo
            }), 200

        # Mantém o alerta pendente até o n8n confirmar o envio.
        con.execute("""
            INSERT INTO whatsapp_alertas_estado
                (phone, pending_nivel, pending_periodo, atualizado_em)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(phone) DO UPDATE SET
                pending_nivel=excluded.pending_nivel,
                pending_periodo=excluded.pending_periodo,
                atualizado_em=CURRENT_TIMESTAMP
        """, (phone, nivel, periodo))

    return jsonify({
        "should_send": True,
        "phone": phone,
        "nivel": nivel,
        "periodo": periodo,
        "message": mensagem
    }), 200


@app.post("/api/whatsapp/alerta/confirmar")
@require_auth
def confirmar_alerta_whatsapp():
    """O n8n chama este endpoint somente depois de a Evolution aceitar o envio."""
    _garantir_tabela_alertas()
    data = request.get_json(silent=True) or {}
    phone = only_digits(data.get("phone"))
    nivel = str(data.get("nivel") or "").strip()
    periodo = str(data.get("periodo") or "").strip()

    if phone not in ALLOWED_PHONES or nivel not in ("preventivo", "critico") or not periodo:
        return jsonify({"ok": False, "error": "Dados de confirmação inválidos."}), 400

    with db.conectar() as con:
        row = con.execute(
            "SELECT pending_nivel, pending_periodo FROM whatsapp_alertas_estado WHERE phone=?",
            (phone,)
        ).fetchone()
        if not row or row["pending_nivel"] != nivel or row["pending_periodo"] != periodo:
            return jsonify({"ok": False, "error": "Não existe alerta pendente correspondente."}), 409

        con.execute("""
            UPDATE whatsapp_alertas_estado
            SET last_nivel=?, last_periodo=?, pending_nivel=NULL,
                pending_periodo=NULL, atualizado_em=CURRENT_TIMESTAMP
            WHERE phone=?
        """, (nivel, periodo, phone))

    return jsonify({"ok": True, "message": "Alerta confirmado como enviado."}), 200


if __name__ == "__main__":
    if not API_TOKEN:
        raise SystemExit("Defina FINCONECTA_API_TOKEN antes de iniciar a API.")
    if not ALLOWED_PHONES:
        raise SystemExit("Defina FINCONECTA_ALLOWED_PHONES com pelo menos um telefone autorizado.")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5001")), debug=False)
