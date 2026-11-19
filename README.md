# FinConecta 2.0

Aplicação individual de educação e organização financeira em Python + CustomTkinter + SQLite.

## Executar no Windows
```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

## Dados
O banco novo fica em `finconecta.db`.

**Migração:** antes de substituir a versão antiga, faça uma cópia de segurança do arquivo `finconecta.db`. Esta versão possui migração incremental para as tabelas existentes, mas como a localização antiga era `FinConecta/finconecta.db`, copie esse arquivo para `finconecta.db` antes da primeira execução para manter seus dados.

## Funcionalidades
- Painel mensal com receitas, despesas, saldo, dívidas, comprometimento e comparação mensal.
- Receitas e despesas com pesquisa, filtro por mês, edição e exclusão.
- Despesas com situação, recorrência, vencimento, forma de pagamento e parcelas.
- Dívidas com parcelas, juros informados, pagamentos e histórico.
- Simulador 50/30/20 com comparação por categorias mapeadas.
- Metas com depósitos e histórico.
- Conteúdo educativo, relatórios e exportação CSV.
- Dicas automáticas baseadas nos lançamentos.

## macOS / Linux
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```
É necessário Python com suporte a Tkinter.

## Testes
```bash
python -m unittest -v
```
Os testes usam um banco temporário. A variável de ambiente `FINCONECTA_DB` permite escolher outro caminho para o banco. O menu Backup permite salvar uma cópia SQLite.
