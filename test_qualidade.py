import tempfile
import unittest
from pathlib import Path
from finconecta import database as db
from finconecta.qualidade import numero_br, csv_seguro

class TestFinConecta(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original = db.DB_PATH
        db.DB_PATH = Path(self.tmp.name) / 'teste.db'
        db.criar_banco()
    def tearDown(self):
        db.DB_PATH = self.original
        self.tmp.cleanup()
    def test_movimentos(self):
        db.inserir_movimento('receita','Salário',1000,'2027-01-01',None)
        db.inserir_movimento('despesa','Conta',200,'2027-01-31',None)
        self.assertEqual(db.resumo_mes(2027,1)[:2],(1000,200))
        self.assertEqual(db.resumo_mes(2027,2)[:2],(0,0))
        for valor in (-1,0,float('nan'),1.234):
            with self.assertRaises(ValueError): db.inserir_movimento('despesa','Conta',valor,'2027-01-01',None)
    def test_pagamento(self):
        db.inserir_divida('Banco','Teste',100,None)
        mid=db.listar_dividas()[0]['id']
        db.registrar_pagamento(mid,40,'2027-01-01')
        with self.assertRaises(ValueError): db.registrar_pagamento(mid,61,'2027-01-01')
        self.assertEqual(db.listar_dividas()[0]['saldo'],60)
    def test_meta(self):
        db.inserir_meta('Reserva',100,20,None)
        mid=db.listar_metas()[0]['id']
        db.adicionar_a_meta(mid,30)
        with self.assertRaises(ValueError): db.adicionar_a_meta(mid,51)
        self.assertEqual(db.listar_metas()[0]['valor_atual'],50)
    def test_backup_csv(self):
        db.inserir_movimento('receita','=1+1',10,'2027-01-01',None)
        self.assertTrue(db.backup_banco().exists())
        p=Path(self.tmp.name)/'teste.csv'
        db.exportar_csv(p,2027,1)
        self.assertIn("'=1+1",p.read_text(encoding='utf-8-sig'))
        with self.assertRaises(ValueError): db.listar_movimentos('receitas; DROP TABLE receitas')
    def test_formato(self):
        self.assertEqual(numero_br('1.250,50'),1250.50)
        with self.assertRaises(ValueError): numero_br('abc')

if __name__ == '__main__': unittest.main()
