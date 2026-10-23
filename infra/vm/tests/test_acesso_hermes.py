"""Tests of what each Hermes conversation may do (infra/vm/hermes/plugins/agentepessoal, 23/10 migration, phase 2):
- uso_hermes: every model call of a session carries its owner, session and routine id in X-A0-* headers (only on the
  SDKs that take extra_headers);
- acesso_hermes: a guest gets only the personal-use tools (never terminal/execute_code/files/memory/browser) and only
  their own files; in the rehearsal the browser only reads and code never talks to the browser by CDP;
- aprovacoes_hermes: the same reviewer and rules of Agent Zero: never = block, ask = Hermes approval gate with an exact
  rule key, allow = through; the Instagram message is let through and announced; the leak guard blocks a CPF in a
  message; "Nesta tarefa" (session) and "Sempre permitir" (always) work as on the A0.
Run from the repository root: python3 infra/vm/tests/test_acesso_hermes.py"""
import importlib.util
import json
import os
import sys
import tempfile
import types
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
P = RAIZ / "infra" / "vm" / "hermes" / "plugins" / "agentepessoal"
PLUGINS = RAIZ / "infra" / "vm" / "plugins"
falhas = []


def checa(cond, msg):
    if not cond:
        falhas.append(msg)


def carregar(nome, caminho):
    spec = importlib.util.spec_from_file_location(nome, caminho)
    m = importlib.util.module_from_spec(spec)
    sys.modules[nome] = m
    spec.loader.exec_module(m)
    return m


tmp = Path(tempfile.mkdtemp())
ponte = carregar("agentepessoal_ponte_a0", P / "ponte_a0.py")
ponte.PLUGINS = PLUGINS
ponte.SESSOES = tmp / "sessoes.json"
ponte.SESSOES.write_text('{"s-ilia": "ilia", "s-m": "matheus", "cron_*": "matheus"}')

# --- uso_hermes
uso = carregar("teste_uso_hermes", P / "uso_hermes.py")
r = uso.pedido_com_dono({"messages": [], "extra_headers": {"anthropic-beta": "x"}}, session_id="s-ilia",
                        api_mode="anthropic_messages")
checa(r and r["request"]["extra_headers"] == {"anthropic-beta": "x", "X-A0-Dono": "ilia", "X-A0-Conversa": "s-ilia"},
      f"dono e sessão nos cabeçalhos, sem perder os que já havia: {r}")
r = uso.pedido_com_dono({"messages": []}, session_id="cron_ab12cd34ef56_20261023_081700", api_mode="anthropic_messages")
checa(r["request"]["extra_headers"].get("X-A0-Rotina") == "ab12cd34ef56" and r["request"]["extra_headers"]["X-A0-Dono"] == "matheus",
      f"rodada do cron: id da rotina e o dono ({r})")
checa(uso.pedido_com_dono({"messages": []}, session_id="s-m", api_mode="bedrock_converse") is None,
      "no Converse do boto3 nada muda (extra_headers quebraria a chamada)")
checa(uso.cabecalhos("sessão com espaço")["X-A0-Dono"] == "matheus" and "X-A0-Conversa" not in uso.cabecalhos("a b"),
      "id torto não vira cabeçalho")

# --- acesso_hermes
ac = carregar("teste_acesso_hermes", P / "acesso_hermes.py")
ac.PLUGINS = PLUGINS
os.environ.pop("AGENTEPESSOAL_ENSAIO", None)
bloq = lambda **kw: (ac.checar(**kw) or {}).get("action") == "block"  # noqa: E731
for ferramenta in ("terminal", "execute_code", "read_file", "write_file", "patch", "search_files", "memory",
                   "session_search", "skill_view", "cronjob_manage", "delegate_task", "browser_navigate", "prospeccao",
                   "cerebro", "conteudo", "mcp_google_gmail_search", "manage_connections", "image_generate"):
    checa(bloq(tool_name=ferramenta, args={}, session_id="s-ilia"), f"convidado sem {ferramenta}")
