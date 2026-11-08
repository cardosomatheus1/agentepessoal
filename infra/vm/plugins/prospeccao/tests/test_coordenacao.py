import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
c=load('coordenacao_test',ROOT/'helpers/coordenacao.py')
class CoordinationTests(unittest.TestCase):
 def setUp(self):
  self.lead={'id':'test01','nome':'Padaria Teste','handle':'padariateste','etapa':'novo','cidade':'Salvador','segmento':'padaria','nota':83}
 def test_missing_config_never_authorizes(self):
  with patch.dict(os.environ,{'RAIZ_CRM_URL':'','PROSPECTING_BRIDGE_TOKEN':''}):
   with self.assertRaises(c.CoordenacaoIndisponivel):c.permitir(self.lead)
 def test_reserved_lead_never_gets_claimed(self):
  with patch.object(c,'_pedir',return_value={'leads':[{'blocked':True,'leadId':'id'}]}) as request:
   self.assertEqual(c.permitir(self.lead)[0],False);self.assertEqual(request.call_count,1)
 def test_allowed_action_claims_central_ownership(self):
  with patch.object(c,'_pedir',side_effect=[{'leads':[{'blocked':False,'leadId':'lead-id'}]},{'allowed':True}]) as request:
   self.assertEqual(c.permitir(self.lead),(True,''));self.assertEqual(request.call_args.args,('claim',{'leadId':'lead-id'}))
 def test_incomplete_answer_is_closed(self):
  with patch.object(c,'_pedir',return_value={'leads':[]}):self.assertFalse(c.permitir(self.lead)[0])
 def test_optout_and_score_are_preserved(self):
  self.lead.update(etapa='descartado',historico=[{'tipo':'etapa:descartado','texto':'Não quer contato'}])
  row=c.registro(self.lead);self.assertEqual(row['state'],'OPT_OUT');self.assertEqual(row['score'],83)
 def test_preapproved_action_is_not_handed_out_after_partner_reserves(self):
  import tempfile
  from datetime import datetime
  p=load('prospecting_boundary',ROOT/'helpers/prospeccao.py')
  with tempfile.TemporaryDirectory() as tmp:
   p.PASTA=Path(tmp);p.agora=lambda:datetime(2026,11,9,16,tzinfo=p._tz()).timestamp()
   p.definir_conta('teste_boundary','raiz.connect')
   d=p.carregar('teste_boundary');d['config']['exigir_conferencia']=False;d['config']['executar_em_teste']=True
   d['leads']=[{**self.lead,'historico':[],'criado':p.agora()}]
   d['acoes']=[{'id':'test_action','lead_id':self.lead['id'],'tipo':'dm_abertura','estado':'aprovada','decidida':0,'texto':'teste'}]
   p.salvar('teste_boundary',d)
   p._commercial_permit=lambda lead:(False,'reservado por parceiro')
   action,reason=p.proxima('teste_boundary','raiz.connect',repor=False)
   self.assertIsNone(action);self.assertIn('reservado',reason)
   self.assertFalse(p.carregar('teste_boundary')['acoes'][0].get('em_execucao'))
if __name__=='__main__':unittest.main()
