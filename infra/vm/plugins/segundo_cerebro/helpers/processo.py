"""The Segundo Cérebro Next server (standalone `node server.js`), started by the gateway on first use.

- binds only 127.0.0.1, on a free ephemeral port chosen here; refused if /proc shows it listening anywhere else;
- the internal bearer is random per start and lives only in this process's memory; the child gets just its SHA-256;
- the child's environment is built from scratch (no AWS keys or other secrets of the Agent Zero process);
- the release comes from /a0/usr/segundo_cerebro/atual -> releases/<commit>/server.js (no symlinks anywhere);
- a start that fails is not retried for ESPERA_FALHA seconds (the gateway answers 503 meanwhile).
"""

import atexit
import hashlib
import http.client
import os
import re
import secrets
import shutil
import signal
import socket
import stat
import subprocess
import threading
import time
from pathlib import Path

RAIZ_ESTADO = Path("/a0/usr/segundo_cerebro")
RAIZ_DADOS = "/a0/usr"  # the parser reads only its three fixed Matheus files below it, read-only
CAMINHO_PATH = "/usr/local/bin:/usr/bin:/bin"
NOME_RELEASE = re.compile(r"^[0-9a-f]{40}$|^local-[0-9a-f]{12}$")
PRAZO_INICIO = 25.0
ESPERA_FALHA = 30.0


class Indisponivel(Exception):
    pass


def _regular(p: Path) -> bool:
    try:
        return stat.S_ISREG(os.lstat(p).st_mode)
    except OSError:
        return False


def _diretorio(p: Path) -> bool:
    try:
        return stat.S_ISDIR(os.lstat(p).st_mode)
    except OSError:
        return False


def porta_livre() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def so_loopback(porta: int, proc_net: Path = Path("/proc/net")) -> bool:
    """True only if every LISTEN socket on this port is 127.0.0.1 (or ::1) and there is at least one."""
    achou = False
    loop = {"tcp": {"0100007F"}, "tcp6": {"00000000000000000000000001000000"}}
    for nome, aceitos in loop.items():
        try:
            linhas = (proc_net / nome).read_text().splitlines()[1:]
        except OSError:
            if nome == "tcp":
                return False
            continue
        for linha in linhas:
            partes = linha.split()
            if len(partes) < 4 or partes[3] != "0A":
                continue
            endereco, _, p = partes[1].partition(":")
            if int(p, 16) != porta:
                continue
            if endereco not in aceitos:
                return False
            achou = True
    return achou