for ferramenta in ("web_search", "terminal_isolado", "lembrar", "ficha", "cofre_descrever", "vision_analyze"):
    checa(not bloq(tool_name=ferramenta, args={"q": "x"}, session_id="s-ilia"), f"convidado com {ferramenta}")
checa(bloq(tool_name="whatsapp_enviar", args={"arquivo": "/a0/usr/prospeccao/matheus.json"}, session_id="s-ilia"),
      "convidado não manda arquivo do Matheus")
checa(not bloq(tool_name="whatsapp_enviar", args={"arquivo": "/a0/usr/whatsapp/ilia/foto.jpg"}, session_id="s-ilia"),
      "convidado manda o arquivo que ele mesmo enviou")
for ferramenta in ("terminal", "read_file", "browser_click", "prospeccao"):
    checa(not bloq(tool_name=ferramenta, args={"command": "ls"}, session_id="s-m"), f"o Matheus usa {ferramenta} (fora do ensaio)")
checa(not bloq(tool_name="terminal", args={"command": "ls"}, session_id="nao-mapeada"), "sessão sem dono = do Matheus")
os.environ["AGENTEPESSOAL_ENSAIO"] = "1"
for ferramenta in ("browser_click", "browser_type", "browser_press", "browser_console", "browser_cdp", "browser_exec",
                   "browser_dialog", "browser_vault"):
    checa(bloq(tool_name=ferramenta, args={"ref": "@e1"}, session_id="s-m"), f"ensaio: {ferramenta} bloqueado")
for ferramenta in ac.NAVEGADOR_SO_LE:
    checa(not bloq(tool_name=ferramenta, args={"url": "https://www.instagram.com/direct/inbox/"}, session_id="s-m"),
          f"ensaio: {ferramenta} só lê e passa")
for codigo in ("curl http://navegador-hermes:9222/json", "python3 -c 'from playwright.sync_api import sync_playwright'",
               "websocat ws://172.18.0.5:9222/devtools/browser/x"):
    checa(bloq(tool_name="terminal", args={"command": codigo}, session_id="s-m"), f"ensaio: código não fala com o navegador: {codigo}")
checa(not bloq(tool_name="terminal", args={"command": "ls /a0/usr/prospeccao"}, session_id="s-m"), "ensaio: terminal comum segue")
# ensaio: abrir uma conversa da caixa do Direct (cada uma é um botão, sem link) passa; o resto não
ap0 = carregar("agentepessoal_aprovacoes", P / "aprovacoes_hermes.py")
caixa = ('- button "user-profile-picture Mais Congelados You: Oi! Sou o Matheus  12 hours ago" [ref=e28]\n'
         '- button "Send message" [ref=e30]\n- tab "Primary" [ref=e31]\n'
         '- button "user-profile-picture Fulano Follow" [ref=e32]')
ap0.ver_pagina(tool_name="browser_navigate", args={"url": "https://www.instagram.com/direct/inbox/"},
               result=json.dumps({"success": True, "url": "https://www.instagram.com/direct/inbox/"}), session_id="s-d")
ap0.ver_pagina(tool_name="browser_snapshot", args={}, result=json.dumps({"snapshot": caixa}), session_id="s-d")
checa(not bloq(tool_name="browser_click", args={"ref": "@e28"}, session_id="s-d"), "ensaio: abrir a conversa do Direct passa")
checa(not bloq(tool_name="browser_click", args={"ref": "e31"}, session_id="s-d"), "ensaio: a aba Principal passa")
for ref in ("@e30", "@e32", "@e99"):
    checa(bloq(tool_name="browser_click", args={"ref": ref}, session_id="s-d"), f"ensaio: clique {ref} (ação ou desconhecido) bloqueado")
