#!/usr/bin/env python3
"""Hermes and OpenClaw at full strength, apart from everything of Matheus's (20/10, Matheus: "o agente usa o Hermes e
o OpenClaw juntamente a ele, sendo ele o orquestrador ... parece que eles tão limitados a só texto").

Until now they answered one text turn with every tool off, because they ran inside the agent's container, next to the
vault, the accounts and the logged-in browser. Here each delegated task gets its own Docker container (a "box"):
- nothing of the agent mounted: Hermes/OpenClaw installs read-only, the task's own folder (/trabalho) read-write;
  Hermes's dependency store and runtime come through a per-task overlay (they write lock files), never shared writes;
- its own network "delegados": internet yes; the host only on the relay port, no private range (the agent's container,
  the VPC), no cloud metadata; no capabilities, no new privileges, not root; memory, CPU and process limits;
- the relay (this service, RELAY_PORTA on the network's gateway) forwards only model calls to the model proxy and
  searches to the agent's SearXNG: the proxy's other routes (files, tokens) stay out of reach;
- input files only from the agent's work folders (never the vault, keys, the agents' install or settings), copied in;
  deliverables come out of /trabalho/saida into /a0/usr/workdir/delegados/<id>/ (regular files only).
The agent reaches this service on 172.17.0.1:PORTA with the secret in /opt/a0/usr/delegados/segredo.txt."""

import hmac
import json
import os
import re
import secrets
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORTA = 8791
RELAY_PORTA = 8792
REDE = "delegados"
IMAGEM = "agentepessoal-delegado:1"  # bump the tag when DOCKERFILE changes
DOCKERFILE = """FROM node:22-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends chromium fonts-liberation fonts-noto-color-emoji \\
    fonts-noto-core python3-pip python3-venv zip unzip jq ripgrep ffmpeg poppler-utils \\
    && rm -rf /var/lib/apt/lists/* \\
    && pip3 install --break-system-packages --no-cache-dir pandas openpyxl matplotlib requests beautifulsoup4 lxml \\
       pypdf python-docx pillow
"""
MOTORES = ("hermes", "openclaw")
MODELO = "openai.gpt-6-luna"
PROXY = "http://127.0.0.1:8787"
SEARXNG_PORTA = 55510
AGENTES = Path("/opt/a0/usr/workdir/agentes")
C = "/a0/usr/workdir/agentes"  # the same paths inside the box (Hermes's install records absolute paths)
BASE = Path("/opt/delegados/base")  # readable copies of Hermes's dependency store and runtime (owned by the box user)
TAREFAS = Path("/opt/delegados/tarefas")
USR_HOST = Path("/opt/a0/usr")
USR_A0 = "/a0/usr"
SAIDAS = USR_HOST / "workdir" / "delegados"
SEGREDO = USR_HOST / "delegados" / "segredo.txt"
SCRIPTS = Path("/opt/agentepessoal")
UID = "1000:1000"
LIMITES = ["--memory", "3g", "--memory-swap", "3g", "--cpus", "2", "--pids-limit", "512", "--shm-size", "1g"]
SIMULTANEAS = 2
MINUTOS_MAX = 30
TAREFA_MAX = 20_000
ARQUIVOS_MAX = 10
ARQUIVO_MAX = 25 * 1024 * 1024
SAIDA_MAX = 200 * 1024 * 1024
CHAMADAS_MAX = 400  # model calls per task through the relay
GUARDAR_DIAS = 3
# where the agent's own work lives; anything under these, minus the forbidden names, may go into a box
ENTRADA_RAIZES = ("workdir", "projects", "uploads", "downloads", "whatsapp/matheus", "conteudo")
PROIBIDOS = {"agentes", "cofre", "caixa", "mcp", "credenciais", "credenciais.json", "secrets", ".ssh", ".aws",
             ".git", "settings.json", "usuarios.json", "segredo.txt", ".env"}
_SEGREDO_NO_TEXTO = re.compile(r"AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{30,}|xox[abpr]-[A-Za-z0-9-]{10,}"
                               r"|-----BEGIN [A-Z ]*PRIVATE KEY-----|AIza[0-9A-Za-z_-]{30,}")
_ID = re.compile(r"^d[0-9]{8}-[0-9]{6}-[a-z0-9]{6}$")
_TRAVA = threading.Lock()
_CHAMADAS: dict = {}  # box IP -> model calls through the relay


