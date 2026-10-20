"""Segundo Cérebro: build, package, deploy and roll back the page + its Agent Zero gateway plugin. Usage, from the
repository root (implantar.py --segundo-cerebro calls the same functions):

    python3 infra/operador/segundo_cerebro.py preparar [--saida DIR]    local only: no AWS, no commit needed
    python3 infra/operador/implantar.py --segundo-cerebro                 deploy HEAD (committed and pushed)
    python3 infra/operador/implantar.py --segundo-cerebro --rollback      put back what ran before the last deploy

What goes: the Next standalone build of app/ (server.js + .next/static + public) and the plugin
infra/vm/plugins/segundo_cerebro. Rules (same as implantar.py, plus):
1. deploy builds from `git archive HEAD`, never from the working tree; `preparar` uses HEAD plus only the Segundo
   Cérebro files of the working tree (FOCO_LOCAL), so unrelated uncommitted work never enters an artifact;
2. no dependency install: the build uses the existing app/node_modules;
3. Node tests and the build run before anything is uploaded; on the VM the plugin suite and a real start of the
   release run on a staging copy before the swap; the previous plugin and release are kept for --rollback;
4. there is no --forcar: a VM running a version that is not in this checkout's history stops the deploy.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
PLUGIN = "infra/vm/plugins/segundo_cerebro"
LADO_VM = "infra/operador/segundo_cerebro_vm.py"
# what deploy reads from HEAD; all of it must be committed and pushed (_conferir_git)
CAMINHOS_APROVADOS = ["app", PLUGIN, "infra/operador/segundo_cerebro.py", LADO_VM]
# working-tree files `preparar` may take on top of HEAD (everything else under app/ comes from HEAD)
FOCO_LOCAL = [
    "app/app/segundo-cerebro", "app/app/api/segundo-cerebro", "app/lib/second-brain.mjs", "app/lib/second-brain.d.mts",
    "app/lib/connection-map.mjs", "app/lib/connection-map.d.mts", "app/tests", "app/next.config.ts",
    "app/components/Sidebar.tsx", "app/SECOND_BRAIN.md", PLUGIN, LADO_VM, "infra/operador/segundo_cerebro.py",
]
TESTES_NODE = ["tests/second-brain.test.mjs", "tests/second-brain-boundaries.test.mjs",
               "tests/second-brain-real-format.test.mjs", "tests/connection-map.test.mjs"]
IGNORAR = {"__pycache__", ".pytest_cache"}
LIMITE_PACOTE = 200 * 1024 * 1024


def sh(*cmd: str, cwd: Path = RAIZ) -> str:
    return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


# ---------- source trees ----------

def _extrair_tar(dados: bytes, destino: Path) -> None:
    import io
    with tarfile.open(fileobj=io.BytesIO(dados)) as t:
        t.extractall(destino, filter="data")


def extrair_head(destino: Path, raiz: Path = RAIZ) -> str:
    """HEAD's copy of the approved paths into destino; returns the commit."""
    head = sh("git", "rev-parse", "HEAD", cwd=raiz)
    existentes = [c for c in CAMINHOS_APROVADOS
                  if subprocess.run(["git", "cat-file", "-e", f"HEAD:{c}"], cwd=raiz, capture_output=True).returncode == 0]
    dados = subprocess.run(["git", "archive", "--format=tar", "HEAD", *existentes], cwd=raiz, check=True,
                           capture_output=True).stdout
    _extrair_tar(dados, destino)
    return head


