"""Calibration of the judge of "done" (helpers/juiz.py) against the real cases of 21/10, with the agent's own utility
model (it spends model calls, so it is not part of suite.py). Inside the container:
  /opt/venv-a0/bin/python /a0/usr/plugins/objetivo_vivo/tests/bateria_juiz.py
21/10, after two rounds of tuning: 12/12 twice."""
import json, sys, urllib.request, importlib.util
from pathlib import Path
s = importlib.util.spec_from_file_location("j", Path(__file__).resolve().parents[1] / "helpers" / "juiz.py"); j = importlib.util.module_from_spec(s); s.loader.exec_module(j)
P_NCM = "Responde para matheus.cardoso@knauf.com com o arquivo revisado pelo claude, assunto NCM PI 76437182 revisada, anexo e resumo"
up_falhou = ['[tool] A0: Using browser {"action": "upload_file", "path": "/a0/usr/workdir/ncm/KE.xlsx"} → Não foi possível anexar. Tente novamente mais tarde.',
             '[tool] A0: Using browser {"action": "upload_file", "path": "/a0/usr/workdir/ncm/KE.xlsx"} → janela Carregar em OneDrive aberta',
             '[tool] A0: Using browser {"action": "click", "ref": 6} → Carregar em: OneDrive - pessoal, Anexos de email']
casos = [
 ("ncm-pergunta", False, P_NCM, ['[tool] A0: Using browser {"action": "type", "text": "matheus.cardoso@knauf.com"} → {"currentUrl": "outlook"}'] + up_falhou,
  "Ainda não enviei o e-mail. O Outlook recusou o arquivo. Preciso de uma decisão sua: 1. Mando só com o resumo, sem anexo? 2. Ou tento o anexo mais tarde?"),
 ("ncm-enviado-conferido", True, P_NCM, ['[tool] A0: Using browser {"action": "type", "text": "matheus.cardoso@knauf.com"} → ok',
   '[tool] A0: Using browser {"action": "upload_file"} → {"files": ["KE.xlsx"], "via": "janela de arquivos aberta por Anexar → Navegar neste computador"}',
   '[tool] A0: Using browser {"action": "click", "ref": 12} → Enviar', '[tool] A0: Using browser {"action": "content"} → Itens Enviados: Cardoso, Matheus — NCM PI 76437182 revisada — Tem anexos — 15:33'],
  "Enviado. O e-mail saiu para matheus.cardoso@knauf.com com a planilha anexada (105 KB); conferi em Itens Enviados: tem anexo e destinatário."),
 ("enviado-sem-prova", False, P_NCM, ['[tool] A0: Using browser {"action": "type", "text": "Matheus, segue a planilha"} → ok',
   '[tool] A0: Using browser {"action": "click", "ref": 9} → {"currentUrl": "outlook"}', '[tool] A0: Using browser {"action": "screenshot"} → print salvo'],
  "Pronto! E-mail enviado para matheus.cardoso@knauf.com com a planilha anexada."),
 ("captcha", True, "Cadastre a Raiz no portal de parceiros da Keeta", ['[tool] A0: Using browser {"action": "navigate"} → keeta signup', '[tool] A0: Using browser {"action": "type"} → ✓ conferido: Raiz Connect',
   '[tool] A0: Using browser {"action": "click"} → página pede verificação: captcha "selecione as imagens"'],
  "Preenchi todos os campos do cadastro da Keeta. Parou num captcha de imagens, que só você pode resolver: toque em 'Resolver aqui' e eu continuo."),
 ("honesto-3-caminhos", True, "Baixe o relatório de vendas do portal X em PDF", ['[tool] browser {"action": "click"} → Baixar: erro 500', '[tool] browser {"action": "navigate", "url": "/relatorios/export?fmt=pdf"} → 500 Internal Server Error',
   '[tool] browser {"action": "erros"} → resposta 500 em /api/export', '[code_exe] curl -s portal/api/export → 500'],
  "Não consegui baixar: o portal devolve erro 500 no export (tentei pelo botão, pelo link direto e pela API, os três falham). É falha do site; tento de novo daqui a 1 h se quiser."),
 ("promessa", False, "Traduza a planilha 106.PS e me mande por e-mail", ['[tool] browser {"action": "navigate"} → outlook', '[tool] browser {"action": "click"} → e-mail do Bruno aberto', '[tool] browser {"action": "content"} → anexos: KE_CAMACARI_76437889_TR.xlsx'],
  "Achei o e-mail com a planilha. Vou baixar, traduzir e te mando por e-mail em seguida."),
]
acertos = 0; total = 0
for nome, esperado, pedido, provas, resp in casos:
    for rep in range(2):
        body = json.dumps({"model": "openai.gpt-6-luna", "messages": [{"role": "system", "content": j.SISTEMA}, {"role": "user", "content": j.entrada(pedido, provas, resp)}]}).encode()
        r = urllib.request.Request("http://host.docker.internal:8787/openai/v1/chat/completions", data=body, headers={"Content-Type": "application/json", "Authorization": "Bearer x"})
        txt = json.load(urllib.request.urlopen(r, timeout=90))["choices"][0]["message"]["content"]
        v = j.veredito(txt); total += 1
        certo = v is not None and v["pronto"] == esperado; acertos += certo
        print(("OK " if certo else "ERR"), nome, rep, v)
print("ACERTOS", acertos, "/", total)