class Processo:
    def __init__(self, raiz_estado: Path = RAIZ_ESTADO, raiz_dados: str = RAIZ_DADOS, node: str | None = None,
                 prazo: float = PRAZO_INICIO, espera_falha: float = ESPERA_FALHA, proc_net: Path = Path("/proc/net")):
        self.raiz_estado = Path(raiz_estado)
        self.raiz_dados = raiz_dados
        self.node = node
        self.prazo = prazo
        self.espera_falha = espera_falha
        self.proc_net = proc_net
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._release: Path | None = None
        self._porta = 0
        self._token = ""
        self._falhou_em = -1e9
        atexit.register(self.parar)

    # ---- release ----
    def release_atual(self) -> Path | None:
        raiz = self.raiz_estado
        if not _diretorio(raiz) or not _regular(raiz / "atual") or os.lstat(raiz / "atual").st_size > 128:
            return None
        nome = (raiz / "atual").read_text(encoding="ascii", errors="replace").strip()
        if not NOME_RELEASE.match(nome):
            return None
        rel = raiz / "releases" / nome
        if not _diretorio(raiz / "releases") or not _diretorio(rel) or not _regular(rel / "server.js"):
            return None
        return rel

    def ambiente(self, release: Path, porta: int, digest: str) -> dict:
        return {
            "PATH": CAMINHO_PATH,
            "HOME": str(release),
            "NODE_ENV": "production",
            "HOSTNAME": "127.0.0.1",
            "PORT": str(porta),
            "NEXT_TELEMETRY_DISABLED": "1",
            "SECOND_BRAIN_TOKEN_SHA256": digest,
            "SECOND_BRAIN_DATA_ROOT": self.raiz_dados,
        }

    # ---- lifecycle ----
    def garantir(self) -> tuple[int, str]:
        """(port, bearer) of a healthy server for the current release; raises Indisponivel."""
        with self._lock:
            rel = self.release_atual()
            if rel is None:
                self._parar()
                raise Indisponivel("nenhuma versão do Segundo Cérebro instalada")
            if self._proc and self._proc.poll() is None and self._release == rel:
                return self._porta, self._token
            self._parar()  # died, or another release became current (deploy / rollback)
            if time.monotonic() - self._falhou_em < self.espera_falha:
                raise Indisponivel("o servidor falhou há pouco")
            try:
                self._iniciar(rel)
            except Indisponivel:
                self._falhou_em = time.monotonic()
                raise
            return self._porta, self._token

    def _iniciar(self, rel: Path) -> None:
        node = self.node or shutil.which("node", path=CAMINHO_PATH)
        if not node:
            raise Indisponivel("node não encontrado")
        self._matar_orfao()
        token = secrets.token_urlsafe(32)
        porta = porta_livre()
        log = open(self.raiz_estado / "node.log", "wb")
        try:
            proc = subprocess.Popen([node, "server.js"], cwd=rel, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                    env=self.ambiente(rel, porta, hashlib.sha256(token.encode()).hexdigest()),
                                    close_fds=True, start_new_session=True)
        except OSError as exc:
            raise Indisponivel(f"não iniciou: {type(exc).__name__}")
        finally:
            log.close()
        (self.raiz_estado / "node.pid").write_text(f"{proc.pid}\n")
        if not self._saudavel(proc, porta) or not so_loopback(porta, self.proc_net):
            self._encerrar(proc)
            raise Indisponivel("o servidor não ficou saudável só em 127.0.0.1")
        self._proc, self._release, self._porta, self._token = proc, rel, porta, token

    def _saudavel(self, proc: subprocess.Popen, porta: int) -> bool:
        """Up and refusing a request without the bearer (401): the auth of the release is live."""
        limite = time.monotonic() + self.prazo
        while time.monotonic() < limite:
            if proc.poll() is not None:
                return False
            try:
                c = http.client.HTTPConnection("127.0.0.1", porta, timeout=2)
                c.request("GET", "/api/segundo-cerebro", headers={"Host": f"127.0.0.1:{porta}"})
                status = c.getresponse().status
                c.close()
                return status == 401
            except (OSError, http.client.HTTPException):
                time.sleep(0.15)
        return False

    def falhou(self) -> None:
        """The gateway could not talk to the server: drop it; the next request starts a new one (after the wait)."""
        with self._lock:
            self._parar()
            self._falhou_em = time.monotonic()

    def parar(self) -> None:
        with self._lock:
            self._parar()

    def _parar(self) -> None:
        proc, self._proc, self._release, self._token, self._porta = self._proc, None, None, "", 0
        if proc is not None:
            self._encerrar(proc)

    @staticmethod
    def _encerrar(proc: subprocess.Popen) -> None:
        if proc.poll() is not None:
            return
        for sinal, espera in ((signal.SIGTERM, 5), (signal.SIGKILL, 5)):
            try:
                os.killpg(proc.pid, sinal)
            except (ProcessLookupError, PermissionError):
                return
            try:
                proc.wait(espera)
                return
            except subprocess.TimeoutExpired:
                continue

    def _matar_orfao(self) -> None:
        """A server left by a previous Agent Zero process (crash) still holds a port: stop it, if it is ours."""
        arquivo = self.raiz_estado / "node.pid"
        try:
            pid = int(arquivo.read_text().strip()) if _regular(arquivo) else 0
        except ValueError:
            pid = 0
        if pid <= 1:
            return
        try:
            cwd = os.readlink(f"/proc/{pid}/cwd")
            cmd = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        except OSError:
            return
        if Path(cwd).parent == self.raiz_estado / "releases" and b"server.js" in cmd:
            try:
                os.killpg(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass

    @property
    def rodando(self) -> bool:
        return bool(self._proc and self._proc.poll() is None)
