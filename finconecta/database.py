from pathlib import Path
import sqlite3
import os
from contextlib import contextmanager
from datetime import datetime
from .qualidade import (valor_monetario, texto_obrigatorio, validar_data, tabela_movimento, validar_parcelas, periodo_sql, csv_seguro)
from datetime import date

DB_PATH = Path(os.environ.get("FINCONECTA_DB", str(Path(__file__).resolve().parent.parent / "finconecta.db"))).expanduser().resolve()

@contextmanager
def conectar():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA busy_timeout = 5000")
    try:
        with con:
            yield con
    finally:
        con.close()

def _colunas(con, tabela):
    return {r["name"] for r in con.execute(f"PRAGMA table_info({tabela})")}

def _adicionar_coluna(con, tabela, definicao):
    nome = definicao.split()[0]
    if nome not in _colunas(con, tabela):
        con.execute(f"ALTER TABLE {tabela} ADD COLUMN {definicao}")

def criar_banco():
    if DB_PATH.exists() and DB_PATH.stat().st_size:
        backup_banco()
    with conectar() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS categorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            tipo TEXT NOT NULL CHECK(tipo IN ('receita','despesa')),
            UNIQUE(nome,tipo)
        );
        CREATE TABLE IF NOT EXISTS receitas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            descricao TEXT NOT NULL, valor REAL NOT NULL CHECK(valor>0),
            data TEXT NOT NULL, categoria_id INTEGER, observacao TEXT,
            FOREIGN KEY(categoria_id) REFERENCES categorias(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS despesas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            descricao TEXT NOT NULL, valor REAL NOT NULL CHECK(valor>0),
            data TEXT NOT NULL, categoria_id INTEGER, observacao TEXT,
            FOREIGN KEY(categoria_id) REFERENCES categorias(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS dividas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            credor TEXT NOT NULL, descricao TEXT NOT NULL,
            valor_total REAL NOT NULL CHECK(valor_total>0),
            vencimento TEXT, observacao TEXT
        );
        CREATE TABLE IF NOT EXISTS pagamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            divida_id INTEGER NOT NULL, valor REAL NOT NULL CHECK(valor>0),
            data TEXT NOT NULL, observacao TEXT,
            FOREIGN KEY(divida_id) REFERENCES dividas(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS metas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL, valor_objetivo REAL NOT NULL CHECK(valor_objetivo>0),
            valor_atual REAL NOT NULL DEFAULT 0 CHECK(valor_atual>=0),
            prazo TEXT, observacao TEXT
        );
        CREATE TABLE IF NOT EXISTS depositos_metas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, meta_id INTEGER NOT NULL,
            valor REAL NOT NULL CHECK(valor>0), data TEXT NOT NULL,
            observacao TEXT, FOREIGN KEY(meta_id) REFERENCES metas(id) ON DELETE CASCADE
        );
        """)
        # Migração incremental: preserva as tabelas e lançamentos antigos.
        for tabela in ("receitas", "despesas"):
            _adicionar_coluna(con, tabela, "tipo_recorrencia TEXT NOT NULL DEFAULT 'Variável'")
            _adicionar_coluna(con, tabela, "status TEXT NOT NULL DEFAULT 'Pago'")
            _adicionar_coluna(con, tabela, "vencimento TEXT")
            _adicionar_coluna(con, tabela, "forma_pagamento TEXT")
            _adicionar_coluna(con, tabela, "parcela_atual INTEGER")
            _adicionar_coluna(con, tabela, "total_parcelas INTEGER")
            _adicionar_coluna(con, tabela, "orcamento_grupo TEXT")
        for definicao in (
            "quantidade_parcelas INTEGER", "valor_parcela REAL",
            "juros REAL NOT NULL DEFAULT 0", "parcelas_total INTEGER"
        ):
            _adicionar_coluna(con, "dividas", definicao)
        padrao = [
            ("Salário","receita"),("Renda extra","receita"),("Freelance","receita"),
            ("Comissões","receita"),("Vendas","receita"),("Rendimentos","receita"),
            ("Moradia","despesa"),("Alimentação","despesa"),("Transporte","despesa"),
            ("Saúde","despesa"),("Lazer","despesa"),("Educação","despesa"),
            ("Empréstimos e financiamentos","despesa"),("Cartão de crédito","despesa"),
            ("Contas recorrentes","despesa"),("Investimentos","despesa"),
            ("Reserva de emergência","despesa"),("Compras parceladas","despesa"),
            ("Despesas imprevistas","despesa"),("Internet e telefone","despesa"),
            ("Água e energia","despesa"),("Outros","despesa")
        ]
        con.executemany("INSERT OR IGNORE INTO categorias(nome,tipo) VALUES(?,?)", padrao)
        # Recria índice sem alterar dados existentes.
        con.execute("CREATE INDEX IF NOT EXISTS idx_receitas_data ON receitas(data)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_despesas_data ON despesas(data)")

def listar_categorias(tipo):
    with conectar() as con:
        return con.execute("SELECT id,nome FROM categorias WHERE tipo=? ORDER BY nome",(tipo,)).fetchall()

def adicionar_categoria(tipo,nome):
    nome=texto_obrigatorio(nome)
    if tipo not in ("receita","despesa") or not nome: raise ValueError("Informe uma categoria válida.")
    with conectar() as con:
        try: con.execute("INSERT INTO categorias(nome,tipo) VALUES(?,?)",(nome,tipo))
        except sqlite3.IntegrityError: raise ValueError("Essa categoria já existe.")

def inserir_movimento(tipo, descricao, valor, data, categoria_id, observacao="", recorrencia="Variável",
                      status="Pago", vencimento=None, forma_pagamento="", parcela_atual=None,
                      total_parcelas=None):
    validar_movimento(descricao, valor, data, vencimento, recorrencia, status, parcela_atual, total_parcelas)
    tabela = tabela_movimento(tipo)
    with conectar() as con:
        con.execute(f"""INSERT INTO {tabela}
        (descricao,valor,data,categoria_id,observacao,tipo_recorrencia,status,vencimento,
         forma_pagamento,parcela_atual,total_parcelas)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (descricao,valor,data,categoria_id,observacao,recorrencia,status,vencimento or None,
         forma_pagamento or None,parcela_atual,total_parcelas))