def extrair_local(destino: Path, raiz: Path = RAIZ) -> dict:
    """HEAD plus the working-tree copy of FOCO_LOCAL only. Returns what was taken and what dirty paths were left out."""
    head = extrair_head(destino, raiz)
    tomados = []
    for rel in FOCO_LOCAL:
        origem = raiz / rel
        if origem.is_symlink():
            raise SystemExit(f"recusado: {rel} é link simbólico")
        if origem.is_dir():
            for f in sorted(origem.rglob("*")):
                if f.is_symlink():
                    raise SystemExit(f"recusado: {f.relative_to(raiz)} é link simbólico")
                if f.is_file() and not IGNORAR.intersection(f.relative_to(raiz).parts):
                    alvo = destino / f.relative_to(raiz)
                    alvo.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, alvo)
                    tomados.append(str(f.relative_to(raiz)))
        elif origem.is_file():
            (destino / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origem, destino / rel)
            tomados.append(rel)
    saida = subprocess.run(["git", "status", "--porcelain=v1", "-z"], cwd=raiz, check=True, capture_output=True).stdout
    sujos = [e[3:].decode() for e in saida.split(b"\0") if len(e) > 3 and e[2:3] == b" "]
    fora = sorted(s for s in sujos if not any(s == f or s.startswith(f.rstrip("/") + "/") for f in FOCO_LOCAL))
    return {"head": head, "tomados": tomados, "sujos_fora": fora}


# ---------- build ----------

def mock_fontes(app_existente: Path, destino: Path) -> Path | None:
    """next/font/google downloads Geist at build time. Offline, answer it from the font files of the previous local
    build (app/.next/static/media) through Next's own NEXT_FONT_GOOGLE_MOCKED_RESPONSES: no request leaves.
    Turbopack keeps a mocked url() as written, so the files go inline (data:) instead of as a local path."""
    import base64
    import re
    css = ""
    for f in sorted((app_existente / ".next" / "static").rglob("*.css")):
        css += f.read_text(encoding="utf-8", errors="replace")
    blocos = re.findall(r"@font-face\s*\{[^}]*\}", css)
    familias: dict[str, list[str]] = {}
    for b in blocos:
        fam = re.search(r"font-family:\s*['\"]?([^;'\"]+)", b)
        url = re.search(r"url\(([^)]+)\)", b)
        if not fam or not url or "Fallback" in fam.group(1):
            continue
        arquivo = app_existente / ".next" / "static" / "media" / Path(url.group(1).strip("'\"")).name
        if not arquivo.is_file():
            continue
        nome = re.sub(r"^__|_[0-9a-f]{6,}$", "", fam.group(1).strip()).replace("_", " ").strip()
        dados = base64.b64encode(arquivo.read_bytes()).decode()
        face = b.replace(url.group(0), f"url(data:font/woff2;base64,{dados})")
        if face not in familias.setdefault(nome, []):
            familias[nome].append(face)
    if not {"Geist", "Geist Mono"} <= set(familias):
        return None
    mapa = {}
    for nome, faces in familias.items():
        q = nome.replace(" ", "+")
        mapa[f"https://fonts.googleapis.com/css2?family={q}:wght@100..900&display=swap"] = "\n".join(faces)
    destino.write_text("module.exports = " + json.dumps(mapa, indent=1) + ";\n", encoding="utf-8")
    return destino


def ambiente_build(home: Path, offline: bool, mock: Path | None) -> dict:
    env = {"PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"), "HOME": str(home), "LANG": "C.UTF-8",
           "NEXT_TELEMETRY_DISABLED": "1", "CI": "1"}
    if offline:  # every proxy points at a closed loopback port: any attempt fails here, nothing leaves the machine
        for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
            env[k] = "http://127.0.0.1:9"
        env["NO_PROXY"] = env["no_proxy"] = ""
        if mock:
            env["NEXT_FONT_GOOGLE_MOCKED_RESPONSES"] = str(mock)
    return env


def _rodar(cmd: list, cwd: Path, env: dict, log: Path, timeout: int) -> int:
    with open(log, "wb") as saida:
        return subprocess.run(cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=saida, stderr=subprocess.STDOUT,
                              timeout=timeout).returncode