ap0.ver_pagina(tool_name="browser_navigate", args={"url": "https://www.instagram.com/fulano/"}, result="{}", session_id="s-d")
checa(bloq(tool_name="browser_click", args={"ref": "@e28"}, session_id="s-d"), "ensaio: fora do /direct nenhum clique passa")
checa(bloq(tool_name="browser_click", args={"ref": "@e28"}, session_id="outra-sessao"), "ensaio: sessão sem leitura da página: bloqueado")
os.environ.pop("AGENTEPESSOAL_ENSAIO")

# --- aprovacoes_hermes
ap = carregar("teste_aprovacoes_hermes", P / "aprovacoes_hermes.py")
ap.PLUGINS = PLUGINS
ap.DADOS = tmp / "dados"
ap.SEMPRE = ap.DADOS / "sempre.txt"
rv = ap.revisor()
rv.COFRE = str(tmp / "segredos")
classes = []
proxima = {}


def classificar(tool, args, intencao, sempre):
    classes.append((tool, args, intencao, sempre))
    return dict(proxima)


rv.classificar = classificar
avisos = []
wa = types.ModuleType("whatsapp_ponte")
wa.enviar = lambda login, texto, *a, **k: avisos.append((login, texto)) or ""
wa._mtime = (PLUGINS / "whatsapp" / "helpers" / "ponte.py").stat().st_mtime
sys.modules["whatsapp_ponte"] = wa
snap = '- textbox "Mensagem" [ref=e3]\n- button "Enviar" [ref=e12]\n- link "Perfil" [ref=e14]'
ap.ver_pagina(tool_name="browser_navigate", args={"url": "https://www.instagram.com/direct/t/1/"}, result='{"ok": true}',
              session_id="s-m")
# como o Hermes devolve (JSON com o texto da página dentro; revisão OpenCode 23/10: o texto cru não aparecia)
ap.ver_pagina(tool_name="browser_snapshot", args={}, result=json.dumps({"success": True, "snapshot": "- generic:\n  " + snap.replace("\n", "\n  "),
                                                                       "element_count": 3}), session_id="s-m")
checa(ap.intencao("browser_click", {"ref": "@e12"}, "s-m") == 'click no elemento button "Enviar" na página https://www.instagram.com/direct/t/1/',
      f"intenção do clique pelo rótulo: {ap.intencao('browser_click', {'ref': '@e12'}, 's-m')}")
checa(ap.checar(tool_name="browser_snapshot", args={}, session_id="s-m") is None and not classes, "ler a página não passa pelo revisor")
checa(ap.checar(tool_name="browser_click", args={"ref": "@e14"}, session_id="s-m") is None and not classes,
      "clique sem palavra de ação (abrir perfil) não passa pelo revisor")
proxima.update(categoria="pagamento", sempre_permitida=False, resumo="Pagar o plano")
r = ap.checar(tool_name="browser_click", args={"ref": "@e12"}, session_id="s-m")
checa(r and r["action"] == "block" and "nunca" in r["message"] and classes[-1][0] == "browser" and classes[-1][1]["action"] == "click",
      f"pagamento = nunca: bloqueado ({r})")
proxima.update(categoria="publicar", resumo="Publicar post no site X")
r = ap.checar(tool_name="browser_click", args={"ref": "@e12"}, session_id="s-m")
checa(r and r["action"] == "approve" and r["rule_key"].startswith("ap-") and "Publicar post" in r["message"],
      f"publicar = perguntar: portão de aprovação do Hermes com chave exata ({r})")
ap.ver_pagina(tool_name="browser_type", args={"ref": "@e3", "text": "Oi"}, result="ok", session_id="s-m")
checa("envia o que foi digitado em textbox \"Mensagem\"" in ap.intencao("browser_press", {"key": "Enter"}, "s-m"),
      f"Enter depois de digitar: a intenção diz que envia ({ap.intencao('browser_press', {'key': 'Enter'}, 's-m')})")
