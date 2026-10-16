#!/usr/bin/env python3
"""Each guest's own isolated computer (16/10, Matheus: guests may use a terminal, run code and edit files, "precisa ser
isolado, de forma alguma acessar nada meu").

The agent's own terminal runs inside the agent's container, next to everything of Matheus's, so a guest never gets it.
Instead each guest has a separate Docker container, caixa-<login>:
- nothing of the agent mounted: only /opt/caixas/<login> (the guest's own folder) as its home;
- its own network "caixas": internet yes, but no host (model proxy, bridge, this service), no private ranges and no
  cloud metadata (firewall.sh); no capabilities, no new privileges, not root; memory, CPU and process limits;
- started on demand, stopped after IDLE_S without use; a home over DISCO_MAX bytes refuses new commands.
The agent reaches this service on host port 8790 with the secret in /opt/a0/usr/caixa/segredo.txt (the agent's
container sees it; the guests' containers do not). Files go in only from the guest's own folders and come out only into
the guest's project folder.
"""

import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CONVIDADOS = ("ilia", "will")  # same list as login_usuarios/helpers/convidados.py (a test checks)
PORTA = 8790
IMAGEM = "node:22-bookworm"  # Node, Python 3, git, curl, build tools; already on the VM
REDE = "caixas"
CASAS = Path("/opt/caixas")
USR_HOST = Path("/opt/a0/usr")
USR_A0 = "/a0/usr"
SEGREDO = USR_HOST / "caixa" / "segredo.txt"
HOME = "/home/node"
UID = "1000:1000"
LIMITES = ["--memory", "1g", "--memory-swap", "1g", "--cpus", "1", "--pids-limit", "256"]
TEMPO_MAX = 180
SAIDA_MAX = 8000
ARQUIVO_MAX = 25 * 1024 * 1024
DISCO_MAX = 3 * 1024 ** 3
IDLE_S = 30 * 60
_LOGIN = re.compile(r"^[a-z0-9_-]{1,32}$")
_USO: dict = {}
_TRAVA = threading.Lock()


class Recusa(Exception):
    pass


def log(msg: str) -> None:
    print(f"caixa_convidados: {msg}", flush=True)


def docker(*args: str, timeout: int = 120, entrada: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, timeout=timeout, input=entrada)


def conferir_login(login: str) -> str:
    login = str(login or "").strip().lower()
    if not _LOGIN.match(login) or login not in CONVIDADOS:
        raise Recusa("só convidados têm caixa")
    return login


def nome(login: str) -> str:
    return f"caixa-{login}"


def argumentos_run(login: str) -> list:
    """The `docker run` of a guest's box (kept in one place so a test can read every flag)."""
    # public DNS: the VPC's resolver is in a private range the box may not reach
    return ["run", "-d", "--name", nome(login), "--hostname", f"caixa-{login}", "--network", REDE,
            "--dns", "1.1.1.1", "--dns", "8.8.8.8",
            *LIMITES, "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--user", UID,
            "-v", f"{CASAS / login}:{HOME}", "-w", HOME, "-e", f"HOME={HOME}",
            "-e", "PIP_BREAK_SYSTEM_PACKAGES=1", "-e", "PIP_USER=1", "-e", f"PATH={HOME}/.local/bin:/usr/local/sbin:"
            "/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", "--restart", "no", IMAGEM, "sleep", "infinity"]


def garantir_rede() -> None:
    if docker("network", "inspect", REDE).returncode:
        r = docker("network", "create", "--driver", "bridge", "-o", "com.docker.network.bridge.enable_icc=false", REDE)
        if r.returncode:
            raise Recusa(f"rede das caixas não criada: {r.stderr.decode()[:200]}")
    r = subprocess.run(["/opt/agentepessoal/firewall.sh"], capture_output=True, timeout=60)
    if r.returncode or not isolada():  # never run a guest's box without its firewall
        raise Recusa("o isolamento de rede das caixas falhou; nada foi rodado")


