"""Tests of the Hermes bridge to our Agent Zero tools (infra/vm/hermes/plugins/agentepessoal, 23/10 migration): every
listed tool loads from its plugin file with only the stub modules (no Agent Zero), gets a JSON schema built from its
signature and manual, and runs; the session's owner comes from the sessions map (owner by default). Run from the
repository root: python3 infra/vm/tests/test_ponte_a0.py"""
import asyncio
import importlib.util
import json
import sys
import tempfile
import types
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
P = RAIZ / "infra" / "vm" / "hermes" / "plugins" / "agentepessoal"
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


ponte = carregar("teste_ponte_a0", P / "ponte_a0.py")
ponte.PLUGINS = RAIZ / "infra" / "vm" / "plugins"
tmp = Path(tempfile.mkdtemp())
ponte.SESSOES = tmp / "sessoes.json"
plugin = types.ModuleType("teste_agentepessoal")
plugin.__file__ = str(P / "__init__.py")
src = (P / "__init__.py").read_text().replace('_aqui / "ponte_a0.py"', 'Path(__file__).resolve().parent / "ponte_a0.py"')
exec(compile(src, str(P / "__init__.py"), "exec"), plugin.__dict__)
plugin.ponte = ponte
sys.modules["agentepessoal_ponte_a0"].PLUGINS = ponte.PLUGINS  # the modules of the plugin read the bridge from there
sys.modules["agentepessoal_ponte_a0"].SESSOES = ponte.SESSOES

registradas = {}


class Ctx:
    def register_tool(self, name, toolset, schema, handler, is_async=False):
        # the Hermes runs a handler as a coroutine only when told so (tools/registry.py: entry.is_async)
        checa(is_async == asyncio.iscoroutinefunction(handler), f"{name}: is_async bate com o manipulador")
        registradas[name] = (schema, handler)

    def register_middleware(self, kind, callback):
        ganchos.append(("middleware", kind))

    def register_hook(self, nome, callback):
        ganchos.append(("hook", nome))


ganchos = []


plugin.register(Ctx())
for g in (("middleware", "tool_execution"), ("middleware", "llm_request"), ("hook", "transform_tool_result"),
          ("hook", "pre_llm_call")):
    checa(g in ganchos, f"o cofre se liga ao Hermes: {g}")
# "Hermes primeiro" (23/10): nada nosso com o nome ou o papel de uma ferramenta que o Hermes já faz bem, e nada que grave
# no agendador/conversas do Agent Zero (lista tirada da v0.22.2 na VM)
NATIVAS = {"web_search", "web_extract", "memory", "todo_list", "delegate_task", "read_file", "write_file", "patch",
           "search_files", "terminal", "execute_code", "session_search", "cronjob_manage", "vision_analyze",
           "video_analyze", "skill_manage", "skill_view", "skills_list", "clarify", "text_to_speech", "image_generate"}
NATIVAS |= {n for n in registradas if n.startswith(("browser_", "kanban_"))}
SO_NO_A0 = {"pesquisar", "tarefa_limite", "salvar_rotina", "criar_gatilho", "passos", "painel_vivo", "canal", "reuniao"}
nomes = {n for _, n in plugin.FERRAMENTAS}
checa(not nomes & NATIVAS, f"ponte não repete ferramenta nativa do Hermes: {sorted(nomes & NATIVAS)}")
checa(not nomes & SO_NO_A0, f"ponte não leva ferramenta que grava no agendador do A0 ou repete o Hermes: {sorted(nomes & SO_NO_A0)}")
# Pelo comportamento, não só pelo nome (revisão OpenCode 23/10): partindo dos métodos da ferramenta, seguindo as chamadas
# dentro do plugin, nada usa o agendador ou as conversas do Agent Zero (pelo Hermes daria erro de import ou criaria coisa
# que o A0 executa).
import ast
import re
P_A0 = ponte.PLUGINS
MARCAS=re.compile(r"TaskScheduler|PlannedTask|ScheduledTask|AdHocTask|AgentContext|save_tmp_chat|_para_a_conversa|helpers\.task_scheduler|helpers\.persist_chat")
def alcance(plug, nome):
    arqs=[P_A0/plug/"tools"/f"{nome}.py"]+sorted((P_A0/plug/"helpers").glob("*.py"))
    funcs={}; inicio=[]
    for a in arqs:
        if not a.exists(): continue
        t=a.read_text(); arv=ast.parse(t)
        for n in ast.walk(arv):
            if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):
                funcs.setdefault(n.name,[]).append((a.name,t,n))
        if a.parent.name=="tools":
            for n in ast.walk(arv):
                if isinstance(n,ast.ClassDef):
                    for m in n.body:
                        if isinstance(m,(ast.FunctionDef,ast.AsyncFunctionDef)): inicio.append((a.name,t,m))
    vistos=set(); fila=list(inicio); achados=set()
    while fila:
        arq,t,f=fila.pop()
        if (arq,f.name,f.lineno) in vistos: continue
        vistos.add((arq,f.name,f.lineno))
        seg=ast.get_source_segment(t,f) or ""
        for i,l in enumerate(seg.splitlines()):
            m=MARCAS.search(l)
            if m and not l.strip().startswith("#"): achados.add(f"{arq}:{f.lineno+i}:{f.name}:{m.group(0)}")
        for c in ast.walk(f):
            if isinstance(c,ast.Call):
                nm=c.func.id if isinstance(c.func,ast.Name) else c.func.attr if isinstance(c.func,ast.Attribute) else None
                for alvo in funcs.get(nm,[]): fila.append(alvo)
    return sorted(achados)