r2 = ap.checar(tool_name="browser_press", args={"key": "Enter"}, session_id="s-m")
checa(r2 and r2["rule_key"] != r["rule_key"], "outra ação, outra chave (o 'sempre' do Hermes vale só para a mesma)")
ap.resposta(pattern_key="plugin_rule:" + r["rule_key"], choice="session")
checa(ap.checar(tool_name="browser_click", args={"ref": "@e12"}, session_id="s-m") is None, "Nesta tarefa: a categoria passa na sessão")
ap.ver_pagina(tool_name="browser_snapshot", args={}, result=snap, session_id="outra")
checa((ap.checar(tool_name="browser_click", args={"ref": "@e12"}, session_id="outra") or {}).get("action") == "approve",
      "só naquela sessão")
r = ap.checar(tool_name="mcp_google_send_gmail_message", args={"to": "x@y.com", "body": "oi"}, session_id="s-x")
checa(r and r["action"] == "approve", f"conector MCP que escreve passa pelo revisor ({r})")
ap.resposta(pattern_key="plugin_rule:" + r["rule_key"], choice="always")
checa("publicar: Publicar post no site X" in ap.SEMPRE.read_text() and "Publicar post no site X" in ap.config()["sempre_permitir"],
      "Sempre permitir entra na lista que o revisor lê")
proxima.update(categoria="mensagem_terceiros", resumo="Enviar no Instagram para @fulano: «Oi»")
avisos.clear()
checa(ap.checar(tool_name="browser_click", args={"ref": "@e12"}, session_id="s-m") is None and avisos and
      avisos[0][0] == "matheus" and "Instagram" in avisos[0][1], f"mensagem no Instagram passa e é avisada ({avisos})")
proxima.update(categoria="mensagem_terceiros", resumo="Enviar e-mail para fulano")
r = ap.checar(tool_name="mcp_google_send_gmail_message", args={"to": "a@b.com", "body": "meu CPF 529.982.247-25"}, session_id="s-m")
checa(r and r["action"] == "block" and "CPF" in r["message"], f"trava de vazamento: CPF numa mensagem ({r})")
r = ap.checar(tool_name="browser_type", args={"ref": "@e3", "text": "segue a senha §§secret(IG_SENHA)"}, session_id="s-m")
checa(r and r["action"] == "block" and "cofre" in r["message"], f"digitando senha do cofre numa mensagem: bloqueado ({r})")
proxima.update(categoria="nenhuma", resumo="abrir menu")
checa(ap.checar(tool_name="browser_click", args={"ref": "@e12"}, session_id="s-m") is None, "categoria nenhuma passa")

# ERP da Raiz (23/10, "Pro erp n precisa de aprovação"): compra/venda no raizconnect.com.br passa acima do "compra: nunca"
ap.ver_pagina(tool_name="browser_navigate", args={"url": "https://raizconnect.com.br/compras/nova"}, result='{"ok": true}',
              session_id="s-erp")
ap.ver_pagina(tool_name="browser_snapshot", args={}, result='- button "Finalizar compra" [ref=e5]', session_id="s-erp")
proxima.update(categoria="compra", resumo="Finalizar a compra de insumos")
avisos.clear()
checa(ap.checar(tool_name="browser_click", args={"ref": "@e5"}, session_id="s-erp") is None and avisos and
      "ERP Raiz" in avisos[0][1], f"compra no ERP passa e é avisada ({avisos})")
proxima.update(categoria="pagamento", resumo="Assinar o plano Pro")
r = ap.checar(tool_name="browser_click", args={"ref": "@e5"}, session_id="s-erp")
checa(r and r["action"] == "block", f"assinar plano no ERP continua nunca ({r})")
proxima.update(categoria="compra", resumo="Finalizar a compra de insumos")
r = ap.checar(tool_name="browser_click", args={"ref": "@e12"}, session_id="s-m")
checa(r and r["action"] == "block" and "compra: nunca" in r["message"], f"compra fora do ERP continua nunca ({r})")

