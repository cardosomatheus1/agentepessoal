"""Tests of the Hermes clock (infra/vm/hermes/plugins/agentepessoal/relogio_hermes.py, 23/10 migration, phase 2): the
same job_loop files of our Agent Zero plugins load under the bridge stubs; one pass runs every task and one failing
task never stops the others; the clock stays off unless AGENTEPESSOAL_RELOGIO=1 (until the cutover the A0 runs them)
and only one process of a container runs it. Run from the repository root: python3 infra/vm/tests/test_relogio_hermes.py"""
import asyncio
import fcntl
import importlib.util
import os
import re
import sys
import tempfile
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


ponte = carregar("agentepessoal_ponte_a0", P / "ponte_a0.py")
rl = carregar("teste_relogio_hermes", P / "relogio_hermes.py")
tmp = Path(tempfile.mkdtemp())
rl.TRAVA = tmp / "relogio.lock"

# the real tasks: each file exists, loads with only the stubs and touches nothing of the A0 runtime
rl.PLUGINS = PLUGINS
A0 = re.compile(r"AgentContext|TaskScheduler|mcp_handler|from agent import|initialize|helpers\.(?!extension\b)\w+")
for plugin, arquivo in rl.TAREFAS:
    caminho = PLUGINS / plugin / "extensions" / "python" / "job_loop" / arquivo
    checa(caminho.exists(), f"{plugin}/{arquivo} existe")
    try:
        checa(rl._classe(plugin, arquivo) is not None, f"{plugin}/{arquivo} carrega com a ponte")
    except Exception as exc:
        falhas.append(f"{plugin}/{arquivo} não carrega: {type(exc).__name__}: {exc}")
    checa(not A0.search(caminho.read_text(encoding="utf-8")), f"{plugin}/{arquivo} não usa nada do A0 além de Extension")

# one pass: a failing task never stops the others
falsos = tmp / "plugins"
for nome, corpo in (("a", "        (Path(__file__).parent / 'feito').write_text('1')\n"),
                    ("b", "        raise RuntimeError('quebrou')\n"),
                    ("c", "        (Path(__file__).parent / 'feito').write_text('1')\n")):
    d = falsos / nome / "extensions" / "python" / "job_loop"
    d.mkdir(parents=True)
    (d / "_10_x.py").write_text("from pathlib import Path\nfrom helpers.extension import Extension\n\n\n"
                                "class X(Extension):\n    async def execute(self, **kwargs):\n" + corpo)
rl.PLUGINS = falsos
feito = asyncio.run(rl.volta((("a", "_10_x.py"), ("b", "_10_x.py"), ("c", "_10_x.py"))))
checa(feito["a/_10_x.py"] == "ok" and feito["c/_10_x.py"] == "ok" and "quebrou" in feito["b/_10_x.py"],
      f"uma tarefa quebrada não para as outras: {feito}")
checa((falsos / "c" / "extensions" / "python" / "job_loop" / "feito").exists(), "a tarefa depois da quebrada rodou")

# off unless AGENTEPESSOAL_RELOGIO=1; one clock per container
os.environ.pop("AGENTEPESSOAL_RELOGIO", None)
checa(rl.iniciar() is False and rl._estado["thread"] is None, "desligado sem AGENTEPESSOAL_RELOGIO=1 (até a virada, o A0)")
os.environ["AGENTEPESSOAL_RELOGIO"] = "1"
outro = open(rl.TRAVA, "a")
fcntl.flock(outro, fcntl.LOCK_EX | fcntl.LOCK_NB)
checa(rl.iniciar() is False, "outro processo com a trava: este não liga um segundo relógio")
fcntl.flock(outro, fcntl.LOCK_UN)
rl.TAREFAS = (("a", "_10_x.py"),)
checa(rl.iniciar() is True and rl._estado["thread"].is_alive(), "com a variável e a trava livre, liga")
checa(rl.iniciar() is True, "chamar de novo não abre outra thread")
rl._parar.set()
rl._estado["thread"].join(5)
os.environ.pop("AGENTEPESSOAL_RELOGIO")

if falhas:
    raise SystemExit("test_relogio_hermes: " + "; ".join(falhas))
print("test_relogio_hermes: ok")