class Recusa(Exception):
    pass


def log(msg: str) -> None:
    print(f"caixa_delegados: {msg}", flush=True)


def docker(*args: str, timeout: int = 120, entrada: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, timeout=timeout, input=entrada)


def sistema_da_caixa(motor: str, minutos: int) -> str:
    """What the delegate is told about its box (same for both engines, so the agent can compare them)."""
    return (
        f"Você é {'Hermes' if motor == 'hermes' else 'OpenClaw'}, um executor chamado pelo Agent Zero (o orquestrador) "
        "para UMA tarefa. Você roda numa máquina isolada e descartável: pode usar à vontade o terminal (bash, python3 "
        "com pandas/openpyxl/matplotlib/requests/bs4/pypdf/python-docx/pillow, node, ffmpeg, jq, ripgrep), arquivos, "
        "internet e um navegador Chromium.\n"
        "- Arquivos de entrada: /trabalho/entrada/. Entregáveis: salve em /trabalho/saida/ (só o que estiver lá volta).\n"
        "- Navegador pelo terminal: `agent-browser open URL`, `agent-browser snapshot -i` (elementos com @ref), "
        "`agent-browser click @e3`, `agent-browser fill @e5 \"texto\"`, `agent-browser get text body`, "
        "`agent-browser screenshot /trabalho/saida/tela.png`, `agent-browser close`.\n"
        "- Busca na web pelo terminal: `buscar \"termos\"` (resultados em JSON).\n"
        "- Não entre em contas nem faça login, não compre/pague nada, não envie mensagens, e-mails ou formulários em "
        "nome de ninguém, não resolva CAPTCHA. Se a tarefa exigir isso, pare e diga o que faltou.\n"
        f"- Você tem até {minutos} min. Verifique o que fez (rode, abra, confira) antes de dizer que terminou.\n"
        "- Resposta final: o que fez, o resultado, os arquivos em /trabalho/saida/ e o que não deu certo, sem inventar."
    )


def _dentro(caminho: Path, raizes: tuple) -> bool:
    real = caminho.resolve()
    return any(real == r.resolve() or r.resolve() in real.parents for r in raizes)


def origem_permitida(caminho_a0: str) -> Path:
    """A file the agent names (/a0/usr/...) -> its host path, only from the agent's work folders and never a secret."""
    caminho_a0 = str(caminho_a0 or "").strip()
    if not caminho_a0.startswith(USR_A0 + "/"):
        raise Recusa(f"arquivo fora de {USR_A0}/: {caminho_a0!r}")
    host = USR_HOST / caminho_a0[len(USR_A0) + 1:]
    if host.is_symlink() or any(p.is_symlink() for p in host.parents if USR_HOST in p.parents):
        raise Recusa(f"atalho (link) não vai para a caixa: {caminho_a0}")
    raizes = tuple(USR_HOST / r for r in ENTRADA_RAIZES)
    if not _dentro(host, raizes):
        raise Recusa(f"só arquivos das pastas de trabalho ({', '.join(ENTRADA_RAIZES)}): {caminho_a0}")
    partes = {p.lower() for p in host.resolve().relative_to(USR_HOST.resolve()).parts}
    if partes & PROIBIDOS:
        raise Recusa(f"esse arquivo é do cofre, das chaves ou da instalação dos agentes: {caminho_a0}")
    if not host.is_file():
        raise Recusa(f"arquivo não encontrado: {caminho_a0}")
    if host.stat().st_size > ARQUIVO_MAX:
        raise Recusa(f"arquivo grande demais (máximo 25 MB): {caminho_a0}")
    return host


def _nome_seguro(n: str) -> str:
    return (re.sub(r"[^\w.\-]", "_", n).lstrip(".") or "arquivo")[:120]


def novo_id() -> str:
    return time.strftime("d%Y%m%d-%H%M%S") + "-" + "".join(secrets.choice("abcdefghijkmnpqrstuvwxyz23456789")
                                                          for _ in range(6))


def conferir_id(id_: str) -> str:
    id_ = str(id_ or "").strip()
    if not _ID.match(id_):
        raise Recusa("id de tarefa inválido")
    return id_


def relay_url(gateway: str) -> str:
    return f"http://{gateway}:{RELAY_PORTA}"