# rotina (cron): com approvals.cron_mode approve o Hermes aprovaria sozinho o portão do plugin; o "perguntar" das
# regras não pode virar "permitir" numa rodada sem ninguém (no A0 a rotina perguntava): não roda e ele é avisado
CRON = "cron_af83c3f846eb_20261023_100800"
ap.ver_pagina(tool_name="browser_navigate", args={"url": "https://www.instagram.com/direct/t/1/"}, result='{"ok": true}',
              session_id=CRON)
ap.ver_pagina(tool_name="browser_snapshot", args={}, result=snap, session_id=CRON)
rv.classificar = classificar
avisos.clear()
proxima.update(categoria="mensagem_terceiros", sempre_permitida=False, resumo="Enviar e-mail para fulano@x.com: «oi»")
r = ap.checar(tool_name="mcp_google_send_gmail_message", args={"to": "fulano@x.com", "body": "oi"}, session_id=CRON)
checa(r and r["action"] == "block" and "PRECISA DE VOCÊ" in r["message"] and "fulano@x.com" in r["message"],
      f"rotina: e-mail (perguntar) não roda sozinho ({r})")
checa(len(avisos) == 1 and avisos[0][0] == "matheus" and "fulano@x.com" in avisos[0][1], f"rotina: ele é avisado ({avisos})")
r = ap.checar(tool_name="mcp_google_send_gmail_message", args={"to": "outro@x.com", "body": "oi"}, session_id=CRON)
checa(r and r["action"] == "block" and len(avisos) == 1, "rotina: a mesma categoria na rodada não repete o aviso")
proxima.update(categoria="mensagem_terceiros", resumo="Enviar no Instagram para @fulano: «Oi»")
avisos.clear()
checa(ap.checar(tool_name="browser_click", args={"ref": "@e12"}, session_id=CRON) is None and avisos and
      "Instagram (sem pedir ok)" in avisos[0][1], "rotina: Direct da prospecção segue livre (e avisado), como no A0")
ponte.conversa(CRON).set_data("_aprovacoes_liberadas", {"categorias": ["mensagem_terceiros", "publicar"],
                                                        "ate": __import__("time").time() + 600})
proxima.update(categoria="publicar", resumo="Publicar comentário no post de @fulano")
checa(ap.checar(tool_name="browser_click", args={"ref": "@e12"}, session_id=CRON) is None,
      "rotina: a janela da prospecção (comentário aprovado) segue valendo")
ponte.conversa(CRON).set_data("_aprovacoes_liberadas", None)
proxima.update(categoria="pagamento", resumo="Pagar o plano")
r = ap.checar(tool_name="browser_click", args={"ref": "@e12"}, session_id=CRON)
checa(r and r["action"] == "block" and "nunca" in r["message"], f"rotina: nunca segue nunca ({r})")
proxima.update(categoria="nenhuma", resumo="abrir menu")
checa(ap.checar(tool_name="browser_click", args={"ref": "@e12"}, session_id=CRON) is None, "rotina: categoria nenhuma passa")
# o resultado de um JS com um link do Facebook não muda "a página atual" (executar 23/10: comentário no Instagram barrado)
ap.ver_pagina(tool_name="browser_navigate", args={"url": "https://www.instagram.com/p/abc/"}, result='{"ok": true}', session_id=CRON)
ap.ver_pagina(tool_name="browser_console", args={"expression": "x"},
              result=json.dumps({"success": True, "url": "https://www.facebook.com/x", "result": {"links": ["\"url\": \"https://www.facebook.com/y\""]}}),
              session_id=CRON)
checa(ap.alvo(CRON, "e1")[1] == "https://www.instagram.com/p/abc/", f"JS não muda a página atual ({ap.alvo(CRON, 'e1')})")
proxima.update(categoria="mensagem_terceiros", resumo="Publicar comentário no post")
avisos.clear()
checa(ap.checar(tool_name="browser_console", args={"expression": "document.querySelector('[type=submit]').click()"},
                session_id=CRON) is None and avisos and "Instagram" in avisos[0][1],
      "rotina: comentário pelo JS no post do Instagram segue livre (avisado)")