def construir(fonte: Path, trabalho: Path, offline: bool, node_modules: Path = RAIZ / "app" / "node_modules") -> dict:
    """Node tests + `next build` on the extracted tree (fonte/app), with a copy of the existing node_modules (never
    installed; Turbopack refuses a node_modules symlink that leaves the project). Returns a report; raises SystemExit
    on any failure."""
    app = fonte / "app"
    if not (node_modules / "next" / "package.json").is_file():
        raise SystemExit("app/node_modules não tem o Next: este build não instala dependências")
    subprocess.run(["cp", "-a", "--reflink=auto", str(node_modules), str(app / "node_modules")], check=True)
    home = trabalho / "home"
    home.mkdir(exist_ok=True)
    mock = mock_fontes(RAIZ / "app", trabalho / "fontes-mock.js") if offline else None
    env = ambiente_build(home, offline, mock)
    rel = {"offline": offline, "fontes_locais": bool(mock)}
    node = shutil.which("node", path=env["PATH"])
    if not node:
        raise SystemExit("node não encontrado")
    rel["node"] = sh(node, "--version")
    testes = [t for t in TESTES_NODE if (app / t).is_file()]
    codigo = _rodar([node, "--test", "--test-reporter=tap", *testes], app, env, trabalho / "testes-node.log", 600)
    tap = (trabalho / "testes-node.log").read_text(encoding="utf-8", errors="replace")
    contar = lambda k: next((int(l.split()[-1]) for l in tap.splitlines() if l.startswith(f"# {k} ")), 0)
    rel["testes_node"] = {"codigo": codigo, "total": contar("tests"), "passou": contar("pass"), "falhou": contar("fail")}
    if codigo or not rel["testes_node"]["total"] or rel["testes_node"]["falhou"]:
        raise SystemExit(f"testes Node falharam: veja {trabalho / 'testes-node.log'}")
    codigo = _rodar([node, "node_modules/next/dist/bin/next", "build"], app, env, trabalho / "build.log", 1200)
    rel["build"] = {"codigo": codigo}
    if codigo:
        raise SystemExit(f"next build falhou: veja {trabalho / 'build.log'}")
    return rel


# ---------- package ----------

def _copiar_arvore(origem: Path, destino: Path) -> None:
    shutil.copytree(origem, destino, symlinks=True, ignore=shutil.ignore_patterns(*IGNORAR))


def conferir_links(raiz: Path) -> None:
    """Every symlink in the package must be relative and stay inside it (the standalone node_modules may use them)."""
    base = raiz.resolve()
    for f in raiz.rglob("*"):
        if f.is_symlink():
            alvo = os.readlink(f)
            if os.path.isabs(alvo) or not (f.parent / alvo).resolve().is_relative_to(base):
                raise SystemExit(f"link inseguro no pacote: {f.relative_to(raiz)} -> {alvo}")


def montar_pacote(fonte: Path, destino: Path, versao: str, origem: str) -> dict:
    """destino/{release,plugin,vm,MANIFESTO.json}: standalone + .next/static + public; plugin; VM-side script."""
    app = fonte / "app"
    standalone = app / ".next" / "standalone"
    if not (standalone / "server.js").is_file():
        raise SystemExit("o build não gerou .next/standalone/server.js (output: 'standalone' no next.config.ts?)")
    release = destino / "release"
    _copiar_arvore(standalone, release)
    if (release / "node_modules").is_symlink():  # the build tree links node_modules; the release must carry its own copy
        raise SystemExit("o standalone apontou para o node_modules do build em vez de copiar o necessário")
    _copiar_arvore(app / ".next" / "static", release / ".next" / "static")
    if (app / "public").is_dir():
        _copiar_arvore(app / "public", release / "public")
    for proibido in list(release.rglob(".env*")):
        raise SystemExit(f"arquivo de ambiente no pacote: {proibido.relative_to(destino)}")
    _copiar_arvore(fonte / PLUGIN, destino / "plugin")
    (destino / "vm").mkdir()
    shutil.copy2(fonte / LADO_VM, destino / "vm" / "segundo_cerebro_vm.py")
    conferir_links(destino)
    arquivos = {}
    for f in sorted(destino.rglob("*")):
        if f.is_file() and not f.is_symlink():
            arquivos[str(f.relative_to(destino))] = hashlib.sha256(f.read_bytes()).hexdigest()
    manifesto = {"versao": versao, "origem": origem, "criado": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                 "arquivos": arquivos}
    (destino / "MANIFESTO.json").write_text(json.dumps(manifesto, indent=1), encoding="utf-8")
    return manifesto