def configuracao(motor: str, minutos: int, gateway: str) -> dict:
    """/trabalho/config.json: everything the runner needs, nothing secret (the relay holds no credential either)."""
    return {"motor": motor, "modelo": MODELO, "base_url": f"{relay_url(gateway)}/openai/v1",
            "segundos": minutos * 60, "passos": 120, "esforco": "medium", "sistema": sistema_da_caixa(motor, minutos)}


def argumentos_run(id_: str, motor: str, pasta: Path, gateway: str) -> list:
    """The `docker run` of a delegated task (kept in one place so a test can read every flag and mount)."""
    hermes = f"{C}/state/hermes"
    volumes = ["-v", f"{AGENTES / 'runtime'}:{C}/runtime:ro",
               "-v", f"{pasta}:/trabalho",
               "-v", f"{SCRIPTS / 'delegado_hermes.py'}:/caixa/delegado_hermes.py:ro",
               "-v", f"{SCRIPTS / 'delegado_openclaw.py'}:/caixa/delegado_openclaw.py:ro"]
    if motor == "hermes":
        volumes += ["-v", f"{AGENTES / 'hermes-agent'}:{C}/hermes-agent:ro",
                    "-v", f"{pasta / 'casa' / 'hermes'}:{hermes}",
                    "-v", f"{pasta / 'camadas' / 'installs' / 'm'}:{hermes}/installs",
                    "-v", f"{pasta / 'camadas' / 'runtime' / 'm'}:{C}/runtime/hermes"]
        comando = [f"{C}/runtime/hermes/python-3.14.7+20260901-linux-arm64/bin/python3", "-I",
                   "/caixa/delegado_hermes.py"]
    else:
        volumes += ["-v", f"{AGENTES / 'openclaw'}:{C}/openclaw:ro"]
        comando = ["python3", "-I", "/caixa/delegado_openclaw.py"]
    agent_browser = f"{C}/runtime/hermes/agent-browser-0.26.0-linux-arm64/bin"
    ambiente = {"HOME": "/trabalho/casa", "HERMES_HOME": hermes, "HERMES_RUNTIME_DIR": f"{C}/runtime/hermes",
                "AGENT_BROWSER_EXECUTABLE_PATH": "/usr/bin/chromium", "UV_CACHE_DIR": "/trabalho/casa/uv",
                "SEARXNG_URL": f"{relay_url(gateway)}/searxng", "BUSCAR_URL": f"{relay_url(gateway)}/buscar",
                "PIP_BREAK_SYSTEM_PACKAGES": "1", "PIP_USER": "1",
                "PATH": f"/trabalho/bin:/trabalho/casa/.local/bin:{agent_browser}:{C}/runtime/node-v26.12.0-linux-arm64/bin:"
                        "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"}
    env = [x for k, v in ambiente.items() for x in ("-e", f"{k}={v}")]
    return ["run", "-d", "--name", f"delegado-{id_}", "--hostname", "caixa-delegado", "--network", REDE,
            "--label", f"delegado={id_}", "--dns", "1.1.1.1", "--dns", "8.8.8.8",
            *LIMITES, "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--user", UID,
            *volumes, *env, "-w", "/trabalho", "--restart", "no", IMAGEM, *comando]


BUSCAR = """#!/usr/bin/env python3
import json, os, sys, urllib.parse, urllib.request
q = " ".join(sys.argv[1:]).strip()
if not q:
    sys.exit("uso: buscar \\"termos\\"")
with urllib.request.urlopen(os.environ["BUSCAR_URL"] + "?" + urllib.parse.urlencode({"q": q}), timeout=40) as r:
    print(json.dumps(json.loads(r.read()), ensure_ascii=False, indent=1))
"""