def listar_movimentos(tipo, mes=None, ano=None, busca="", categoria_id=None):
    tabela = tabela_movimento(tipo)
    where=[]; args=[]
    if mes and ano: where.append("m.data>=? AND m.data<?"); args.extend(periodo_sql(ano,mes))
    if busca: where.append("m.descricao LIKE ?"); args.append(f"%{busca}%")
    if categoria_id: where.append("m.categoria_id=?"); args.append(categoria_id)
    sql=f"""SELECT m.*,COALESCE(c.nome,'Sem categoria') categoria
        FROM {tabela} m LEFT JOIN categorias c ON c.id=m.categoria_id"""
    if where: sql+=" WHERE "+" AND ".join(where)
    sql+=" ORDER BY m.data DESC,m.id DESC"
    with conectar() as con: return con.execute(sql,args).fetchall()

def salvar_edicao_movimento(tipo, mid, descricao, valor, data, categoria_id, observacao,
                            recorrencia, status, vencimento, forma, parcela, total):
    validar_movimento(descricao, valor, data, vencimento, recorrencia, status, parcela, total)
    tabela=tabela_movimento(tipo)
    with conectar() as con:
        con.execute(f"""UPDATE {tabela} SET descricao=?,valor=?,data=?,categoria_id=?,observacao=?,
        tipo_recorrencia=?,status=?,vencimento=?,forma_pagamento=?,parcela_atual=?,total_parcelas=?
        WHERE id=?""",(descricao,valor,data,categoria_id,observacao,recorrencia,status,
        vencimento or None,forma or None,parcela,total,mid))

def excluir_movimento(tipo, mid):
    tabela=tabela_movimento(tipo)
    with conectar() as con: con.execute(f"DELETE FROM {tabela} WHERE id=?",(mid,))