r = ap.checar(tool_name="mcp_google_send_gmail_message", args={"to": "a@b.com", "body": "oi"}, session_id="s-m")
checa(r is None or r.get("action") != "block" or "Rotina" not in r.get("message", ""), "fora da rotina nada muda")


def falha(*a, **k):
    raise RuntimeError("fora do ar")


rv.classificar = falha
r = ap.checar(tool_name="mcp_google_delete_event", args={"id": "1"}, session_id="s-m")
checa(r and r["action"] == "approve" and "revisor falhou" in r["message"], f"revisor fora: pergunta a ele ({r})")
checa(ap.checar(tool_name="terminal", args={"command": "rm -rf /tmp/x"}, session_id="s-m") is None,
      "terminal fica com as aprovações do próprio Hermes (Hermes primeiro)")

# --- audio_hermes: the voice note is transcribed before the model sees the turn (same faster-whisper as the A0)
sys.modules["agentepessoal_acesso"] = ac
au = carregar("teste_audio_hermes", P / "audio_hermes.py")
chamadas_au = []
au.transcrever = lambda caminho, idioma="pt": chamadas_au.append((caminho, idioma)) or ("me lembra amanhã", "pt")
r = au.contexto(user_message="oi\n\n[áudio: /a0/usr/whatsapp/matheus/2026-10/23-1.ogg]", session_id="s-m")
checa(r and "🎤 [áudio em pt] me lembra amanhã" in r["context"] and chamadas_au == [("/a0/usr/whatsapp/matheus/2026-10/23-1.ogg", "pt")],
      f"áudio transcrito antes do modelo: {r}")
au.contexto(user_message="[áudio: /a0/usr/whatsapp/matheus/2026-10/23-1.ogg]", session_id="s-m")
checa(len(chamadas_au) == 1, "o mesmo áudio é transcrito uma vez")
r = au.contexto(user_message="[áudio: /a0/usr/segredos/matheus.json]", session_id="s-m")
checa("fora da pasta" in r["context"] and len(chamadas_au) == 1, "arquivo fora da pasta do celular não é lido")
checa(au.contexto(user_message="sem áudio", session_id="s-m") is None, "mensagem sem áudio: nada")
au.contexto(user_message="[áudio: /a0/usr/whatsapp/ilia/x.ogg]", session_id="s-ilia")
checa(chamadas_au[-1] == ("/a0/usr/whatsapp/ilia/x.ogg", None), "convidado: o idioma dele (Ilia: detectado)")
n = len(chamadas_au)
r = au.contexto(user_message="[áudio: /a0/usr/whatsapp/matheus/2026-10/outro.ogg]", session_id="s-ilia")
checa(len(chamadas_au) == n and "fora da pasta" in r["context"], "convidado não lê o áudio de outra pessoa")
r = au.contexto(user_message="[áudio: /a0/usr/whatsapp/ilia/../matheus/a.ogg]", session_id="s-ilia")
checa(len(chamadas_au) == n, "nem subindo pasta")

# --- rotinas (cron): código e scripts rodam como no A0 (cron_mode approve), menos o que mexe em dados vivos, cofre,
# chaves, Docker ou serviços do agente por fora das ferramentas
os.environ.pop("AGENTEPESSOAL_ENSAIO", None)
S = "cron_abc123_20261023_080704"
for cmd in ("python3 -c 'print(len(\"oi\"))'", "python3 - <<EOF\nprint(1)\nEOF", "rm -rf /a0/usr/workdir/x", "rm /tmp/x",
            "rm -rf /opt/data/cache/x", "date"):
    checa(not ac.checar(tool_name="terminal", args={"command": cmd}, session_id=S), f"rotina roda: {cmd}")