# ---------------------------------------------------------------- network and firewall
def regras_isolamento(subrede: str) -> list:
    """INPUT: from the boxes, only the relay port of the host (ACCEPT first, then DROP everything else);
    DOCKER-USER: no private range, no metadata."""
    return ([["INPUT", "-s", subrede, "-p", "tcp", "--dport", str(RELAY_PORTA), "-j", "ACCEPT"],
             ["INPUT", "-s", subrede, "-j", "DROP"]]
            + [["DOCKER-USER", "-s", subrede, "-d", d, "-j", "DROP"]
               for d in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16", "100.64.0.0/10")])


def ordem_ok(linhas_input: list, subrede: str) -> bool:
    """`iptables -S INPUT` lines: the relay ACCEPT must come before the DROP of the boxes' network."""
    aceita = next((i for i, l in enumerate(linhas_input) if f"-s {subrede}" in l and f"--dport {RELAY_PORTA}" in l
                   and "ACCEPT" in l), None)
    bloqueia = next((i for i, l in enumerate(linhas_input) if f"-s {subrede}" in l and "--dport" not in l
                     and l.rstrip().endswith("DROP")), None)
    return aceita is not None and bloqueia is not None and aceita < bloqueia


def subrede_e_gateway() -> tuple:
    r = docker("network", "inspect", REDE, "-f", "{{range .IPAM.Config}}{{.Subnet}}|{{.Gateway}}{{end}}")
    partes = r.stdout.decode().strip().split("|")
    return (partes[0], partes[1]) if r.returncode == 0 and len(partes) == 2 and all(partes) else ("", "")


def isolada() -> bool:
    subrede, _ = subrede_e_gateway()
    if not subrede:
        return False
    presentes = all(subprocess.run(["iptables", "-C", *r], capture_output=True).returncode == 0
                    for r in regras_isolamento(subrede))
    linhas = subprocess.run(["iptables", "-S", "INPUT"], capture_output=True, text=True).stdout.splitlines()
    return presentes and ordem_ok(linhas, subrede)


def garantir_rede() -> tuple:
    if docker("network", "inspect", REDE).returncode:
        r = docker("network", "create", "--driver", "bridge", "-o", "com.docker.network.bridge.enable_icc=false", REDE)
        if r.returncode:
            raise Recusa(f"rede dos delegados não criada: {r.stderr.decode()[:200]}")
    subprocess.run(["/opt/agentepessoal/firewall.sh"], capture_output=True, timeout=60)
    if not isolada():  # never run a delegate without its firewall
        raise Recusa("o isolamento de rede dos delegados falhou; nada foi rodado")
    return subrede_e_gateway()


def garantir_imagem() -> None:
    if docker("image", "inspect", IMAGEM).returncode:
        r = docker("build", "-q", "-t", IMAGEM, "-", timeout=2400, entrada=DOCKERFILE.encode())
        if r.returncode:
            raise Recusa(f"imagem dos delegados não construída: {r.stderr.decode()[-300:]}")
        log(f"imagem {IMAGEM} construída")


def garantir_base() -> None:
    """Readable copies of Hermes's dependency store and runtime, owned by the box user (the originals are root-only).
    Refreshed when the original changes (a Hermes update)."""
    for nome, origem in (("hermes-installs", AGENTES / "state" / "hermes" / "installs"),
                         ("hermes-runtime", AGENTES / "runtime" / "hermes")):
        destino, marca = BASE / nome, BASE / f".{nome}.mtime"
        atual = str(origem.stat().st_mtime)
        if destino.exists() and marca.exists() and marca.read_text() == atual:
            continue
        BASE.mkdir(parents=True, exist_ok=True)
        temp = BASE / f".{nome}.novo"
        shutil.rmtree(temp, ignore_errors=True)
        subprocess.run(["cp", "-a", str(origem), str(temp)], check=True, timeout=1800)
        subprocess.run(["chown", "-R", "1000:1000", str(temp)], check=True, timeout=600)
        if destino.exists():
            shutil.rmtree(destino)
        temp.rename(destino)
        marca.write_text(atual)
        log(f"base {nome} atualizada")


def montar_camadas(pasta: Path) -> None:
    """Per-task copy-on-write views of Hermes's store and runtime: the task writes its locks in its own upper layer."""
    for nome, base in (("installs", BASE / "hermes-installs"), ("runtime", BASE / "hermes-runtime")):
        c = pasta / "camadas" / nome
        for d in ("up", "wk", "m"):
            (c / d).mkdir(parents=True, exist_ok=True)
        os.chown(c / "up", 1000, 1000)
        if subprocess.run(["mountpoint", "-q", str(c / "m")]).returncode:
            subprocess.run(["mount", "-t", "overlay", "overlay", "-o",
                            f"lowerdir={base},upperdir={c / 'up'},workdir={c / 'wk'}", str(c / "m")],
                           check=True, capture_output=True, timeout=60)


def desmontar_camadas(pasta: Path) -> None:
    for nome in ("installs", "runtime"):
        m = pasta / "camadas" / nome / "m"
        if m.exists() and subprocess.run(["mountpoint", "-q", str(m)]).returncode == 0:
            subprocess.run(["umount", "-l", str(m)], capture_output=True, timeout=60)


# ---------------------------------------------------------------- tasks
def rodando() -> list:
    r = docker("ps", "--filter", "label=delegado", "--format", "{{.Label \"delegado\"}}")
    return [x for x in r.stdout.decode().split() if x]


def iniciar(dados: dict) -> dict:
    motor = str(dados.get("motor") or "").strip().lower()
    if motor not in MOTORES:
        raise Recusa("motor deve ser hermes ou openclaw")
    tarefa = str(dados.get("tarefa") or "").strip()
    if not tarefa:
        raise Recusa("a tarefa está vazia")
    if len(tarefa) > TAREFA_MAX:
        raise Recusa(f"tarefa longa demais (máximo {TAREFA_MAX} caracteres): mande o material como arquivo")
    if _SEGREDO_NO_TEXTO.search(tarefa):
        raise Recusa("a tarefa contém o que parece uma chave ou senha: tire antes de delegar")
    arquivos = dados.get("arquivos") or []
    if isinstance(arquivos, str):
        arquivos = [a.strip() for a in arquivos.split(",") if a.strip()]
    if len(arquivos) > ARQUIVOS_MAX:
        raise Recusa(f"no máximo {ARQUIVOS_MAX} arquivos por tarefa")
    origens = [origem_permitida(a) for a in arquivos]
    minutos = max(1, min(int(dados.get("minutos") or 10), MINUTOS_MAX))
    with _TRAVA:
        if len(rodando()) >= SIMULTANEAS:
            raise Recusa(f"já há {SIMULTANEAS} tarefas delegadas rodando: espere uma terminar")
        garantir_imagem()
        if motor == "hermes":
            garantir_base()
        _, gateway = garantir_rede()
        id_ = novo_id()
        pasta = TAREFAS / id_
        for d in ("entrada", "saida", "casa/hermes", "casa/openclaw", "bin"):
            (pasta / d).mkdir(parents=True, exist_ok=True)
        (pasta / "casa" / "hermes" / "config.yaml").write_text('browser:\n  backend: "off"\n')  # agent-browser stack
        (pasta / "bin" / "buscar").write_text(BUSCAR)
        os.chmod(pasta / "bin" / "buscar", 0o755)
        for origem in origens:
            shutil.copyfile(origem, pasta / "entrada" / _nome_seguro(origem.name))
        (pasta / "tarefa.txt").write_text(tarefa)
        (pasta / "config.json").write_text(json.dumps(configuracao(motor, minutos, gateway), ensure_ascii=False))
        subprocess.run(["chown", "-R", "1000:1000", str(pasta)], check=True, timeout=120)
        if motor == "hermes":
            montar_camadas(pasta)
        (pasta / "meta.json").write_text(json.dumps({"id": id_, "motor": motor, "inicio": time.time(),
                                                      "prazo": time.time() + minutos * 60 + 120}))
        r = docker(*argumentos_run(id_, motor, pasta, gateway), timeout=300)
        if r.returncode:
            desmontar_camadas(pasta)
            raise Recusa(f"a caixa não subiu: {r.stderr.decode()[:300]}")
    log(f"{id_}: {motor}, {minutos} min, {len(origens)} arquivo(s)")
    return {"id": id_, "motor": motor, "minutos": minutos}


def coletar_saida(pasta: Path, destino: Path) -> list:
    """Regular files of /trabalho/saida (no links, no devices), up to SAIDA_MAX in total -> the agent's folder."""
    destino.mkdir(parents=True, exist_ok=True)
    feitos, total = [], 0
    raiz = (pasta / "saida").resolve()
    for f in sorted((pasta / "saida").rglob("*")):
        if f.is_symlink() or not f.is_file() or raiz not in f.resolve().parents:
            continue
        tam = f.stat().st_size
        if total + tam > SAIDA_MAX:
            break
        rel = f.relative_to(pasta / "saida")
        alvo = destino / Path(*[_nome_seguro(p) for p in rel.parts])
        alvo.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(f, alvo)
        total += tam
        feitos.append({"arquivo": f"{USR_A0}/{alvo.relative_to(USR_HOST)}", "bytes": tam})
    return feitos


def estado(dados: dict) -> dict:
    id_ = conferir_id(dados.get("id"))
    pasta = TAREFAS / id_
    if not (pasta / "meta.json").exists():
        raise Recusa("tarefa não encontrada")
    meta = json.loads((pasta / "meta.json").read_text())
    if (pasta / "final.json").exists():
        return json.loads((pasta / "final.json").read_text())
    r = docker("inspect", "-f", "{{.State.Running}}|{{.State.ExitCode}}", f"delegado-{id_}")
    vivo = r.returncode == 0 and r.stdout.decode().startswith("true")
    if vivo and time.time() < meta["prazo"]:
        return {"id": id_, "motor": meta["motor"], "status": "rodando",
                "segundos": round(time.time() - meta["inicio"])}
    docker("rm", "-f", f"delegado-{id_}")
    try:
        res = json.loads((pasta / "resultado.json").read_text())
    except (OSError, ValueError):
        res = {"ok": False, "erro": "passou do prazo" if vivo else "a caixa terminou sem resultado"}
    desmontar_camadas(pasta)
    final = {"id": id_, "motor": meta["motor"], "status": "pronto" if res.get("ok") else "falhou",
             "resposta": str(res.get("resposta") or "")[:20000], "erro": res.get("erro"),
             "ferramentas": res.get("ferramentas") or [], "segundos": res.get("segundos"),
             "arquivos": coletar_saida(pasta, SAIDAS / id_)}
    (pasta / "final.json").write_text(json.dumps(final, ensure_ascii=False))
    log(f"{id_}: {final['status']} em {final['segundos']} s, {len(final['arquivos'])} arquivo(s)")
    return final


def parar(dados: dict) -> dict:
    id_ = conferir_id(dados.get("id"))
    docker("rm", "-f", f"delegado-{id_}")
    return estado({"id": id_})


def listar(_dados: dict) -> dict:
    itens = []
    for meta in sorted(TAREFAS.glob("d*/meta.json"))[-20:]:
        m = json.loads(meta.read_text())
        final = meta.parent / "final.json"
        st = json.loads(final.read_text())["status"] if final.exists() else "rodando"
        itens.append({"id": m["id"], "motor": m["motor"], "status": st,
                      "inicio": time.strftime("%d/%m %H:%M", time.localtime(m["inicio"]))})
    return {"tarefas": itens}


def faxina(agora: float | None = None) -> None:
    """Close what passed its deadline; delete task folders after GUARDAR_DIAS (deliverables stay in the agent's)."""
    agora = agora or time.time()
    for meta in TAREFAS.glob("d*/meta.json"):
        try:
            m = json.loads(meta.read_text())
            if not (meta.parent / "final.json").exists() and agora > m["prazo"]:
                estado({"id": m["id"]})
            elif agora - m["inicio"] > GUARDAR_DIAS * 86400:
                desmontar_camadas(meta.parent)
                shutil.rmtree(meta.parent, ignore_errors=True)
        except Exception as exc:
            log(f"faxina {meta.parent.name}: {exc}")


# ---------------------------------------------------------------- relay (model + search, nothing else)
def rota_permitida(metodo: str, caminho: str) -> str:
    """Where a box request may go: 'modelo', 'searxng', 'buscar' or '' (refused)."""
    alvo = urllib.parse.urlsplit(caminho).path
    if metodo == "POST" and alvo in ("/openai/v1/responses", "/openai/v1/chat/completions"):
        return "modelo"
    if metodo == "GET" and alvo == "/openai/v1/models":
        return "modelo"
    if metodo == "GET" and alvo == "/searxng/search":
        return "searxng"
    if metodo == "GET" and alvo == "/buscar":
        return "buscar"
    return ""


def buscar_searxng(params: dict) -> bytes:
    """The agent's SearXNG listens only inside its container (127.0.0.1): ask it there, with a fixed command and an
    encoded query (never a shell string from the box)."""
    url = f"http://127.0.0.1:{SEARXNG_PORTA}/search?{urllib.parse.urlencode(params)}"
    r = docker("exec", "agent-zero", "curl", "-s", "-m", "30", url, timeout=40)
    if r.returncode or not r.stdout:
        raise OSError("busca indisponível")
    return r.stdout


def resumir_busca(dados: dict) -> dict:
    return {"resultados": [{"titulo": x.get("title"), "url": x.get("url"), "trecho": (x.get("content") or "")[:400]}
                           for x in (dados.get("results") or [])[:12]]}


class Repasse(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _erro(self, codigo: int, msg: str) -> None:
        corpo = json.dumps({"erro": msg}).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _repassar(self, metodo: str) -> None:
        rota = rota_permitida(metodo, self.path)
        if not rota:
            return self._erro(404, "só modelo e busca passam por aqui")
        corpo = None
        if metodo == "POST":
            tam = int(self.headers.get("Content-Length") or 0)
            if tam > 20 * 1024 * 1024:
                return self._erro(413, "pedido grande demais")
            corpo = self.rfile.read(tam)
        ip = self.client_address[0]
        if rota == "modelo" and metodo == "POST":
            _CHAMADAS[ip] = _CHAMADAS.get(ip, 0) + 1
            if _CHAMADAS[ip] > CHAMADAS_MAX:
                return self._erro(429, f"esta tarefa passou de {CHAMADAS_MAX} chamadas ao modelo")
        if rota != "modelo":
            consulta = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            params = {"q": (consulta.get("q") or [""])[0][:400], "format": "json"}
            if rota == "searxng":
                params.update({k: v[0][:40] for k, v in consulta.items() if k in ("pageno", "language", "categories",
                                                                                  "time_range")})
            try:
                bruto = buscar_searxng(params)
                dados = json.dumps(resumir_busca(json.loads(bruto)), ensure_ascii=False).encode() \
                    if rota == "buscar" else bruto
            except (OSError, ValueError, subprocess.TimeoutExpired):
                return self._erro(502, "busca indisponível")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(dados)))
            self.end_headers()
            self.wfile.write(dados)
            return
        cab = {"Content-Type": self.headers.get("Content-Type") or "application/json",
               "Accept": self.headers.get("Accept") or "*/*"}
        try:
            resp = urllib.request.urlopen(urllib.request.Request(PROXY + self.path, data=corpo, headers=cab,
                                                                 method=metodo), timeout=600)
        except urllib.error.HTTPError as e:
            resp = e
        except Exception:
            return self._erro(502, "o serviço não respondeu")
        self.send_response(resp.status if hasattr(resp, "status") else resp.code)
        self.send_header("Content-Type", resp.headers.get("Content-Type") or "application/json")
        self.send_header("Transfer-Encoding", "chunked")
        self.send_header("Connection", "close")
        self.end_headers()
        while True:  # streamed answers (SSE) go through as they come
            try:
                bloco = resp.read1(65536) if hasattr(resp, "read1") else resp.read(65536)
            except Exception:
                break
            if not bloco:
                break
            self.wfile.write(f"{len(bloco):X}\r\n".encode() + bloco + b"\r\n")
            self.wfile.flush()
        self.wfile.write(b"0\r\n\r\n")
        self.close_connection = True

    def do_POST(self):
        self._repassar("POST")

    def do_GET(self):
        self._repassar("GET")


# ---------------------------------------------------------------- the agent's side
def segredo() -> str:
    if not SEGREDO.exists():
        SEGREDO.parent.mkdir(parents=True, exist_ok=True)
        SEGREDO.write_text(secrets.token_urlsafe(32))
        os.chmod(SEGREDO, 0o600)
    return SEGREDO.read_text().strip()


ACOES = {"iniciar": iniciar, "estado": estado, "parar": parar, "listar": listar}


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
            return self._responder(500, {"erro": "falha na caixa dos delegados; tente de novo"})


def ciclo_faxina() -> None:
    while True:
        time.sleep(120)
        try:
            faxina()
        except Exception as exc:
            log(f"faxina: {exc}")


def preparar() -> None:
    try:
        garantir_imagem()
        garantir_base()
    except Exception as exc:
        log(f"preparo: {exc}")


def main() -> None:
    segredo()
    TAREFAS.mkdir(parents=True, exist_ok=True)
    SAIDAS.mkdir(parents=True, exist_ok=True)
    _, gateway = garantir_rede()
    threading.Thread(target=ciclo_faxina, daemon=True).start()
    threading.Thread(target=preparar, daemon=True).start()
    repasse = ThreadingHTTPServer((gateway, RELAY_PORTA), Repasse)
    threading.Thread(target=repasse.serve_forever, daemon=True).start()
    # on the docker bridge's gateway only: the agent's container reaches it as host.docker.internal
    ThreadingHTTPServer(("172.17.0.1", PORTA), Pedido).serve_forever()


if __name__ == "__main__":
    main()
