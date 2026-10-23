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
for plugin_nome, nome in plugin.FERRAMENTAS:
    checa(nome in registradas, f"{plugin_nome}/{nome} carrega só com a ponte (sem o Agent Zero)")
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
ponte.SESSOES.write_text(json.dumps({"tg-fernanda-1": "fernanda"}))
checa(ponte.conversa("tg-fernanda-1").get_data("dono") == "fernanda", "o dono vem do mapa de sessões")
checa(ponte.conversa("outra").get_data("dono") == ponte.DONO_PADRAO, "sessão sem dono é do Matheus")
ponte.SESSOES.write_text(json.dumps({"tg-fernanda-1": "fernanda", "cron_ab*": "ilia", "cron_abc*": "will"}))
checa(ponte.login_mapeado("cron_abc_20261023") == "will" and ponte.login_mapeado("cron_abx") == "ilia",
      "chave com * cobre as sessões que começam com ela (a mais longa vale)")
checa(ponte.login_mapeado("outra") == "", "login_mapeado não inventa dono (o cofre depende disso)")
ponte.SESSOES.write_text("[1, 2]")
checa(ponte.login_mapeado("x") == "" and ponte.login_da_sessao("x") == ponte.DONO_PADRAO, "mapa estragado não quebra")
checa("helpers.tool" in sys.modules and not hasattr(sys.modules["helpers.tool"], "PrintStyle"), "só os módulos mínimos")
if falhas:
    raise SystemExit("test_ponte_a0: " + "; ".join(falhas))
print(f"test_ponte_a0: ok ({len(registradas)} ferramentas)")
