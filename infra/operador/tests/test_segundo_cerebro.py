"""Deploy of the Segundo Cérebro without AWS: temporary git repositories, a fake `docker` that runs the container
commands locally, a synthetic package and a fake SSM. Run: python3 infra/operador/tests/test_segundo_cerebro.py"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

AQUI = Path(__file__).resolve()
OPERADOR = AQUI.parents[1]
RAIZ = AQUI.parents[3]
sys.path.insert(0, str(OPERADOR))

import segundo_cerebro as sc  # noqa: E402
import segundo_cerebro_vm as scvm  # noqa: E402

V1, V2 = "1" * 40, "2" * 40

RELEASE_FALSA = r'''
import hashlib, json, os
from http.server import BaseHTTPRequestHandler, HTTPServer
AQUI = os.path.dirname(os.path.abspath(__file__))
if os.path.exists(os.path.join(AQUI, "quebrada")):
    raise SystemExit(4)
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        auth = self.headers.get("Authorization", "")
        ok = auth.startswith("Bearer ") and hashlib.sha256(auth[7:].encode()).hexdigest() == os.environ["SECOND_BRAIN_TOKEN_SHA256"]
        if self.path == "/api/segundo-cerebro":
            st, corpo, tipo = (200, json.dumps({"owner": "matheus"}).encode(), "application/json") if ok else (401, b"{}", "application/json")
        elif self.path == "/segundo-cerebro":
            st, corpo, tipo = 200, b'<html><link rel="stylesheet" href="/_next/static/chunks/a.css"></html>', "text/html; charset=utf-8"
        elif self.path == "/_next/static/chunks/a.css":
            st, corpo, tipo = 200, b"body{}", "text/css"
        else:
            st, corpo, tipo = 404, b"", "text/plain"
        self.send_response(st); self.send_header("Content-Type", tipo); self.send_header("Content-Length", str(len(corpo)))
        self.end_headers(); self.wfile.write(corpo)
    def log_message(self, *a): pass
HTTPServer((os.environ["HOSTNAME"], int(os.environ["PORT"])), H).serve_forever()
'''

DOCKER_FALSO = r'''
import json, os, sys
from pathlib import Path
cfg_arq = Path(os.environ["FAKE_DOCKER_CFG"])
cfg = json.loads(cfg_arq.read_text())
args = sys.argv[1:]
with open(cfg["log"], "a") as f:
    f.write(json.dumps(args) + "\n")
if args[0] == "inspect":
    print("true" if cfg.get("rodando", True) else "false"); sys.exit(0)
if args[0] == "restart":
    cfg["reiniciado"] = True; cfg_arq.write_text(json.dumps(cfg)); sys.exit(0)
assert args[0] == "exec", args
resto, env = args[1:], dict(os.environ)
while resto[0].startswith("-"):
    if resto[0] == "-i":
        resto = resto[1:]
    else:
        k, v = resto[1].split("=", 1); env[k] = v; resto = resto[2:]
resto = resto[1:]  # container name
if resto[0] == "curl":
    caminho = resto[-1].split(":80", 1)[1]
    codigos = cfg["curl_depois"] if cfg.get("reiniciado") and "curl_depois" in cfg else cfg["curl"]
    if "-w" in resto:
        print(codigos.get(caminho, 0), end="")
    sys.exit(0)
if len(resto) == 2 and resto[1] == "--version" and "node_versao" in cfg:
    if not cfg["node_versao"]:
        sys.exit(127)
    print(cfg["node_versao"]); sys.exit(0)
os.execvpe(resto[0], resto, env)
'''

SUITE_OK = "class Suite:\n    async def rodar(self, so=''):\n        return {'total': 2, 'passou': 2, 'resultados': []}\n"
SUITE_FALHA = ("class Suite:\n    async def rodar(self, so=''):\n"
               "        return {'total': 2, 'passou': 1, 'resultados': [{'teste': 't_x', 'ok': False}]}\n")


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout


def arvores(base: Path) -> set:
    return {str(p.relative_to(base)) for p in base.rglob("*") if p.is_file()}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="teste-sc-implantar-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # a source tree as extrair_* leaves it, already "built"
    def fonte(self, marca: str, suite: str = SUITE_OK, quebrada: bool = False) -> Path:
        f = Path(tempfile.mkdtemp(prefix=f"fonte-{marca}-", dir=self.tmp))
        rel = f / "app" / ".next" / "standalone"
        (rel / "node_modules" / "next").mkdir(parents=True)
        (rel / "node_modules" / "next" / "package.json").write_text("{}")
        (rel / "server.js").write_text(RELEASE_FALSA)
        if quebrada:
            (rel / "quebrada").write_text("")
        (f / "app" / ".next" / "static" / "chunks").mkdir(parents=True)
        (f / "app" / ".next" / "static" / "chunks" / "a.css").write_text("body{}")
        (f / "app" / "public").mkdir(parents=True)
        (f / "app" / "public" / "icon.svg").write_text("<svg/>")
        p = f / sc.PLUGIN
        (p / "helpers").mkdir(parents=True)
        (p / "tests").mkdir()
        (p / "plugin.yaml").write_text(f"name: segundo_cerebro\ntitle: teste {marca}\n")
        shutil.copy2(RAIZ / sc.PLUGIN / "helpers" / "processo.py", p / "helpers" / "processo.py")
        (p / "tests" / "suite.py").write_text(suite)
        (p / "helpers" / "__pycache__").mkdir()
        (p / "helpers" / "__pycache__" / "x.pyc").write_bytes(b"lixo")
        (f / "infra" / "operador").mkdir(parents=True, exist_ok=True)
        shutil.copy2(OPERADOR / "segundo_cerebro_vm.py", f / sc.LADO_VM)
        return f

    def pacote(self, versao: str, **kw) -> Path:
        destino = self.tmp / f"pacote-{versao[:4]}-{len(list(self.tmp.iterdir()))}"
        destino.mkdir()
        sc.montar_pacote(self.fonte(versao[:4], **kw), destino, versao, "teste")
        return destino


class TestPacote(Base):
    def repo(self) -> Path:
        r = self.tmp / "repo"
        (r / "app" / "components").mkdir(parents=True)
        (r / sc.PLUGIN).mkdir(parents=True)
        (r / "infra" / "vm" / "plugins" / "conteudo").mkdir(parents=True)
        (r / "app" / "next.config.ts").write_text("v1")
        (r / "app" / "components" / "ChatApp.tsx").write_text("chat v1")
        (r / sc.PLUGIN / "plugin.yaml").write_text("name: segundo_cerebro\n")
        (r / "infra" / "vm" / "plugins" / "conteudo" / "a.py").write_text("conteudo v1")
        git(r, "init", "-q")
        git(r, "-c", "user.email=t@t", "-c", "user.name=t", "add", ".")
        git(r, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "v1")
        return r

    def test_head_ignora_working_tree(self):
        r = self.repo()
        (r / "app" / "next.config.ts").write_text("sujo")
        (r / "app" / "novo.ts").write_text("não commitado")
        destino = self.tmp / "x"
        destino.mkdir()
        head = sc.extrair_head(destino, r)
        self.assertEqual(head, git(r, "rev-parse", "HEAD").strip())
        self.assertEqual((destino / "app" / "next.config.ts").read_text(), "v1")
        self.assertFalse((destino / "app" / "novo.ts").exists())
        self.assertFalse((destino / "infra" / "vm" / "plugins" / "conteudo").exists(), "só os caminhos aprovados")

    def test_local_so_os_arquivos_do_foco(self):
        r = self.repo()
        (r / "app" / "next.config.ts").write_text("foco local")
        (r / "app" / "components" / "ChatApp.tsx").write_text("chat sujo")
        (r / "infra" / "vm" / "plugins" / "conteudo" / "a.py").write_text("conteudo sujo")
        destino = self.tmp / "x"
        destino.mkdir()
        o = sc.extrair_local(destino, r)
        self.assertEqual((destino / "app" / "next.config.ts").read_text(), "foco local")
        self.assertEqual((destino / "app" / "components" / "ChatApp.tsx").read_text(), "chat v1", "sujo fora do foco: HEAD")
        self.assertIn("app/components/ChatApp.tsx", o["sujos_fora"])
        self.assertIn("infra/vm/plugins/conteudo/a.py", o["sujos_fora"])
        self.assertNotIn("app/next.config.ts", o["sujos_fora"])

    def test_local_recusa_link_simbolico(self):
        r = self.repo()
        (r / "app" / "next.config.ts").unlink()
        (r / "app" / "next.config.ts").symlink_to("/etc/passwd")
        destino = self.tmp / "x"
        destino.mkdir()
        with self.assertRaises(SystemExit):
            sc.extrair_local(destino, r)

    def test_montar_pacote(self):
        p = self.tmp / "p"
        p.mkdir()
        m = sc.montar_pacote(self.fonte("a"), p, V1, "teste")
        for k in ("release/server.js", "release/.next/static/chunks/a.css", "release/public/icon.svg",
                  "release/node_modules/next/package.json", "plugin/plugin.yaml", "plugin/helpers/processo.py",
                  "vm/segundo_cerebro_vm.py"):
            self.assertIn(k, m["arquivos"])
        self.assertFalse(any("__pycache__" in k for k in m["arquivos"]))
        self.assertEqual(m["versao"], V1)
        tgz = self.tmp / "p.tgz"
        self.assertGreater(sc.empacotar(p, tgz), 0)

    def test_pacote_recusa_inseguro(self):
        f = self.fonte("b")
        (f / "app" / ".next" / "standalone" / "fora").symlink_to("/etc")
        with self.assertRaises(SystemExit):
            p = self.tmp / "p1"; p.mkdir(); sc.montar_pacote(f, p, V1, "t")
        (f / "app" / ".next" / "standalone" / "fora").unlink()
        (f / "app" / ".next" / "standalone" / ".env.local").write_text("SEGREDO=x")
        with self.assertRaises(SystemExit):
            p = self.tmp / "p2"; p.mkdir(); sc.montar_pacote(f, p, V1, "t")
        (f / "app" / ".next" / "standalone" / ".env.local").unlink()
        (f / "app" / ".next" / "standalone" / "server.js").unlink()
        with self.assertRaises(SystemExit):
            p = self.tmp / "p3"; p.mkdir(); sc.montar_pacote(f, p, V1, "t")

    def test_conferir_git_recusa_sujo(self):
        try:
            import implantar
        except ImportError as exc:  # boto3 missing
            self.fail(f"implantar.py não importou: {exc}")
        r = self.repo()
        (r / "app" / "next.config.ts").write_text("sujo")
        antigo = implantar.RAIZ
        implantar.RAIZ = r
        try:
            with self.assertRaises(SystemExit) as e:
                implantar._conferir_git(sc.CAMINHOS_APROVADOS)
            self.assertIn("não commitadas", str(e.exception))
        finally:
            implantar.RAIZ = antigo

    def test_sem_forcar(self):
        import implantar
        with self.assertRaises(SystemExit) as e:
            implantar.segundo_cerebro(["--segundo-cerebro", "--forcar"])
        self.assertIn("--forcar", str(e.exception))

    def test_git_sujo_para_antes_de_tudo(self):
        chamadas = []

        def sujo(caminhos):
            self.assertEqual(caminhos, sc.CAMINHOS_APROVADOS)
            raise SystemExit("há mudanças não commitadas")

        with self.assertRaises(SystemExit):
            sc.implantar(lambda *a: chamadas.append(a), lambda *a: chamadas.append(a), sujo, None, None, None,
                         lambda: chamadas.append("conta"), "balde")
        self.assertEqual(chamadas, [], "nada de conta, VM ou S3 com o git sujo")


class TestLadoVm(Base):
    def setUp(self):
        super().setUp()
        self.usr = self.tmp / "usr"
        (self.usr / "plugins" / "outro").mkdir(parents=True)
        (self.usr / "plugins" / "outro" / "plugin.yaml").write_text("name: outro\n")
        (self.usr / "memoria" / "decisoes").mkdir(parents=True)
        (self.usr / "memoria" / "decisoes" / "matheus.json").write_text('{"decisoes": []}')
        bin_ = self.tmp / "bin"
        bin_.mkdir()
        self.docker = bin_ / "docker"
        self.docker.write_text(f"#!{sys.executable}\n" + DOCKER_FALSO)
        self.docker.chmod(0o755)
        self.cfg = self.tmp / "docker.json"
        self.log = self.tmp / "docker.log"
        self.config(curl={"/segundo-cerebro": 401, "/api/segundo-cerebro": 401, "/login": 200}, node_versao="v22.22.0")

    def config(self, **kw):
        atual = json.loads(self.cfg.read_text()) if self.cfg.exists() else {"log": str(self.log)}
        atual.update(kw)
        self.cfg.write_text(json.dumps(atual))
        os.environ["FAKE_DOCKER_CFG"] = str(self.cfg)

    def vm(self, acao, versao="", pacote=None, *extra) -> dict:
        args = [acao, "--usr", str(self.usr), "--usr-container", str(self.usr), "--docker", str(self.docker),
                "--python-container", sys.executable, "--node-container", sys.executable, "--espera-reinicio", "6"]
        if versao:
            args += ["--versao", versao]
        if pacote:
            args += ["--pacote", str(pacote)]
        import contextlib
        import io
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            scvm.main(args + list(extra))
        return json.loads(saida.getvalue().strip().splitlines()[-1])

    def implantar(self, versao, **kw) -> dict:
        p = self.pacote(versao, **kw)
        c = self.vm("conferir", versao, p)
        self.assertTrue(c["ok"], c)
        e = self.vm("estagiar", versao, p)
        if not e["ok"]:
            return e
        return self.vm("trocar", versao, p)

    @property
    def plugin(self) -> Path:
        return self.usr / "plugins" / "segundo_cerebro"

    @property
    def estado(self) -> Path:
        return self.usr / "segundo_cerebro"

    def test_primeira_instalacao_e_rollback_desativa(self):
        t = self.implantar(V1)
        self.assertTrue(t["ok"], t)
        self.assertEqual((self.plugin / ".versao").read_text().split()[0], V1)
        self.assertEqual((self.estado / "atual").read_text().strip(), V1)
        self.assertTrue((self.estado / "releases" / V1 / "server.js").is_file())
        self.assertTrue((self.estado / "releases" / V1 / ".next" / "static" / "chunks" / "a.css").is_file())
        self.assertTrue((self.estado / "vm" / "segundo_cerebro_vm.py").is_file(), "cópia do script para o rollback")
        self.assertTrue((self.usr / "plugins" / "outro" / "plugin.yaml").is_file(), "outros plugins intocados")
        s = self.vm("sondar")
        self.assertTrue(s["ok"], s)
        self.assertEqual(s["release"]["dono"], "matheus")
        antes = arvores(self.usr)
        r = self.vm("reverter")
        self.assertTrue(r["ok"], r)
        self.assertIsNone(r["plugin"])
        self.assertFalse(self.plugin.exists(), "primeira instalação revertida: plugin desligado (fora do lugar)")
        self.assertEqual((self.estado / "atual").read_text().strip(), "desativado")
        retirado = [p for p in (self.estado / "retirados").iterdir() if "revertido" in p.name]
        self.assertEqual(len(retirado), 1)
        self.assertTrue((retirado[0] / "plugin.yaml").is_file(), "o plugin revertido foi guardado, não apagado")
        self.assertTrue((self.estado / "releases" / V1 / "server.js").is_file(), "a release fica")
        self.assertGreaterEqual(len(arvores(self.usr)), len(antes) - 0, "nada apagado")
        self.assertFalse(self.vm("reverter")["ok"], "não reverte duas vezes o mesmo deploy")
        self.assertEqual(json.loads((self.usr / "memoria/decisoes/matheus.json").read_text()), {"decisoes": []})

    def test_segunda_versao_e_rollback_volta_a_anterior(self):
        self.assertTrue(self.implantar(V1)["ok"])
        self.assertTrue(self.implantar(V2)["ok"])
        self.assertIn("teste 2222", (self.plugin / "plugin.yaml").read_text())
        snaps = list((self.estado / "plugins-anteriores").iterdir())
        self.assertEqual(len(snaps), 1)
        self.assertIn("teste 1111", (snaps[0] / "plugin.yaml").read_text())
        antes = arvores(self.usr)
        r = self.vm("reverter")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["release"], V1)
        self.assertIn("teste 1111", (self.plugin / "plugin.yaml").read_text(), "volta o plugin anterior, não o do git")
        self.assertEqual((self.plugin / ".versao").read_text().split()[0], V1)
        self.assertEqual((self.estado / "atual").read_text().strip(), V1)
        self.assertTrue((snaps[0] / "plugin.yaml").is_file(), "o snapshot continua guardado")
        self.assertTrue((self.estado / "releases" / V2 / "server.js").is_file(), "a release desfeita fica")
        depois = arvores(self.usr)
        perdidos = {p for p in antes - depois if not p.startswith("plugins/segundo_cerebro/")}
        self.assertEqual(perdidos, set(), "nada apagado (o plugin desfeito foi para retirados/)")
        self.assertTrue(any("revertido" in p.name for p in (self.estado / "retirados").iterdir()))

    def test_estagio_falho_nao_troca(self):
        self.assertTrue(self.implantar(V1)["ok"])
        antes = (self.plugin / "plugin.yaml").read_text()
        e = self.implantar(V2, suite=SUITE_FALHA)
        self.assertFalse(e["ok"])
        self.assertIn("suíte", e["erro"])
        t = self.vm("trocar", V2, self.pacote(V2, suite=SUITE_FALHA))
        self.assertFalse(t["ok"])
        self.assertEqual((self.plugin / "plugin.yaml").read_text(), antes, "plugin no ar intocado")
        self.assertEqual((self.estado / "atual").read_text().strip(), V1)
        e = self.implantar(V2, quebrada=True)
        self.assertFalse(e["ok"])
        self.assertIn("release", e["erro"])
        self.assertFalse((self.estado / "releases" / V2).exists(), "release que não sobe não vai para releases/")
        self.assertEqual((self.estado / "atual").read_text().strip(), V1)

    def test_destinos_e_runtime_inseguros(self):
        p = self.pacote(V1)
        (self.usr / "plugins" / "segundo_cerebro").symlink_to(self.usr / "plugins" / "outro")
        self.assertTrue(any("link" in x for x in self.vm("conferir", V1, p)["problemas"]))
        (self.usr / "plugins" / "segundo_cerebro").unlink()
        (self.usr / "plugins" / "segundo_cerebro").mkdir()
        (self.usr / "plugins" / "segundo_cerebro" / "plugin.yaml").write_text("name: outra_coisa\n")
        self.assertTrue(any("outro conteúdo" in x for x in self.vm("conferir", V1, p)["problemas"]))
        (self.usr / "plugins" / "segundo_cerebro" / "plugin.yaml").write_text("name: segundo_cerebro\n")
        self.assertTrue(any("sem .versao" in x for x in self.vm("conferir", V1, p)["problemas"]), "instalado à mão")
        os.rename(self.usr / "plugins" / "segundo_cerebro", self.tmp / "tirado")
        self.config(node_versao="v18.19.0")
        self.assertTrue(any("runtime desconhecido" in x for x in self.vm("conferir", V1, p)["problemas"]))
        self.config(node_versao="")
        self.assertTrue(any("runtime desconhecido" in x for x in self.vm("conferir", V1, p)["problemas"]))
        self.config(node_versao="v22.22.0", rodando=False)
        self.assertTrue(any("não está rodando" in x for x in self.vm("conferir", V1, p)["problemas"]))
        self.config(rodando=True)
        self.assertTrue(self.vm("conferir", V1, p)["ok"])
        (p / "plugin" / "plugin.yaml").write_text("name: segundo_cerebro\n# alterado\n")
        self.assertTrue(any("corrompido" in x for x in self.vm("conferir", V1, p)["problemas"]))
        p = self.pacote(V1)
        (p / "release" / "extra.js").write_text("x")
        self.assertTrue(any("fora do manifesto" in x for x in self.vm("conferir", V1, p)["problemas"]))
        p = self.pacote(V1)
        self.assertTrue(any("é de" in x for x in self.vm("conferir", V2, p)["problemas"]), "pacote de outra versão")
        self.assertFalse(self.vm("conferir", "../x", p)["ok"])
        self.estado.mkdir()
        (self.estado / "atual").write_text("qualquer-coisa")
        self.assertTrue(any("release no ar desconhecida" in x for x in self.vm("conferir", V1, p)["problemas"]))

    def test_reiniciar_espera_o_agent_zero(self):
        self.config(curl={"/login": 0}, curl_depois={"/login": 200})
        r = self.vm("reiniciar")
        self.assertTrue(r["ok"], r)
        self.assertTrue(json.loads(self.cfg.read_text())["reiniciado"])
        self.config(reiniciado=False, curl={"/login": 0}, curl_depois={"/login": 0})
        self.assertFalse(self.vm("reiniciar")["ok"], "não voltou no prazo")


class TestFluxo(unittest.TestCase):
    """The orchestrator against a scripted VM (fake SSM)."""

    def rodar(self, respostas: dict, publico_ok=True, conhecidos=(V1,)):
        comandos = []

        def vm(cmd, timeout=600):
            comandos.append(cmd)
            acao = next(a for a in ("conferir", "estagiar", "trocar", "sondar", "reiniciar", "reverter") if f" {a} " in cmd + " ")
            fila = respostas[acao]
            return json.dumps(fila.pop(0) if len(fila) > 1 else fila[0])

        enviados = []
        try:
            sc._implantar_pacote(vm, lambda k, d: enviados.append(k), lambda a, b: a in conhecidos, lambda: "https://agente",
                                 lambda url: {"ok": publico_ok}, V2, b"pacote", "balde", agora=lambda: 1000)
            erro = None
        except SystemExit as exc:
            erro = str(exc)
        acoes = [next(a for a in ("conferir", "estagiar", "trocar", "sondar", "reiniciar", "reverter") if f" {a} " in c + " ")
                 for c in comandos]
        return erro, acoes, comandos, enviados

    OK = {"conferir": [{"ok": True, "problemas": [], "plugin": V1, "release": V1}], "estagiar": [{"ok": True}],
          "trocar": [{"ok": True}], "sondar": [{"ok": True, "gateway": 401}], "reiniciar": [{"ok": True}],
          "reverter": [{"ok": True}]}

    def r(self, **troca):
        return {k: list(troca.get(k, v)) for k, v in self.OK.items()}

    def test_sucesso(self):
        erro, acoes, comandos, enviados = self.rodar(self.r())
        self.assertIsNone(erro)
        self.assertEqual(acoes, ["conferir", "estagiar", "trocar", "sondar"])
        self.assertEqual(enviados, [f"tmp/implantar-segundo-cerebro-{V2[:8]}.tgz"])
        self.assertIn("s3://balde/", comandos[0])
        self.assertTrue(all(f"--versao {V2}" in c for c in comandos))

    def test_estagio_falho_nao_troca(self):
        erro, acoes, *_ = self.rodar(self.r(estagiar=[{"ok": False, "erro": "suíte"}]))
        self.assertIn("nada foi trocado", erro)
        self.assertEqual(acoes, ["conferir", "estagiar"])

    def test_vm_recusa_destino(self):
        erro, acoes, *_ = self.rodar(self.r(conferir=[{"ok": False, "problemas": ["runtime desconhecido: node"]}]))
        self.assertIn("runtime desconhecido", erro)
        self.assertEqual(acoes, ["conferir"])

    def test_versao_de_outra_sessao(self):
        erro, acoes, *_ = self.rodar(self.r(conferir=[{"ok": True, "problemas": [], "plugin": "9" * 40, "release": V1}]))
        self.assertIn("não está no seu histórico", erro)
        self.assertEqual(acoes, ["conferir"])
        erro, acoes, *_ = self.rodar(self.r(conferir=[{"ok": True, "problemas": [], "plugin": "", "release": "local-x"}]))
        self.assertIn("desconhecida", erro)

    def test_primeira_instalacao_reinicia_uma_vez(self):
        erro, acoes, *_ = self.rodar(self.r(conferir=[{"ok": True, "problemas": [], "plugin": "", "release": ""}],
                                            sondar=[{"ok": False, "gateway": 404}, {"ok": True, "gateway": 401}]))
        self.assertIsNone(erro)
        self.assertEqual(acoes, ["conferir", "estagiar", "trocar", "sondar", "reiniciar", "sondar"])

    def test_sonda_falha_reverte_sozinho(self):
        erro, acoes, comandos, _ = self.rodar(self.r(sondar=[{"ok": False, "gateway": 401, "release": {"ok": False}}]))
        self.assertIn("revertido automaticamente", erro)
        self.assertEqual(acoes, ["conferir", "estagiar", "trocar", "sondar", "reverter"])
        self.assertIn("--automatico", comandos[-1])
        erro, acoes, *_ = self.rodar(self.r(sondar=[{"ok": False, "gateway": 404}, {"ok": False, "gateway": 404}]))
        self.assertEqual(acoes, ["conferir", "estagiar", "trocar", "sondar", "reiniciar", "sondar", "reverter"])

    def test_publico_falha_reverte(self):
        erro, acoes, *_ = self.rodar(self.r(), publico_ok=False)
        self.assertIn("revertido automaticamente", erro)
        self.assertEqual(acoes[-1], "reverter")

    def test_rollback_cli(self):
        comandos = []
        sc.reverter(lambda c, t=600: comandos.append(c) or json.dumps({"ok": True, "plugin": "snap", "release": V1}))
        self.assertIn("/opt/a0/usr/segundo_cerebro/vm/segundo_cerebro_vm.py reverter", comandos[0])
        with self.assertRaises(SystemExit):
            sc.reverter(lambda c, t=600: json.dumps({"ok": False, "erro": "nada para reverter"}))


if __name__ == "__main__":
    unittest.main(verbosity=1)