def empacotar(pasta: Path, arquivo: Path) -> int:
    with tarfile.open(arquivo, "w:gz") as t:
        for f in sorted(pasta.iterdir()):
            t.add(f, arcname=f.name)
    tamanho = arquivo.stat().st_size
    if tamanho > LIMITE_PACOTE:
        raise SystemExit(f"pacote grande demais ({tamanho} bytes)")
    return tamanho


def suite_plugin(plugin_dir: Path, python: str = sys.executable) -> dict:
    """The plugin suite (Suite.rodar) in a separate interpreter, like implantar.py does on the VM."""
    codigo = ("import asyncio, importlib.util, json, sys\n"
              "s = importlib.util.spec_from_file_location('suite_sc', sys.argv[1] + '/tests/suite.py')\n"
              "m = importlib.util.module_from_spec(s); s.loader.exec_module(m)\n"
              "r = asyncio.run(m.Suite().rodar(''))\n"
              "print(json.dumps({'total': r['total'], 'passou': r['passou'],"
              " 'falhas': [x['teste'] + ': ' + str(x.get('erro', ''))[:200] for x in r['resultados'] if not x['ok']]}))\n")
    p = subprocess.run([python, "-c", codigo, str(plugin_dir)], capture_output=True, text=True, timeout=600,
                       env={**os.environ, "CI": "1"})
    try:
        return json.loads(p.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        return {"total": 0, "passou": 0, "falhas": [f"a suíte não rodou: {p.stderr[-500:]}"]}


# ---------- local preparation (no AWS) ----------

def preparar(saida: Path | None = None, python_suite: str | None = None) -> Path:
    """Artifact + test report from HEAD plus the Segundo Cérebro working files. No AWS, no commit, no install."""
    saida = Path(saida or tempfile.mkdtemp(prefix="segundo-cerebro-preparo-"))
    saida.mkdir(parents=True, exist_ok=True)
    trabalho = Path(tempfile.mkdtemp(prefix="segundo-cerebro-build-"))
    fonte = trabalho / "fonte"
    fonte.mkdir()
    origem = extrair_local(fonte)
    relatorio = {"origem": "local (HEAD + FOCO_LOCAL do working tree)", "head": origem["head"],
                 "arquivos_locais": len(origem["tomados"]), "sujos_deixados_de_fora": origem["sujos_fora"]}
    relatorio["suite_plugin"] = suite_plugin(fonte / PLUGIN, python_suite or sys.executable)
    if relatorio["suite_plugin"]["falhas"] or not relatorio["suite_plugin"]["total"]:
        (saida / "relatorio.json").write_text(json.dumps(relatorio, indent=1, ensure_ascii=False), encoding="utf-8")
        raise SystemExit(f"suíte do plugin falhou: {relatorio['suite_plugin']['falhas'][:3]}")
    relatorio.update(construir(fonte, trabalho, offline=True))
    for log in ("testes-node.log", "build.log"):
        shutil.copy2(trabalho / log, saida / log)
    pacote = trabalho / "pacote"
    pacote.mkdir()
    versao = f"local-{origem['head'][:12]}"
    manifesto = montar_pacote(fonte, pacote, versao, relatorio["origem"])
    relatorio["pacote"] = {"arquivo": str(saida / f"segundo-cerebro-{versao}.tgz"), "arquivos": len(manifesto["arquivos"]),
                           "bytes": empacotar(pacote, saida / f"segundo-cerebro-{versao}.tgz")}
    relatorio["release_tem"] = {k: (pacote / "release" / k).exists()
                                for k in ("server.js", ".next/static", "public", "node_modules/next")}
    (saida / "relatorio.json").write_text(json.dumps(relatorio, indent=1, ensure_ascii=False), encoding="utf-8")
    shutil.rmtree(trabalho, ignore_errors=True)  # our own temporary build tree only
    print(json.dumps(relatorio, indent=1, ensure_ascii=False))
    print(f"preparo local pronto em {saida} (nada foi enviado)")
    return saida


# ---------- deploy (AWS) ----------

VM_USR = "/opt/a0/usr"
ESTAGIO_VM = "/tmp/implantar-segundo-cerebro"
CONTA = "964862484412"


def _vm_json(vm, comando: str, timeout: int = 900) -> dict:
    saida = vm(comando, timeout)
    linha = next((l for l in reversed(saida.splitlines()) if l.startswith("{")), "")
    try:
        return json.loads(linha)
    except ValueError:
        raise SystemExit(f"resposta inesperada da VM:\n{saida[-1500:]}")


def _lado_vm(pasta: str, acao: str, versao: str, extra: str = "") -> str:
    return f"python3 {pasta}/vm/segundo_cerebro_vm.py {acao} --versao {versao} {extra}".strip()


def guarda_de_versao(no_ar: dict, head: str, eh_ancestral, adotar: bool = False) -> None:
    """The plugin and the release running on the VM must both come from this checkout's history (no --forcar).
    With --adotar-manual, a `local-` release the VM side already checked (plugin identical to this package) passes."""
    for nome in ("plugin", "release"):
        sha = (no_ar.get(nome) or "").strip()
        if not sha or (adotar and nome == "release" and __import__("re").fullmatch(r"local-[0-9a-f]{12}", sha)):
            continue
        if not __import__("re").fullmatch(r"[0-9a-f]{40}", sha):
            raise SystemExit(f"a VM roda um {nome} de versão desconhecida ({sha[:20]!r}): confira antes, nada foi feito.")
        if not eh_ancestral(sha, head):
            raise SystemExit(f"a VM roda {nome} de {sha[:8]}, que não está no seu histórico: faça git pull. Nada foi feito.")


def implantar(vm, enviar, conferir_git, eh_ancestral, url_publica, sondar_publico, conferir_conta, bucket: str,
              python_suite: str = sys.executable, adotar: bool = False) -> None:
    """vm(cmd, timeout)->str, enviar(chave, bytes), conferir_git(caminhos)->head, eh_ancestral(a, b)->bool,
    url_publica()->str, sondar_publico(url)->dict, conferir_conta(): injected by implantar.py (tests use fakes)."""
    head = conferir_git(CAMINHOS_APROVADOS)
    conferir_conta()
    trabalho = Path(tempfile.mkdtemp(prefix="segundo-cerebro-implantar-"))
    try:
        fonte = trabalho / "fonte"
        fonte.mkdir()
        if extrair_head(fonte) != head:
            raise SystemExit("HEAD mudou durante o deploy")
        suite = suite_plugin(fonte / PLUGIN, python_suite)
        if suite["falhas"] or not suite["total"]:
            raise SystemExit(f"suíte do plugin falhou aqui: {suite['falhas'][:3]}")
        construir(fonte, trabalho, offline=False)
        pacote = trabalho / "pacote"
        pacote.mkdir()
        montar_pacote(fonte, pacote, head, "git archive HEAD")
        empacotar(pacote, trabalho / "pacote.tgz")
        _implantar_pacote(vm, enviar, eh_ancestral, url_publica, sondar_publico, head,
                          (trabalho / "pacote.tgz").read_bytes(), bucket, adotar=adotar)
    finally:
        shutil.rmtree(trabalho, ignore_errors=True)  # our own temporary build tree only


def _implantar_pacote(vm, enviar, eh_ancestral, url_publica, sondar_publico, head: str, dados: bytes, bucket: str,
                      agora=time.time, adotar: bool = False) -> None:
    chave = f"tmp/implantar-segundo-cerebro-{head[:8]}.tgz"
    enviar(chave, dados)
    pasta = f"{ESTAGIO_VM}/{head[:12]}-{int(agora())}"  # fresh per attempt: no leftovers, nothing to delete
    lado = lambda acao, extra="": _lado_vm(pasta, acao, head, extra)
    baixar = f"mkdir -p {pasta} && aws s3 cp --quiet s3://{bucket}/{chave} - | tar xz --no-same-owner -C {pasta}"
    marca = "--adotar-manual" if adotar else ""
    no_ar = _vm_json(vm, f"{baixar} && " + lado("conferir", marca))
    if no_ar.get("problemas") or not no_ar.get("ok"):
        raise SystemExit("a VM recusou: " + "; ".join(no_ar.get("problemas") or [str(no_ar.get("erro"))])
                         + ". Nada foi trocado.")
    guarda_de_versao(no_ar, head, eh_ancestral, adotar)
    estagio = _vm_json(vm, lado("estagiar", marca), 1200)
    if not estagio.get("ok"):
        raise SystemExit(f"o estágio falhou ({estagio.get('erro', '?')}): nada foi trocado.")
    troca = _vm_json(vm, lado("trocar", marca))
    if not troca.get("ok"):
        raise SystemExit(f"a troca não terminou ({troca.get('erro', '?')}): rode --segundo-cerebro --rollback e confira.")
    reiniciou = False
    sonda = _vm_json(vm, lado("sondar"), 300)
    if not sonda.get("ok") and sonda.get("gateway") != 401:
        # the gateway is not registered in the running web app (first install): it registers at start-up only
        reinicio = _vm_json(vm, lado("reiniciar"), 400)
        reiniciou = True
        sonda = _vm_json(vm, lado("sondar"), 300) if reinicio.get("ok") else {"ok": False, "reinicio": reinicio}
    publico = sondar_publico(url_publica()) if sonda.get("ok") else {"ok": False}
    if not (sonda.get("ok") and publico.get("ok")):
        # no restart needed to undo: with the plugin out of place the registered hook serves nothing
        volta = _vm_json(vm, lado("reverter", "--automatico"), 600)
        raise SystemExit(f"a sonda falhou (VM {sonda}, público {publico}, reiniciou={reiniciou}); "
                         f"revertido automaticamente: {volta}")
    print(f"implantado: segundo_cerebro @ {head[:8]} (gateway 401 sem sessão, release saudável, URL pública ok)"
          + (" — o container foi reiniciado (primeira instalação)" if reiniciou else ""))


def reverter(vm) -> None:
    """Put back the plugin snapshot and the release that ran before the last deploy (not the git version), with the
    copy of the VM-side script the deploy left in /opt/a0/usr/segundo_cerebro/vm. Nothing is deleted."""
    script = f"{VM_USR}/segundo_cerebro/vm/segundo_cerebro_vm.py"
    volta = _vm_json(vm, f"if test -f {script}; then python3 {script} reverter; else "
                         "echo '{\"ok\": false, \"erro\": \"Segundo Cérebro nunca foi implantado nesta VM\"}'; fi", 600)
    if not volta.get("ok"):
        raise SystemExit(f"rollback não feito: {volta.get('erro', volta)}")
    print(f"revertido: plugin {volta.get('plugin') or 'desativado (primeira instalação)'}, "
          f"release {volta.get('release') or 'nenhuma'}")


def main() -> None:
    args = sys.argv[1:]
    if args[:1] == ["preparar"]:
        saida = Path(args[args.index("--saida") + 1]) if "--saida" in args else None
        python = args[args.index("--python-suite") + 1] if "--python-suite" in args else None
        preparar(saida, python)
        return
    raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
