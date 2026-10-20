"""VM side of the Segundo Cérebro deploy (runs as root on the host, called by segundo_cerebro.py through SSM).
Prints one JSON line. Nothing is ever deleted: what leaves its place is renamed into a kept folder.

    conferir   destinations are what we expect (or absent), container running, node >= 20.9 inside it
    estagiar   copy to a staging area, run the plugin suite and a real start of the release inside the container
    trocar     keep the current plugin as a snapshot, put the staged plugin and release in place, point `atual`
    sondar     gateway answers 401 without a session, Agent Zero login still answers, the live release is healthy
    reiniciar  restart the existing container (only when the gateway is not registered yet: first install)
    reverter   put back the plugin snapshot and the release that ran before the last `trocar`; on a first install
               the plugin is renamed away (disabled) and `atual` becomes "desativado"

Layout under <usr> (/opt/a0/usr on the host = /a0/usr in the container):
    plugins/segundo_cerebro/            the live plugin (.versao = commit)
    segundo_cerebro/atual               current release name;  releases/<commit>/server.js ...
    segundo_cerebro/anterior.json       what `reverter` puts back
    segundo_cerebro/plugins-anteriores/ plugin snapshots;  retirados/ what reverter and re-stages moved away
    segundo_cerebro/vm/                 a copy of this script for --rollback
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

NOME = "segundo_cerebro"
VERSAO = re.compile(r"^[0-9a-f]{40}$")
MANUAL = re.compile(r"^local-[0-9a-f]{12}$")  # a `preparar` package someone installed by hand (18/10, before the deploy)
NODE_MINIMO = (20, 9)


class Recusa(Exception):
    pass


def _agora() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def _real_dir(p: Path) -> bool:
    try:
        return stat.S_ISDIR(os.lstat(p).st_mode)
    except OSError:
        return False


def _existe(p: Path) -> bool:
    return os.path.lexists(p)


def _escrever(p: Path, texto: str) -> None:
    """Atomic replace of a small state file (write + rename)."""
    tmp = p.with_name(f".{p.name}.{os.getpid()}.tmp")
    tmp.write_text(texto, encoding="utf-8")
    os.replace(tmp, p)


class Vm:
    def __init__(self, a):
        self.a = a
        self.usr = Path(a.usr)
        self.usr_c = a.usr_container
        self.plugin = self.usr / "plugins" / NOME
        self.estado = self.usr / NOME
        self.pacote = Path(a.pacote) if a.pacote else Path(__file__).resolve().parents[1]
        self.versao = a.versao or ""

    # ---- helpers ----
    def c(self, p: Path) -> str:
        """Host path under usr -> the same path inside the container."""
        return self.usr_c + "/" + str(p.relative_to(self.usr)) if p != self.usr else self.usr_c

    def docker(self, *args: str, entrada: str | None = None, timeout: int = 600) -> subprocess.CompletedProcess:
        return subprocess.run([self.a.docker, *args], input=entrada, capture_output=True, text=True, timeout=timeout)

    def no_container(self, *cmd: str, entrada: str | None = None, env: dict | None = None, timeout: int = 600):
        extra = [x for k, v in (env or {}).items() for x in ("-e", f"{k}={v}")]
        return self.docker("exec", *(["-i"] if entrada is not None else []), *extra, self.a.container, *cmd,
                           entrada=entrada, timeout=timeout)

    def http(self, caminho: str) -> int:
        r = self.no_container("curl", "-s", "-o", "/dev/null", "-m", "20", "-w", "%{http_code}",
                              f"http://127.0.0.1:80{caminho}")
        return int(r.stdout.strip()) if r.stdout.strip().isdigit() else 0

    def cache_reset(self) -> None:
        self.no_container("curl", "-s", "-m", "20", "-X", "POST", "http://127.0.0.1:80/api/cache_reset")

    def historico(self, texto: str) -> None:
        if not _real_dir(self.estado):
            return
        with open(self.estado / "historico.log", "a", encoding="utf-8") as f:
            f.write(f"{_agora()} {texto}\n")

    def versao_plugin(self) -> str:
        v = self.plugin / ".versao"
        return v.read_text().split()[0] if _real_dir(self.plugin) and v.is_file() and v.read_text().split() else ""

    def atual(self) -> str:
        p = self.estado / "atual"
        return p.read_text().strip() if p.is_file() and not p.is_symlink() else ""

    def _hashes(self, raiz: Path) -> dict:
        return {str(f.relative_to(raiz)): hashlib.sha256(f.read_bytes()).hexdigest() for f in raiz.rglob("*")
                if f.is_file() and not f.is_symlink() and "__pycache__" not in f.parts and f.name != ".versao"}

    def manual_adotavel(self) -> bool:
        """--adotar-manual (20/10): the hand-installed state is taken as the starting point only when the release is a
        `local-<12 hex>` one kept in releases/ and the live plugin, without .versao, has exactly the files of the plugin
        in this package (the same git code). Anything else stays refused."""
        atual = self.atual()
        return bool(getattr(self.a, "adotar_manual", False) and MANUAL.match(atual)
                    and _real_dir(self.estado / "releases" / atual) and _real_dir(self.plugin)
                    and not self.versao_plugin() and _real_dir(self.pacote / "plugin")
                    and self._hashes(self.plugin) == self._hashes(self.pacote / "plugin"))

    # ---- conferir ----
    def problemas_destino(self) -> list:
        p = []
        if not _real_dir(self.usr) or not _real_dir(self.usr / "plugins"):
            return [f"{self.usr}/plugins não é a pasta esperada"]
        if _existe(self.plugin):
            if not _real_dir(self.plugin):
                p.append("o destino do plugin existe e não é uma pasta comum (link?)")
            elif not re.search(rf"(?m)^name:\s*{NOME}\s*$", (self.plugin / "plugin.yaml").read_text()
                               if (self.plugin / "plugin.yaml").is_file() else ""):
                p.append("o destino do plugin tem outro conteúdo (plugin.yaml não é segundo_cerebro)")
        if _existe(self.estado):
            if not _real_dir(self.estado):
                p.append(f"{self.estado} existe e não é uma pasta comum")
            else:
                for f in self.estado.iterdir():
                    if f.is_symlink():
                        p.append(f"link simbólico em {f}")
                if _existe(self.estado / "atual") and not (self.estado / "atual").is_file():
                    p.append("o ponteiro atual não é um arquivo comum")
                atual = self.atual()
                adotar = self.manual_adotavel()
                if atual and atual != "desativado" and not VERSAO.match(atual) and not adotar:
                    p.append(f"release no ar desconhecida: {atual[:30]!r}")
                if self.versao and _existe(self.estado / "releases" / self.versao):
                    p.append("esta versão já está instalada em releases/ (nada a fazer; ou faça um commit novo)")
        v = self.versao_plugin()
        if v and not VERSAO.match(v):
            p.append(f"plugin no ar de versão desconhecida: {v[:30]!r}")
        if _real_dir(self.plugin) and not v and not self.manual_adotavel():
            p.append("plugin no ar sem .versao (instalado à mão?): confira antes")
        return p

    def problemas_pacote(self) -> list:
        m = self.pacote / "MANIFESTO.json"
        if not m.is_file():
            return ["pacote sem MANIFESTO.json"]
        manifesto = json.loads(m.read_text())
        if manifesto.get("versao") != self.versao or not VERSAO.match(self.versao):
            return [f"o pacote é de {manifesto.get('versao')!r}, não de {self.versao!r}"]
        for rel, h in manifesto["arquivos"].items():
            f = self.pacote / rel
            if f.is_symlink() or not f.is_file() or hashlib.sha256(f.read_bytes()).hexdigest() != h:
                return [f"pacote corrompido em {rel}"]
        listados = set(manifesto["arquivos"]) | {"MANIFESTO.json"}
        for f in self.pacote.rglob("*"):
            if f.is_file() and not f.is_symlink() and str(f.relative_to(self.pacote)) not in listados:
                return [f"arquivo fora do manifesto: {f.relative_to(self.pacote)}"]
        for f in self.pacote.rglob("*"):
            if f.is_symlink():
                alvo = os.readlink(f)
                if os.path.isabs(alvo) or not (f.parent / alvo).resolve().is_relative_to(self.pacote.resolve()):
                    return [f"link inseguro no pacote: {f.relative_to(self.pacote)}"]
        if not (self.pacote / "release" / "server.js").is_file() or not (self.pacote / "plugin" / "plugin.yaml").is_file():
            return ["pacote incompleto (release/server.js ou plugin/plugin.yaml)"]
        return []

    def problemas_runtime(self) -> tuple[list, str]:
        r = self.docker("inspect", "-f", "{{.State.Running}}", self.a.container)
        if r.returncode or r.stdout.strip() != "true":
            return [f"container {self.a.container} não está rodando"], ""
        if self.no_container("test", "-d", f"{self.usr_c}/plugins").returncode:
            return [f"o container não vê {self.usr_c}/plugins"], ""
        if self.no_container("test", "-x", self.a.python_container).returncode:
            return [f"runtime desconhecido: {self.a.python_container} ausente no container"], ""
        r = self.no_container(self.a.node_container, "--version")
        m = re.fullmatch(r"v(\d+)\.(\d+)\.\d+", r.stdout.strip())
        if r.returncode or not m or (int(m.group(1)), int(m.group(2))) < NODE_MINIMO:
            return [f"runtime desconhecido: node no container {r.stdout.strip()[:20] or 'ausente'} (precisa >= 20.9)"], ""
        return [], r.stdout.strip()

    def conferir(self) -> dict:
        problemas = self.problemas_pacote() + self.problemas_destino()
        runtime, node = self.problemas_runtime()
        problemas += runtime
        return {"ok": not problemas, "problemas": problemas, "plugin": self.versao_plugin(), "release": self.atual(),
                "node": node}

    # ---- estagiar ----
    def estagio(self) -> Path:
        return self.estado / "estagio" / self.versao

    def smoke(self, plugin_dir: Path, release: Path, logs: Path) -> dict:
        """Start the release for real inside the container (own port, own bearer), check 401/200/page/asset, stop.
        Prints no data: only statuses and the owner field."""
        codigo = r'''
import http.client, importlib.util, json, re, sys
from pathlib import Path
plugin, release, logs, dados, node = sys.argv[1:6]
s = importlib.util.spec_from_file_location("sc_processo_sonda", plugin + "/helpers/processo.py")
m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
p = m.Processo(raiz_estado=Path(logs), raiz_dados=dados, node=node or None, prazo=40, espera_falha=0)
p.release_atual = lambda: Path(release)
r = {"ok": False}
try:
    porta, token = p.garantir()
    def get(caminho, auth=True):
        c = http.client.HTTPConnection("127.0.0.1", porta, timeout=20)
        h = {"Host": "127.0.0.1:%d" % porta, "Accept-Encoding": "identity"}
        if auth:
            h["Authorization"] = "Bearer " + token
        c.request("GET", caminho, headers=h); x = c.getresponse(); corpo = x.read(); c.close()
        return x.status, x.getheader("Content-Type") or "", corpo
    st, _, corpo = get("/api/segundo-cerebro")
    r["api"] = st
    r["dono"] = json.loads(corpo).get("owner") if st == 200 else None
    r["api_sem_bearer"] = get("/api/segundo-cerebro", auth=False)[0]
    st, tipo, html = get("/segundo-cerebro", auth=False)
    r["pagina"], r["pagina_html"] = st, tipo.startswith("text/html")
    assets = re.findall(r'/_next/static/[A-Za-z0-9_~./-]+\.(?:css|js)', html.decode("utf-8", "replace"))
    r["asset"] = get(assets[0], auth=False)[0] if assets else 0
    r["ok"] = (r["api"] == 200 and r["dono"] == "matheus" and r["api_sem_bearer"] == 401 and r["pagina"] == 200
               and r["pagina_html"] and r["asset"] == 200)
except Exception as exc:
    r["erro"] = type(exc).__name__ + ": " + str(exc)[:200]
finally:
    p.parar()
print(json.dumps(r))
'''
        logs.mkdir(parents=True, exist_ok=True)
        node = "" if self.a.node_container == "node" else self.a.node_container
        r = self.no_container(self.a.python_container, "-", self.c(plugin_dir), self.c(release), self.c(logs),
                              self.usr_c, node, entrada=codigo, timeout=180)
        try:
            return json.loads(r.stdout.strip().splitlines()[-1])
        except (IndexError, ValueError):
            return {"ok": False, "erro": (r.stderr or r.stdout)[-300:]}

    def suite(self, plugin_dir: Path) -> dict:
        codigo = ("import asyncio, importlib.util, json, sys\n"
                  "s = importlib.util.spec_from_file_location('estagio_sc', sys.argv[1] + '/tests/suite.py')\n"
                  "m = importlib.util.module_from_spec(s); s.loader.exec_module(m)\n"
                  "r = asyncio.run(m.Suite().rodar(''))\n"
                  "print(json.dumps({'total': r['total'], 'passou': r['passou'],"
                  " 'falhas': [x['teste'] for x in r['resultados'] if not x['ok']]}))\n")
        r = self.no_container("sh", "-c", f"cd /a0 2>/dev/null; exec {self.a.python_container} - {self.c(plugin_dir)}",
                              entrada=codigo, env={"ESTAGIO": "1"}, timeout=600)
        try:
            return json.loads(r.stdout.strip().splitlines()[-1])
        except (IndexError, ValueError):
            return {"total": 0, "passou": 0, "falhas": [(r.stderr or r.stdout)[-300:]]}

    def estagiar(self) -> dict:
        c = self.conferir()
        if not c["ok"]:
            return {"ok": False, "erro": "; ".join(c["problemas"])}
        for d in (self.estado, self.estado / "releases", self.estado / "plugins-anteriores", self.estado / "retirados"):
            d.mkdir(mode=0o755, exist_ok=True)
        e = self.estagio()
        if _existe(e):  # an earlier attempt: keep it aside, never delete
            os.rename(e, self.estado / "retirados" / f"{_agora()}-estagio-{self.versao[:8]}")
        (e / "estado" / "releases").mkdir(parents=True)
        shutil.copytree(self.pacote / "plugin", e / "plugin", symlinks=True)
        shutil.copytree(self.pacote / "release", e / "estado" / "releases" / self.versao, symlinks=True)
        suite = self.suite(e / "plugin")
        if suite["falhas"] or not suite["total"] or suite["passou"] != suite["total"]:
            return {"ok": False, "erro": f"suíte do plugin no estágio: {suite['passou']}/{suite['total']} {suite['falhas'][:3]}"}
        sonda = self.smoke(e / "plugin", e / "estado" / "releases" / self.versao, e / "sonda")
        if not sonda.get("ok"):
            return {"ok": False, "erro": f"a release não subiu saudável no estágio: {sonda}"}
        _escrever(e / "ESTAGIO_OK", self.versao)
        return {"ok": True, "testes": f"{suite['passou']}/{suite['total']}", "sonda": sonda}

    # ---- trocar ----
    def trocar(self) -> dict:
        e = self.estagio()
        if not (e / "ESTAGIO_OK").is_file() or (e / "ESTAGIO_OK").read_text().strip() != self.versao:
            return {"ok": False, "erro": "sem estágio aprovado desta versão: nada foi trocado"}
        problemas = self.problemas_destino()
        if problemas:
            return {"ok": False, "erro": "; ".join(problemas)}
        ts, feito = _agora(), []
        anterior = {"release": self.atual() or None, "plugin_snapshot": None, "plugin_versao": self.versao_plugin() or None,
                    "versao_nova": self.versao, "em": ts}
        try:
            if _existe(self.plugin):
                snap = f"{ts}-{(anterior['plugin_versao'] or 'sem-versao')[:8]}"
                os.rename(self.plugin, self.estado / "plugins-anteriores" / snap)
                feito.append((self.estado / "plugins-anteriores" / snap, self.plugin))
                anterior["plugin_snapshot"] = snap
            destino_release = self.estado / "releases" / self.versao
            os.rename(e / "estado" / "releases" / self.versao, destino_release)
            feito.append((destino_release, e / "estado" / "releases" / self.versao))
            os.rename(e / "plugin", self.plugin)
            feito.append((self.plugin, e / "plugin"))
            _escrever(self.plugin / ".versao", f"{self.versao} {ts}\n")
            (self.estado / "vm").mkdir(exist_ok=True)
            copia = self.estado / "vm" / "segundo_cerebro_vm.py"
            if copia.exists():
                os.rename(copia, self.estado / "retirados" / f"{ts}-segundo_cerebro_vm.py")
            shutil.copy2(self.pacote / "vm" / "segundo_cerebro_vm.py", copia)
            _escrever(self.estado / "anterior.json", json.dumps(anterior, indent=1))
            _escrever(self.estado / "atual", self.versao + "\n")
        except OSError as exc:
            for de, para in reversed(feito):  # undo the renames already done, in reverse
                try:
                    os.rename(de, para)
                except OSError:
                    pass
            return {"ok": False, "erro": f"troca desfeita: {type(exc).__name__}: {exc}"}
        self.historico(f"trocar {self.versao} anterior={anterior}")
        self.cache_reset()
        return {"ok": True, "anterior": anterior}

    # ---- sondar / reiniciar ----
    def sondar(self) -> dict:
        r = {"gateway": self.http("/segundo-cerebro"), "api": self.http("/api/segundo-cerebro"), "login": self.http("/login")}
        rel = self.atual()
        if VERSAO.match(rel) and _real_dir(self.estado / "releases" / rel) and _real_dir(self.plugin):
            r["release"] = self.smoke(self.plugin, self.estado / "releases" / rel, self.estado / "sonda" / _agora())
        else:
            r["release"] = {"ok": False, "erro": "sem release/plugin no ar"}
        r["ok"] = r["gateway"] == 401 and r["api"] == 401 and r["login"] in (200, 302) and bool(r["release"].get("ok"))
        return r

    def reiniciar(self) -> dict:
        r = self.docker("restart", self.a.container, timeout=180)
        if r.returncode:
            return {"ok": False, "erro": r.stderr[-300:]}
        for _ in range(int(self.a.espera_reinicio / 3)):
            if self.http("/login") in (200, 302):
                self.historico("reiniciar ok")
                return {"ok": True}
            time.sleep(3)
        return {"ok": False, "erro": "o Agent Zero não voltou a responder no prazo"}

    # ---- reverter ----
    def reverter(self) -> dict:
        arq = self.estado / "anterior.json"
        if not arq.is_file():
            return {"ok": False, "erro": "nada para reverter (sem anterior.json)"}
        anterior = json.loads(arq.read_text())
        if anterior.get("revertido"):
            return {"ok": False, "erro": f"o último deploy já foi revertido em {anterior['revertido']}"}
        if self.versao and anterior.get("versao_nova") != self.versao:
            return {"ok": False, "erro": f"o último deploy é {anterior.get('versao_nova')}, não {self.versao}"}
        snap = anterior.get("plugin_snapshot")
        if snap and not _real_dir(self.estado / "plugins-anteriores" / snap):
            return {"ok": False, "erro": f"snapshot {snap} não encontrado: nada foi mudado"}
        rel = anterior.get("release")
        if rel and not _real_dir(self.estado / "releases" / rel):
            return {"ok": False, "erro": f"release anterior {rel} não encontrada: nada foi mudado"}
        ts = _agora()
        (self.estado / "retirados").mkdir(exist_ok=True)
        if snap:  # prepare the copy first, so the live plugin is out of place only for two renames
            preparo = self.estado / "estagio" / f"reverter-{ts}"
            preparo.parent.mkdir(exist_ok=True)
            shutil.copytree(self.estado / "plugins-anteriores" / snap, preparo, symlinks=True)
        if _existe(self.plugin):
            os.rename(self.plugin, self.estado / "retirados" / f"{ts}-revertido-{(self.versao_plugin() or 'x')[:8]}")
        if snap:
            os.rename(preparo, self.plugin)
        _escrever(self.estado / "atual", (rel or "desativado") + "\n")
        _escrever(arq, json.dumps({**anterior, "revertido": ts}, indent=1))
        self.historico(f"reverter para plugin={snap} release={rel} ({'automático' if self.a.automatico else 'manual'})")
        self.cache_reset()
        return {"ok": True, "plugin": snap, "release": rel, "gateway": self.http("/segundo-cerebro")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("acao", choices=["conferir", "estagiar", "trocar", "sondar", "reiniciar", "reverter"])
    ap.add_argument("--versao", default="")
    ap.add_argument("--pacote", default="")
    ap.add_argument("--usr", default="/opt/a0/usr")
    ap.add_argument("--usr-container", default="/a0/usr")
    ap.add_argument("--docker", default="docker")
    ap.add_argument("--container", default="agent-zero")
    ap.add_argument("--python-container", default="/opt/venv-a0/bin/python")
    ap.add_argument("--node-container", default="node")
    ap.add_argument("--espera-reinicio", type=int, default=240)
    ap.add_argument("--automatico", action="store_true")
    ap.add_argument("--adotar-manual", action="store_true")
    a = ap.parse_args(argv)
    if a.versao and not VERSAO.match(a.versao):
        print(json.dumps({"ok": False, "erro": "versão inválida"}))
        return 1
    if a.acao not in ("reverter", "sondar", "reiniciar") and not a.versao:
        print(json.dumps({"ok": False, "erro": "--versao é obrigatória"}))
        return 1
    try:
        r = getattr(Vm(a), a.acao)()
    except Exception as exc:
        r = {"ok": False, "erro": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(r, ensure_ascii=False))
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