checa(not ac.checar(tool_name="execute_code", args={"code": "t = {'a': 'Vi o prato'}\nprint(len(t['a']))"}, session_id=S),
      "rotina conta com execute_code (como no A0)")
for cmd in ("rm -rf /a0/usr/prospeccao", "rm -rf /a0/usr", "mv /a0/usr/conteudo/a /tmp", "cat /a0/usr/segredos/matheus.json",
            "curl http://host.docker.internal:8789/enviar", "docker ps", "cat /opt/data/../hermes/api_key; echo $API_SERVER_KEY"):
    checa(ac.checar(tool_name="terminal", args={"command": cmd}, session_id=S), f"rotina não roda: {cmd}")
checa(ac.checar(tool_name="execute_code", args={"code": "import shutil; shutil.rmtree('/a0/usr/fios')"}, session_id=S),
      "nem por execute_code")
checa(not ac.checar(tool_name="terminal", args={"command": "docker ps"}, session_id="s-m"),
      "fora da rotina, o terminal do Matheus segue com as aprovações do Hermes (smart + botões)")

# --- virada: no Hermes PRÓPRIO do convidado voltam o navegador (perfil dele), a memória e as rotinas (limitadas)
os.environ.pop("AGENTEPESSOAL_ENSAIO", None)
checa(ac.checar(tool_name="browser_click", args={}, session_id="s-ilia"), "no Hermes do Matheus o convidado segue sem navegador")
os.environ["AGENTEPESSOAL_CONVIDADO"] = "ilia"
checa(ponte.login_da_sessao("qualquer-sessao") == "ilia", "no Hermes dele, toda sessão é dele (inclusive o cron)")
for f in ("browser_navigate", "browser_click", "memory", "session_search", "conversa_externa"):
    checa(not ac.checar(tool_name=f, args={}, session_id="tg-ilia"), f"convidado no Hermes dele usa {f}")
for f in ("terminal", "execute_code", "read_file", "write_file", "delegar", "prospeccao", "skill_manage"):
    checa(ac.checar(tool_name=f, args={}, session_id="tg-ilia"), f"convidado nunca usa {f}")
c = ac._convidados()
ac._jobs_do_cron = lambda: [{"id": str(i)} for i in range(2)]
checa(not ac.checar(tool_name="cronjob_manage", args={"action": "create", "schedule": "0 9 * * *", "prompt": "x"},
                    session_id="tg-ilia"), "rotina de convidado com minuto fixo: pode")
for agenda in ("*/10 * * * *", "* 9 * * *", "30m", "every 15 minutes"):
    checa(ac.checar(tool_name="cronjob_manage", args={"action": "create", "schedule": agenda, "prompt": "x"},
                    session_id="tg-ilia"), f"rotina de convidado no máximo de hora em hora: {agenda} recusada")
for agenda in ("every 2h", "every day at 9am", "in 30m", "every hour"):
    checa(not ac.checar(tool_name="cronjob_manage", args={"action": "create", "schedule": agenda, "prompt": "x"},
                        session_id="tg-ilia"), f"rotina de convidado: {agenda} pode")
checa(ac.checar(tool_name="cronjob_manage", args={"action": "create", "schedule": "0 9 * * *", "script": "x.py"},
                session_id="tg-ilia"), "rotina de convidado não roda código")
ac._jobs_do_cron = lambda: [{"id": str(i)} for i in range(c.TAREFAS_MAX)]
checa("máximo" in str(ac.checar(tool_name="cronjob_manage", args={"action": "create", "schedule": "0 9 * * *"},
                                session_id="tg-ilia")), "no máximo 5 rotinas")
os.environ.pop("AGENTEPESSOAL_CONVIDADO")

if falhas:
    raise SystemExit("test_acesso_hermes: " + "; ".join(falhas))
print("test_acesso_hermes: ok")