def regras_isolamento(subrede: str) -> list:
    return [["INPUT", "-s", subrede, "-j", "DROP"]] + [
        ["DOCKER-USER", "-s", subrede, "-d", d, "-j", "DROP"]
        for d in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16", "100.64.0.0/10")]


def isolada() -> bool:
    """Every isolation rule of the boxes' network is in place (checked, not assumed)."""
    subrede = docker("network", "inspect", REDE, "-f", "{{range .IPAM.Config}}{{.Subnet}}{{end}}").stdout.decode().strip()
    return bool(subrede) and all(subprocess.run(["iptables", "-C", *regra], capture_output=True).returncode == 0
                                 for regra in regras_isolamento(subrede))


def garantir_caixa(login: str) -> None:
    with _TRAVA:
        casa = CASAS / login
        casa.mkdir(parents=True, exist_ok=True)
        os.chown(casa, 1000, 1000)
        os.chmod(casa, 0o700)
        estado = docker("inspect", "-f", "{{.State.Running}}", nome(login))
        if estado.returncode == 0 and estado.stdout.decode().strip() == "true":
            if not isolada():  # e.g. rules lost after a docker restart: stop the box rather than run unprotected
                docker("stop", "-t", "2", nome(login))
                garantir_rede()
                docker("start", nome(login))
            return
        garantir_rede()
        if estado.returncode == 0:
            r = docker("start", nome(login))
        else:
            r = docker(*argumentos_run(login), timeout=600)
        if r.returncode:
            raise Recusa(f"a caixa não subiu: {r.stderr.decode()[:300]}")
        log(f"caixa de {login} ligada")


def tamanho(caminho: Path) -> int:
    r = subprocess.run(["du", "-sb", str(caminho)], capture_output=True, timeout=60)
    try:
        return int(r.stdout.split()[0])
    except (IndexError, ValueError):
        return 0


def rodar(login: str, comando: str, tempo: int = 60) -> dict:
    login = conferir_login(login)
    comando = str(comando or "")
    if not comando.strip():
        raise Recusa("comando vazio")
    if tamanho(CASAS / login) > DISCO_MAX:
        raise Recusa(f"a pasta da caixa passou de {DISCO_MAX // 1024 ** 3} GB: apague arquivos antes (rm, pip cache purge)")
    garantir_caixa(login)
    _USO[login] = time.time()
    tempo = max(5, min(int(tempo or 60), TEMPO_MAX))
    try:
        r = docker("exec", "-u", UID, "-w", HOME, nome(login), "timeout", "-k", "5", str(tempo), "bash", "-lc", comando,
                   timeout=tempo + 30)
        saida = (r.stdout + (b"\n[stderr]\n" + r.stderr if r.stderr else b"")).decode("utf-8", "replace")
        codigo = r.returncode
    except subprocess.TimeoutExpired:
        saida, codigo = "", 124
    if codigo == 124:
        saida += f"\n[parado: passou de {tempo} s]"
    if len(saida) > SAIDA_MAX:
        saida = "[…início cortado…]\n" + saida[-SAIDA_MAX:]
    return {"codigo": codigo, "saida": saida}


def _dentro(caminho: Path, raizes: tuple) -> bool:
    real = caminho.resolve()
    return any(real == r.resolve() or r.resolve() in real.parents for r in raizes)


def origem_permitida(login: str, caminho_a0: str) -> Path:
    """A file the guest sent (or the agent made for them), as the agent names it (/a0/usr/...), on the host."""
    caminho_a0 = str(caminho_a0 or "")
    if not caminho_a0.startswith(USR_A0 + "/"):
        raise Recusa("só arquivos da pessoa (/a0/usr/whatsapp/<login>/ ou /a0/usr/projects/convidado-<login>/)")
    host = USR_HOST / caminho_a0[len(USR_A0) + 1:]
    raizes = (USR_HOST / "whatsapp" / login, USR_HOST / "projects" / f"convidado-{login}")
    if not _dentro(host, raizes) or not host.is_file() or host.is_symlink():
        raise Recusa("esse arquivo não é desta pessoa (ou não existe)")
    if host.stat().st_size > ARQUIVO_MAX:
        raise Recusa("arquivo grande demais (máximo 25 MB)")
    return host


def _nome_seguro(n: str) -> str:
    return (re.sub(r"[^\w.\-]", "_", n).lstrip(".") or "arquivo")[:120]


def enviar(login: str, origem: str) -> dict:
    """Into the box with `docker cp`: paths resolve inside the container, so a link the guest made can't point the
    host's root at anything outside (writing into the guest's folder directly could)."""
    login = conferir_login(login)
    host = origem_permitida(login, origem)
    garantir_caixa(login)
    _USO[login] = time.time()
    alvo = f"{HOME}/entrada/{_nome_seguro(host.name)}"
    docker("exec", "-u", UID, nome(login), "mkdir", "-p", f"{HOME}/entrada")
    with tempfile.TemporaryDirectory() as tmp:  # a copy owned by the box's user, so -a lands it as theirs
        copia = Path(tmp) / "f"
        shutil.copyfile(host, copia)
        os.chown(copia, 1000, 1000)
        r = docker("cp", "-a", str(copia), f"{nome(login)}:{alvo}")
    if r.returncode:
        raise Recusa(f"não copiei para a caixa: {r.stderr.decode()[:200]}")
    return {"na_caixa": alvo}


def trazer(login: str, caminho: str) -> dict:
    """A file of the box -> the guest's project folder (/a0/usr/projects/convidado-<login>/da_caixa/), for sending.
    Read with `docker cp … -` (a tar resolved inside the container); only one regular file is accepted."""
    import io
    import tarfile

    login = conferir_login(login)
    caminho = str(caminho or "").strip()
    if not caminho.startswith("/"):
        caminho = f"{HOME}/{caminho}"
    if caminho != HOME and not caminho.startswith(HOME + "/") or "/../" in caminho + "/":
        raise Recusa(f"use um caminho dentro de {HOME}")
    garantir_caixa(login)
    _USO[login] = time.time()
    info = docker("exec", "-u", UID, nome(login), "stat", "-c", "%s|%F", caminho).stdout.decode().strip().split("|")
    if len(info) != 2 or info[1] != "regular file":
        raise Recusa(f"{caminho} não é um arquivo na caixa (para pasta, compacte antes com zip/tar)")
    if int(info[0]) > ARQUIVO_MAX:
        raise Recusa("arquivo grande demais (máximo 25 MB)")
    r = docker("cp", f"{nome(login)}:{caminho}", "-", timeout=120)
    if r.returncode:
        raise Recusa(f"não achei {caminho} na caixa")
    with tarfile.open(fileobj=io.BytesIO(r.stdout)) as tar:
        membros = tar.getmembers()
        if len(membros) != 1 or not membros[0].isfile():
            raise Recusa("traga um arquivo só (não uma pasta nem um atalho); para pasta, compacte antes (zip/tar)")
        if membros[0].size > ARQUIVO_MAX:
            raise Recusa("arquivo grande demais (máximo 25 MB)")
        dados = tar.extractfile(membros[0]).read()
    pasta = USR_HOST / "projects" / f"convidado-{login}" / "da_caixa"
    pasta.mkdir(parents=True, exist_ok=True)
    alvo = pasta / _nome_seguro(Path(membros[0].name).name)
    with tempfile.NamedTemporaryFile(dir=pasta, delete=False) as tmp:
        tmp.write(dados)
    os.replace(tmp.name, alvo)
    return {"arquivo": f"{USR_A0}/projects/convidado-{login}/da_caixa/{alvo.name}"}


def desligar_paradas(agora: float | None = None) -> list:
    agora = agora or time.time()
    paradas = []
    for login in CONVIDADOS:
        if login in _USO and agora - _USO[login] > IDLE_S:
            if docker("stop", "-t", "5", nome(login)).returncode == 0:
                paradas.append(login)
                log(f"caixa de {login} desligada (sem uso)")
            _USO.pop(login, None)
    return paradas


def segredo() -> str:
    if not SEGREDO.exists():
        SEGREDO.parent.mkdir(parents=True, exist_ok=True)
        SEGREDO.write_text(secrets.token_urlsafe(32))
        os.chmod(SEGREDO, 0o600)
    return SEGREDO.read_text().strip()


ACOES = {"rodar": lambda d: rodar(d.get("login"), d.get("comando"), d.get("tempo") or 60),
         "enviar": lambda d: enviar(d.get("login"), d.get("origem")),
         "trazer": lambda d: trazer(d.get("login"), d.get("caminho"))}


class Pedido(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _responder(self, codigo: int, corpo: dict) -> None:
        dados = json.dumps(corpo, ensure_ascii=False).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def do_POST(self):
        import hmac

        if not hmac.compare_digest(self.headers.get("X-Segredo", ""), segredo()):
            return self._responder(403, {"erro": "sem acesso"})
        acao = self.path.strip("/")
        if acao not in ACOES:
            return self._responder(404, {"erro": "ação desconhecida"})
        try:
            dados = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length") or 0), 200_000)) or b"{}")
            return self._responder(200, ACOES[acao](dados))
        except Recusa as exc:
            return self._responder(200, {"erro": str(exc)})
        except Exception as exc:
            log(f"{acao}: {type(exc).__name__}: {exc}")
            return self._responder(500, {"erro": "falha na caixa; tente de novo"})


def ciclo_desligar() -> None:
    while True:
        time.sleep(300)
        try:
            desligar_paradas()
        except Exception as exc:
            log(f"desligar: {exc}")


def main() -> None:
    segredo()
    CASAS.mkdir(parents=True, exist_ok=True)
    os.chmod(CASAS, 0o711)
    threading.Thread(target=ciclo_desligar, daemon=True).start()
    # on the docker bridge's gateway only: the agent's container reaches it as host.docker.internal
    ThreadingHTTPServer(("172.17.0.1", PORTA), Pedido).serve_forever()


if __name__ == "__main__":
    main()