LEITURA_DO_DONO = {("login_usuarios", "terminal_isolado"): {"dono_contexto"},  # só lê o dono da conversa pai, em try
                   # virada: o navegador da conversa e a entrega na conversa são trocados por externas_hermes.instalar()
                   # (conferido logo abaixo): contexto() do A0 nunca roda e _para_a_conversa entrega pela ponte
                   ("conversas_externas", "conversa_externa"): {"contexto", "aprender_em_fundo"}}
for plugin_nome, nome in plugin.FERRAMENTAS:
    achados = [a for a in alcance(plugin_nome, nome) if a.split(":")[2] not in LEITURA_DO_DONO.get((plugin_nome, nome), ())]
    checa(not achados, f"{plugin_nome}/{nome} usa o agendador/conversas do A0: {achados[:3]}")
for plugin_nome, nome in plugin.FERRAMENTAS:
    checa(nome in registradas, f"{plugin_nome}/{nome} carrega só com a ponte (sem o Agent Zero)")
# conversas externas no Hermes: o navegador é o desta instância (CDP), o vigia atende só os logins dela, e o que o A0
# entregaria na conversa vai à ponte (/conversa)
import os as _os
_os.environ["BROWSER_CDP_URL"] = "http://cdp-teste:9223"
plugin.externas.PLUGINS = ponte.PLUGINS
plugin.externas.RAIZ = ponte.PLUGINS / "conversas_externas"
plugin.externas.CONVIDADOS = ponte.PLUGINS / "login_usuarios" / "helpers" / "convidados.py"
plugin.botoes.PLUGINS, plugin.botoes.RECEBER = ponte.PLUGINS, ponte.PLUGINS / "whatsapp" / "api" / "receber.py"
for velho in ("conversas_externas_helper", "conversas_externas_navegador", "whatsapp_receber_vigia", "whatsapp_ponte"):
    sys.modules.pop(velho, None)
ex_mod, nav_mod = plugin.externas.instalar()
rt = asyncio.run(nav_mod._runtime(ex_mod, "matheus", "Matheus"))
checa(type(rt).__name__ == "NavegadorCDP" and rt.base == "http://cdp-teste:9223", "conversa_externa: navegador do Hermes por CDP")
try:
    asyncio.run(nav_mod._runtime(ex_mod, "ilia", "Ilia"))
    checa(False, "o WhatsApp de um convidado não abre no navegador do Matheus")
except nav_mod.SemWhatsApp:
    pass
try:
    asyncio.run(nav_mod._runtime(ex_mod, "fernanda", "Fernanda"))
    checa(False, "o WhatsApp da Fernanda (não convidada) não abre no navegador do Matheus")
except nav_mod.SemWhatsApp:
    pass
checa(plugin.externas.meus_logins(["fernanda", "ilia", "matheus", "will"], "") == ["matheus"]
      and plugin.externas.meus_logins(["ilia", "matheus"], "ilia") == ["ilia"], "vigia: cada instância só os logins dela")