def resumo_mes(ano,mes):
    inicio=periodo_sql(ano,mes)
    with conectar() as con:
        r=con.execute("SELECT COALESCE(SUM(valor),0) FROM receitas WHERE data>=? AND data<?",inicio).fetchone()[0]
        d=con.execute("SELECT COALESCE(SUM(valor),0) FROM despesas WHERE data>=? AND data<?",inicio).fetchone()[0]
        div=con.execute("""SELECT COALESCE(SUM(saldo),0) FROM (
            SELECT d.valor_total-COALESCE(SUM(p.valor),0) saldo FROM dividas d
            LEFT JOIN pagamentos p ON p.divida_id=d.id GROUP BY d.id)""").fetchone()[0]
        pend=con.execute("SELECT COALESCE(SUM(valor),0) FROM despesas WHERE data>=? AND data<? AND status='Pendente'",inicio).fetchone()[0]
    return float(r),float(d),float(div),float(pend)

def resumo():
    with conectar() as con:
        r=con.execute("SELECT COALESCE(SUM(valor),0) FROM receitas").fetchone()[0]
        d=con.execute("SELECT COALESCE(SUM(valor),0) FROM despesas").fetchone()[0]
        div=con.execute("""SELECT COALESCE(SUM(saldo),0) FROM (
            SELECT d.valor_total-COALESCE(SUM(p.valor),0) saldo FROM dividas d
            LEFT JOIN pagamentos p ON p.divida_id=d.id GROUP BY d.id)""").fetchone()[0]
    return float(r),float(d),float(div)

def totais_categoria(ano,mes):
    with conectar() as con:
        return con.execute("""SELECT COALESCE(c.nome,'Sem categoria') categoria,SUM(d.valor) total
        FROM despesas d LEFT JOIN categorias c ON c.id=d.categoria_id
        WHERE d.data>=? AND d.data<? GROUP BY d.categoria_id ORDER BY total DESC""",
        periodo_sql(ano,mes)).fetchall()

def inserir_divida(credor,descricao,valor,vencimento,observacao="",parcelas=None,valor_parcela=None,juros=0):
    texto_obrigatorio(credor); texto_obrigatorio(descricao); valor_monetario(valor)
    validar_data(vencimento, True); validar_parcelas(None, parcelas)
    if valor_parcela is not None: valor_monetario(valor_parcela)
    valor_monetario(juros, True)
    with conectar() as con:
        con.execute("""INSERT INTO dividas(credor,descricao,valor_total,vencimento,observacao,
        quantidade_parcelas,valor_parcela,juros,parcelas_total) VALUES(?,?,?,?,?,?,?,?,?)""",
        (credor,descricao,valor,vencimento or None,observacao,parcelas,valor_parcela,juros,parcelas))

def listar_dividas():
    with conectar() as con:
        return con.execute("""SELECT d.*,COALESCE(SUM(p.valor),0) pago,
        MAX(d.valor_total-COALESCE(SUM(p.valor),0),0) saldo
        FROM dividas d LEFT JOIN pagamentos p ON p.divida_id=d.id
        GROUP BY d.id ORDER BY d.vencimento IS NULL,d.vencimento""").fetchall()

def registrar_pagamento(divida_id,valor,data,observacao=""):
    valor = valor_monetario(valor); validar_data(data)
    with conectar() as con:
        con.execute("BEGIN IMMEDIATE")
        row=con.execute("""SELECT d.valor_total-COALESCE(SUM(p.valor),0) saldo FROM dividas d
        LEFT JOIN pagamentos p ON p.divida_id=d.id WHERE d.id=? GROUP BY d.id""",(divida_id,)).fetchone()
        if row is None: raise ValueError("Dívida não encontrada.")
        if valor<=0 or valor>row["saldo"]+0.00001: raise ValueError("Confira o valor do pagamento e o saldo restante.")
        con.execute("INSERT INTO pagamentos(divida_id,valor,data,observacao) VALUES(?,?,?,?)",
                    (divida_id,valor,data,observacao))

def historico_pagamentos(divida_id):
    with conectar() as con:
        return con.execute("SELECT * FROM pagamentos WHERE divida_id=? ORDER BY data DESC,id DESC",(divida_id,)).fetchall()

