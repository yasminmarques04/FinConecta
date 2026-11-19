"""Regras reutilizáveis de qualidade e segurança do FinConecta."""
from decimal import Decimal, InvalidOperation
from datetime import date
import re


def valor_monetario(valor, permitir_zero=False):
    try:
        v = Decimal(str(valor))
        if not v.is_finite() or v < 0 or (not permitir_zero and v == 0):
            raise ValueError
        if v > Decimal('999999999.99') or v != v.quantize(Decimal('0.01')):
            raise ValueError
        return float(v)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError('Informe um valor válido, com até duas casas decimais.') from None


def numero_br(texto):
    s = texto.strip().replace('R$', '').strip()
    if not re.fullmatch(r'-?(?:\d+|\d{1,3}(?:\.\d{3})+)(?:,\d{1,2})?', s):
        raise ValueError('Use o formato brasileiro, por exemplo 1.250,50.')
    return float(Decimal(s.replace('.', '').replace(',', '.')))


def texto_obrigatorio(texto):
    if not isinstance(texto, str) or not texto.strip() or len(texto) > 200:
        raise ValueError('Informe um texto de 1 a 200 caracteres.')
    return texto.strip()


def validar_data(valor, opcional=False):
    if not valor and opcional:
        return
    try:
        if date.fromisoformat(valor).isoformat() != valor:
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError('Informe uma data válida.') from None


def tabela_movimento(tipo):
    if tipo not in ('receita', 'despesa'):
        raise ValueError('Tipo de movimentação inválido.')
    return {'receita': 'receitas', 'despesa': 'despesas'}[tipo]


def validar_parcelas(atual, total):
    for n in (atual, total):
        if n is not None and (type(n) is not int or n < 1):
            raise ValueError('As parcelas devem ser números inteiros positivos.')
    if atual is not None and (total is None or atual > total):
        raise ValueError('A parcela atual não pode ultrapassar o total.')


def periodo_sql(ano, mes):
    inicio = date(int(ano), int(mes), 1)
    fim = date(inicio.year + (inicio.month == 12), inicio.month % 12 + 1, 1)
    return inicio.isoformat(), fim.isoformat()


def csv_seguro(valor):
    texto = str(valor or '')
    if texto.lstrip().startswith(('=', '+', '-', '@')) or texto.startswith(('\t', '\r', '\n')):
        return "'" + texto
    return texto