rec = sys.modules["whatsapp_receber_vigia"]
checa(rec._entregar is plugin.botoes._entregar and getattr(rec, "_hermes", False), "o receber do A0 entrega no Hermes (ponte)")
checa(all(hasattr(rec, f) for f in plugin.botoes.BOTOES.values()) and hasattr(rec, "AJUDA") and hasattr(rec, "_atividade"),
      "as funções dos botões existem no receber.py do A0")
# os botões: a função do A0 pelo prefixo; o que ela entregaria na conversa vai à ponte (/conversa)
feitos_b = []


class _Rec:
    async def _botao_fio(self, u, b):
        feitos_b.append(("fio", u, b))
        return self._entregar(u, "✅ Faz pra mim (fio solto f1)", [], "", " (botão)")
rb = _Rec()
rb._entregar = plugin.botoes._entregar
plugin.botoes.conversa = lambda u, t: feitos_b.append(("conversa", u, t)) or {"ok": True}
_receber_orig = plugin.botoes.receber
plugin.botoes.receber = lambda: rb
r = asyncio.run(plugin.botoes.tratar("matheus", "fio:matheus:f1:fazer"))
checa(r == {"ok": True} and feitos_b == [("fio", "matheus", "fio:matheus:f1:fazer"),
                                         ("conversa", "matheus", "✅ Faz pra mim (fio solto f1)")],
      f"botão do fio: função do A0, e o 'faz pra mim' vira pedido no Hermes: {feitos_b}")
checa(asyncio.run(plugin.botoes.tratar("matheus", "xx:1"))["ok"] is False, "botão desconhecido: não faz nada")
plugin.botoes.receber = _receber_orig
# a ponte fora do ar: o que ia para a conversa fica pendente e vai no próximo minuto (nunca se perde)
plugin.botoes.PENDENTES = tmp / "pendente.jsonl"


def _falha(u, t):
    raise OSError("ponte fora")
plugin.botoes.conversa = _falha
checa(plugin.botoes._para_a_conversa("matheus", "resposta da loja")["ok"] and plugin.botoes.PENDENTES.exists(),
      "ponte fora: fica pendente")
entregues_p = []
checa(plugin.botoes.reentregar(lambda u, t: entregues_p.append((u, t)) or {"ok": True}) == 1
      and entregues_p == [("matheus", "resposta da loja")] and not plugin.botoes.PENDENTES.exists(), "e vai depois")
rec2 = plugin.botoes.receber()
checa(rec2._para_a_conversa is plugin.botoes._para_a_conversa, "o vigia e o aprender entregam sem o UserMessage do A0")
# delegar só ao OpenClaw; celular com a tela num arquivo
checa("motor" not in registradas["delegar"][0]["parameters"]["properties"] and "OpenClaw" in registradas["delegar"][0]["description"],
      "delegar: o motor é sempre o OpenClaw (o Hermes tem delegate_task)")
ponte.IMAGENS = tmp / "telas"
nota = ponte.guardar_imagem(b"\xff\xd8jpg", "celular")
checa("vision_analyze" in nota and len(list(ponte.IMAGENS.glob("celular-*.jpg"))) == 1, "a tela do celular vira arquivo")
for nome, (schema, _) in registradas.items():
    try:
        json.dumps(schema)
    except TypeError as exc:
        checa(False, f"{nome}: esquema não é JSON: {exc}")
    checa(schema["name"] == nome and len(schema["description"]) > 40, f"{nome}: esquema com o manual")
ler = registradas.get("ler")
checa(ler and ler[0]["parameters"]["properties"]["caminho"] == {"type": "string"}, "tipos vêm da assinatura")
checa(ler and ler[0]["parameters"]["properties"]["inicio"] == {"type": "integer"}, "inteiro pela assinatura")
csv = tmp / "t.csv"
csv.write_text("nome,valor\nbolo,15\n")
if ler:
    saida = asyncio.run(ler[1]({"caminho": str(csv)}, session_id="s1"))
    checa("bolo" in saida, f"a ferramenta roda pelo Hermes: {saida[:200]}")
import errno
import sqlite3


class _Grava(ponte.Tool):
    async def execute(self, **kwargs):
        raise OSError(errno.EROFS, "Read-only file system", "/a0/usr/prospeccao/matheus.lock")


class _Quebra(ponte.Tool):
    async def execute(self, **kwargs):
        raise ValueError("outro erro")


