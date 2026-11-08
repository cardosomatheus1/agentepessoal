import importlib.util
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
p=load('rubrica_restaurantes',ROOT/'helpers/prospeccao.py')
f=load('fontes_restaurantes',ROOT/'helpers/fontes.py')
class RestaurantesTests(unittest.TestCase):
 def test_especialidades_usam_a_rubrica_restaurante_sem_peso_novo(self):
  for value in ['restaurante','pizzaria','hamburgueria','lanchonete','churrascaria','bistrô','bar','cafeteria','sorveteria','açaí']:
   with self.subTest(value=value):self.assertEqual(p.segmento_rubrica(value),'restaurante')
  self.assertEqual(p.PONTOS_SEGMENTO['restaurante'],15)
 def test_diretorio_e_rotacao_social_incluem_atendimento(self):
  self.assertEqual(dict(f.CNAES)['5611201'],'restaurante');self.assertEqual(dict(f.CNAES)['5611203'],'restaurante')
  for word in ['restaurante','pizzaria','hamburgueria','lanchonete','churrascaria']:self.assertIn(word,f.PALAVRAS_INSTAGRAM)
 def test_directory_does_not_discard_food_service_by_name(self):
  for name in ['BAR DO ZE','LANCHONETE DA ANA','PIZZARIA BOA','HAMBURGUERIA CENTRAL','BURGER DO BAIRRO','CHURRASCARIA A BRASA','PASTELARIA NOVA','BOTECO DA VILA']:
   with self.subTest(name=name):self.assertIsNone(f.FORA.search(name))
  for name in ['MERCADINHO CENTRAL','MERCEARIA DA ANA','DISTRIBUIDORA DE BEBIDAS']:
   with self.subTest(name=name):self.assertIsNotNone(f.FORA.search(name))
if __name__=='__main__':unittest.main()