def inserir_meta(nome,objetivo,atual,prazo,observacao=""):
    texto_obrigatorio(nome); valor_monetario(objetivo); valor_monetario(atual, True); validar_data(prazo, True)
    if atual > objetivo: raise ValueError("Saldo inicial ultrapassa o objetivo.")
    with conectar() as con:
        cur=con.execute("INSERT INTO metas(nome,valor_objetivo,valor_atual,prazo,observacao) VALUES(?,?,?,?,?)",
                        (nome,objetivo,atual,prazo or None,observacao))
        mid=cur.lastrowid
        if atual>0: con.execute("INSERT INTO depositos_metas(meta_id,valor,data,observacao) VALUES(?,?,?,?)",
                                 (mid,atual,date.today().isoformat(),"Saldo inicial"))

def listar_metas():
    with conectar() as con: return con.execute("SELECT * FROM metas ORDER BY id DESC").fetchall()

def adicionar_a_meta(meta_id,valor,data=None,observacao=""):
    valor = valor_monetario(valor); validar_data(data, True)
    with conectar() as con:
        con.execute("BEGIN IMMEDIATE")
        m=con.execute("SELECT * FROM metas WHERE id=?",(meta_id,)).fetchone()
        if not m: raise ValueError("Meta não encontrada.")
        if m["valor_atual"]+valor>m["valor_objetivo"]+0.00001: raise ValueError("O depósito ultrapassa o objetivo.")
        con.execute("INSERT INTO depositos_metas(meta_id,valor,data,observacao) VALUES(?,?,?,?)",
                    (meta_id,valor,data or date.today().isoformat(),observacao))
        con.execute("UPDATE metas SET valor_atual=ROUND(valor_atual+?,2) WHERE id=?",(valor,meta_id))

def historico_meta(meta_id):
    with conectar() as con: return con.execute("SELECT * FROM depositos_metas WHERE meta_id=? ORDER BY data DESC,id DESC",(meta_id,)).fetchall()

def exportar_csv(caminho,ano,mes):
    import csv
    with conectar() as con, open(caminho,"w",newline="",encoding="utf-8-sig") as f:
        w=csv.writer(f,delimiter=";")
        w.writerow(["Tipo","Descrição","Valor","Data","Categoria","Situação","Observação"])
        for tipo in ("receita","despesa"):
            tabela=tabela_movimento(tipo)
            rows=con.execute(f"""SELECT m.*,COALESCE(c.nome,'Sem categoria') categoria FROM {tabela} m
            LEFT JOIN categorias c ON c.id=m.categoria_id WHERE m.data>=? AND m.data<? ORDER BY m.data""",
            periodo_sql(ano,mes)).fetchall()
            for r in rows: w.writerow([tipo,csv_seguro(r["descricao"]),f'{r["valor"]:.2f}',r["data"],csv_seguro(r["categoria"]),csv_seguro(r["status"]),csv_seguro(r["observacao"])])


def validar_movimento(descricao, valor, data, vencimento, recorrencia, status, atual, total):
    texto_obrigatorio(descricao); valor_monetario(valor); validar_data(data); validar_data(vencimento, True)
    validar_parcelas(atual, total)
    if recorrencia not in ("Fixa", "Variável") or status not in ("Pago", "Pendente"):
        raise ValueError("Situação ou recorrência inválida.")


def backup_banco(destino=None):
    """Cópia consistente do SQLite, sem copiar um banco em uso diretamente."""
    if not DB_PATH.exists(): raise ValueError("Banco ainda não criado.")
    destino = Path(destino) if destino else DB_PATH.parent / "backups" / f"finconecta_{datetime.now():%Y%m%d_%H%M%S_%f}.db"
    if destino.resolve() == DB_PATH.resolve() or destino.exists():
        raise ValueError("Escolha um arquivo de backup novo, diferente do banco original.")
    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        with conectar() as origem:
            copia = sqlite3.connect(destino)
            try:
                origem.backup(copia)
                if copia.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Falha na verificação do backup.")
            finally:
                copia.close()
    except Exception:
        destino.unlink(missing_ok=True)
        raise
    return destino