checa(asyncio.run(ponte.executar(_Grava, "x", {}, "s")) == ponte.ERRO_SO_LEITURA, "ação que grava no ensaio: erro claro")
checa(ponte.somente_leitura(sqlite3.OperationalError("unable to open database file")), "sqlite só leitura também")
checa(ponte.somente_leitura(PermissionError(errno.EACCES, "Permission denied", "/a0/usr/whatsapp/.chave")),
      "pasta escondida no ensaio também")
checa(not ponte.somente_leitura(PermissionError(errno.EACCES, "Permission denied", "/etc/shadow")), "fora dos dados, não")
try:
    asyncio.run(ponte.executar(_Quebra, "x", {}, "s"))
    checa(False, "outro erro não é engolido")
except ValueError:
    pass
ponte.SESSOES.write_text(json.dumps({"tg-fernanda-1": "fernanda"}))
checa(ponte.conversa("tg-fernanda-1").get_data("dono") == "fernanda", "o dono vem do mapa de sessões")
checa(ponte.conversa("outra").get_data("dono") == ponte.DONO_PADRAO, "sessão sem dono é do Matheus")
ponte.SESSOES.write_text(json.dumps({"tg-fernanda-1": "fernanda", "cron_ab*": "ilia", "cron_abc*": "will"}))
checa(ponte.login_mapeado("cron_abc_20261023") == "will" and ponte.login_mapeado("cron_abx") == "ilia",
      "chave com * cobre as sessões que começam com ela (a mais longa vale)")
checa(ponte.login_mapeado("outra") == "", "login_mapeado não inventa dono (o cofre depende disso)")
ponte.SESSOES.write_text(json.dumps({"*": "ilia", "c*": "will"}))
checa(ponte.login_mapeado("qualquer") == "" and ponte.login_mapeado("cron_x") == "", "prefixo curto demais não vale")
ponte.SESSOES.write_text("[1, 2]")
checa(ponte.login_mapeado("x") == "" and ponte.login_da_sessao("x") == ponte.DONO_PADRAO, "mapa estragado não quebra")
checa("helpers.tool" in sys.modules and not hasattr(sys.modules["helpers.tool"], "PrintStyle"), "só os módulos mínimos")
# 23/10 (fase 5): o navegador do A0 que as ferramentas pedem (prospecção: a lista do Direct) é o do Hermes, por CDP
import os as _os
navegador_mod = sys.modules["plugins._browser.helpers.runtime"]
checa(asyncio.run(navegador_mod.get_runtime("ctx")) is None or _os.environ.get("BROWSER_CDP_URL"), "sem CDP, sem navegador")
_os.environ["BROWSER_CDP_URL"] = "http://172.22.0.250:9223"
rt = asyncio.run(navegador_mod.get_runtime("ctx", create=False))
rt._abas = lambda: [{"id": "A", "url": "https://www.instagram.com/direct/inbox/", "title": "Direct",
                     "webSocketDebuggerUrl": "ws://172.22.0.250:9223/devtools/page/A"}]
lista = asyncio.run(rt.call("list"))["browsers"]
checa(lista == [{"id": "A", "currentUrl": "https://www.instagram.com/direct/inbox/", "title": "Direct"}], f"abas: {lista}")
enviados_ws = []


class _WS:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def send(self, dado):
        enviados_ws.append(json.loads(dado))

    async def recv(self):
        return json.dumps({"id": 1, "result": {"result": {"value": "{\"conversas\": 3}"}}})


ws_falso = types.ModuleType("websockets")
ws_falso.connect = lambda url, **kw: _WS()
sys.modules["websockets"] = ws_falso
r = asyncio.run(rt.call("evaluate", "A", "(async () => { return 1; })()"))
checa(r == {"result": '{"conversas": 3}'} and enviados_ws[-1]["params"]["expression"] == "(async () => { return 1; })()"
      and enviados_ws[-1]["params"]["awaitPromise"], f"script já chamado vai como está: {enviados_ws[-1]}")
asyncio.run(rt.call("evaluate", "A", "() => { return 2; }"))
checa(enviados_ws[-1]["params"]["expression"] == "(() => { return 2; })()", "função vira chamada (como o evaluate do Playwright)")
try:
    asyncio.run(rt.call("evaluate", "B", "1"))
    checa(False, "aba fechada dá erro")
except LookupError:
    pass
_os.environ.pop("BROWSER_CDP_URL")
if falhas:
    raise SystemExit("test_ponte_a0: " + "; ".join(falhas))
print(f"test_ponte_a0: ok ({len(registradas)} ferramentas)")
