#!/usr/bin/env python3
"""Estabilidade do kernel da VM e limpeza de disco (incidente de 23/10, 21:49 UTC).

O que houve: pane do kernel (Oops em io_ring_ctx_wait_and_kill ← io_uring_release ← close, kernel 6.8.0-1066-aws,
o mais novo do Ubuntu 22.04) quando um `npm` do OpenCode fechou um io_uring. O kernel parou e não religou sozinho; o
alarme reiniciou a VM 10 min depois. O rastro só sobreviveu porque o UEFI guarda o dmesg da pane (pstore).

    estabilidade.py aplicar   (no boot, agentepessoal-estabilidade.service)
        - /etc/sysctl.d/99-agentepessoal-estabilidade.conf: io_uring desligado para todos (=2: io_uring_setup dá EPERM e
          Node/libuv cai no modo normal; Docker já bloqueia io_uring nos contêineres), pane do kernel religa em 10 s,
          Oops vira pane (não fica meio vivo);
        - journal persistente com teto de tamanho;
        - pane guardada pelo pstore (/var/lib/systemd/pstore/<id>): vai para o S3 (incidentes/), o resumo fica em
          /var/lib/agentepessoal/pane_kernel.json (o saude.py mostra) e o Matheus recebe um aviso.
    estabilidade.py limpar    (todo dia, agentepessoal-limpeza-disco.timer)
        - imagens Docker sem nome (dangling), imagens antigas do Hermes (fica a em uso + as 2 mais novas), journal acima
          do teto. Nunca mexe em contêiner (o agent-zero parado fica até 30/10), volume nem dado.
    estabilidade.py estado    (só mostra)

Só biblioteca padrão (roda no python3 do host)."""

import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

SYSCTL_ARQ = Path("/etc/sysctl.d/99-agentepessoal-estabilidade.conf")
SYSCTLS = {
    "kernel.io_uring_disabled": "2",  # 23/10: a pane veio do io_uring (nada nosso precisa dele)
    "kernel.panic": "10",  # pane religa a VM em 10 s (sem isso ela fica parada até o alarme)
    "kernel.panic_on_oops": "1",  # Oops = pane: melhor religar que seguir com o kernel corrompido
}
JOURNALD_ARQ = Path("/etc/systemd/journald.conf.d/agentepessoal.conf")
JOURNAL_MAX = "800M"
PSTORE = Path("/var/lib/systemd/pstore")
ESTADO = Path("/var/lib/agentepessoal")
PANE = ESTADO / "pane_kernel.json"
CHAVE = Path("/opt/a0/usr/whatsapp/.chave")
HERMES_REPO = "agentepessoal/hermes"
MANTER_HERMES = 2


def log(msg: str) -> None:
    print(msg, flush=True)
    subprocess.run(["logger", "-t", "agentepessoal", f"estabilidade: {msg}"], check=False)


def _cmd(*args: str, timeout: int = 120) -> str:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


# ------------------------------------------------------------------ configuração do kernel e do journal

def texto_sysctl() -> str:
    linhas = ["# infra/vm/estabilidade.py (incidente de 23/10: pane do kernel no io_uring). Não edite à mão."]
    return "\n".join(linhas + [f"{k} = {v}" for k, v in SYSCTLS.items()]) + "\n"


def texto_journald() -> str:
    return ("# infra/vm/estabilidade.py: o journal sobrevive ao reinício (o boot que caiu fica legível) e tem teto.\n"
            f"[Journal]\nStorage=persistent\nSystemMaxUse={JOURNAL_MAX}\n")


def _gravar_se_mudou(arq: Path, texto: str) -> bool:
    try:
        if arq.read_text(encoding="utf-8") == texto:
            return False
    except OSError:
        pass
    arq.parent.mkdir(parents=True, exist_ok=True)
    tmp = arq.with_name(arq.name + ".tmp")
    tmp.write_text(texto, encoding="utf-8")
    tmp.chmod(0o644)
    tmp.replace(arq)
    return True


def valores_atuais(proc: Path = Path("/proc/sys")) -> dict:
    saida = {}
    for chave in SYSCTLS:
        try:
            saida[chave] = (proc / chave.replace(".", "/")).read_text().strip()
        except OSError:
            saida[chave] = None
    return saida


def aplicar_config() -> list[str]:
    feitos = []
    if _gravar_se_mudou(SYSCTL_ARQ, texto_sysctl()):
        feitos.append(str(SYSCTL_ARQ))
    _cmd("sysctl", "-q", "-p", str(SYSCTL_ARQ))
    if _gravar_se_mudou(JOURNALD_ARQ, texto_journald()):
        feitos.append(str(JOURNALD_ARQ))
        Path("/var/log/journal").mkdir(parents=True, exist_ok=True)
        _cmd("systemctl", "restart", "systemd-journald")
    errados = {k: v for k, v in valores_atuais().items() if v is not None and v != SYSCTLS[k]}
    if errados:
        log(f"o kernel não aceitou: {errados}")
    return feitos


# ------------------------------------------------------------------ pane guardada pelo pstore

def resumo_pane(texto: str) -> dict:
    """Do dmesg da pane (pstore): processo, função onde parou, a pilha (só nomes) e a frase da pane."""
    def primeiro(padrao: str) -> str:
        m = re.search(padrao, texto)
        return m.group(1).strip() if m else ""

    pilha = []
    for m in re.finditer(r"^(?:<\d>)?\[\s*[\d.]+\]\s+([A-Za-z_][\w.]*)\+0x[0-9a-f]+/0x[0-9a-f]+", texto, re.M):
        if m.group(1) not in pilha:
            pilha.append(m.group(1))
    resumo = {
        "processo": primeiro(r"Comm: (\S+)"),
        "kernel": primeiro(r"Not tainted (\S+)") or primeiro(r"Tainted: \S+ (\S+)"),
        "onde": primeiro(r"pc : ([\w.]+)") or primeiro(r"RIP: \S+:([\w.]+)"),
        "erro": primeiro(r"(Unable to handle kernel [^\n]*|BUG: [^\n]*|general protection fault[^\n]*)"),
        "pane": primeiro(r"Kernel panic - not syncing: ([^\n]*)"),
        "pilha": pilha[:12],
    }
    resumo["io_uring"] = any("io_uring" in f or "io_ring" in f for f in pilha)
    return resumo


def frase_pane(r: dict) -> str:
    causa = "no io_uring" if r.get("io_uring") else f"em {r.get('onde') or 'lugar desconhecido'}"
    proc = f", processo {r['processo']}" if r.get("processo") else ""
    return f"falha do kernel {causa}{proc}"


def _texto_do_pstore(pasta: Path) -> str:
    if (pasta / "dmesg.txt").exists():
        return (pasta / "dmesg.txt").read_text(encoding="utf-8", errors="replace")
    return "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in sorted(pasta.glob("dmesg-*")))


def _quando(pasta: Path) -> float:
    datas = [p.stat().st_mtime for p in pasta.glob("dmesg-*")] or [pasta.stat().st_mtime]
    return min(datas)


def coletar_panes(base: Path = PSTORE, enviar=None) -> list[dict]:
    """Cada pasta do pstore ainda não vista: vai ao S3 (enviar(pasta, texto) -> destino) e vira um resumo."""
    novas = []
    if not base.is_dir():
        return novas
    for pasta in sorted(p for p in base.iterdir() if p.is_dir()):
        marca = pasta / ".agentepessoal"
        if marca.exists():
            continue
        texto = _texto_do_pstore(pasta)
        if not texto.strip():
            continue
        r = resumo_pane(texto)
        r["quando"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(_quando(pasta)))
        r["pstore"] = str(pasta)
        r["s3"] = enviar(pasta, texto) if enviar else ""
        marca.write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
        novas.append(r)
    return novas


def _bucket() -> str:
    try:
        for linha in Path("/etc/agentepessoal.env").read_text().splitlines():
            if linha.startswith("BACKUP_BUCKET="):
                return linha.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return ""


def _enviar_s3(pasta: Path, _texto: str) -> str:
    bucket = _bucket()
    if not bucket:
        return ""
    destino = f"s3://{bucket}/incidentes/pstore-{pasta.name}-{time.strftime('%Y%m%d', time.gmtime(_quando(pasta)))}.txt"
    origem = pasta / "dmesg.txt"
    if not origem.exists():
        origem = pasta / "junto.txt"
        origem.write_text(_texto, encoding="utf-8")
    ok = subprocess.run(["/usr/local/bin/aws", "s3", "cp", "--only-show-errors", str(origem), destino],
                        capture_output=True, timeout=120).returncode == 0
    return destino if ok else ""


def mensagem_pane(r: dict) -> str:
    from datetime import datetime, timedelta, timezone

    try:
        quando = datetime.strptime(r["quando"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        hora = (quando - timedelta(hours=3)).strftime("%d/%m %H:%M")
    except (KeyError, ValueError):
        hora = "há pouco"
    return (f"⚠️ A máquina do agente caiu em {hora} (Bahia) por uma {frase_pane(r)} e já voltou. "
            "Está tudo de pé; o registro técnico ficou guardado para o operador.")


def avisar(texto: str, tentativas: int = 20, espera: float = 30) -> bool:
    """Pela ponte do celular (como o saude.py); no boot ela pode demorar a subir."""
    for _ in range(tentativas):
        try:
            corpo = json.dumps({"usuario": "matheus", "texto": texto, "tipo": "progresso"}).encode()
            req = urllib.request.Request("http://127.0.0.1:8789/enviar", data=corpo, headers={
                "Content-Type": "application/json", "X-Chave": CHAVE.read_text().strip()})
            with urllib.request.urlopen(req, timeout=30) as r:
                r.read()
            return True
        except Exception:  # noqa: BLE001 - ponte ainda subindo
            time.sleep(espera)
    return False


# ------------------------------------------------------------------ disco

def imagens_a_remover(imagens: list[dict], em_uso: set, manter: int = MANTER_HERMES) -> list[str]:
    """Imagens antigas do Hermes (cada implantação faz uma de ~5 GB): ficam as usadas por algum contêiner (rodando ou
    parado) e as `manter` mais novas (a volta rápida). imagens: [{"ref", "id", "criada"}]; devolve as refs a tirar."""
    do_hermes = [i for i in imagens if i["ref"].startswith(HERMES_REPO + ":")]
    ids_novos = []
    for i in sorted(do_hermes, key=lambda i: i["criada"], reverse=True):
        if i["id"] not in ids_novos:
            ids_novos.append(i["id"])
    manter_ids = set(ids_novos[:manter]) | set(em_uso)
    return [i["ref"] for i in do_hermes if i["id"] not in manter_ids]


def _imagens() -> list[dict]:
    saida = []
    for linha in _cmd("docker", "images", "--no-trunc", "--format", "{{.Repository}}:{{.Tag}}|{{.ID}}|{{.CreatedAt}}").splitlines():
        partes = linha.split("|")
        if len(partes) == 3 and not partes[0].endswith(":<none>"):
            saida.append({"ref": partes[0], "id": partes[1], "criada": partes[2]})
    return saida


def _em_uso() -> set:
    ids = _cmd("docker", "ps", "-aq", "--no-trunc").split()
    if not ids:
        return set()
    return set(_cmd("docker", "inspect", "-f", "{{.Image}}", *ids).split())


def _livre_gb() -> float:
    import shutil

    return shutil.disk_usage("/").free / 1e9


def limpar() -> dict:
    antes = _livre_gb()
    tirar = imagens_a_remover(_imagens(), _em_uso())
    for ref in tirar:
        _cmd("docker", "rmi", ref, timeout=300)
    _cmd("docker", "image", "prune", "-f", timeout=600)  # só as sem nome e sem contêiner
    _cmd("journalctl", f"--vacuum-size={JOURNAL_MAX}")
    r = {"removidas": tirar, "livre_antes_gb": round(antes, 1), "livre_depois_gb": round(_livre_gb(), 1)}
    log(f"limpeza: {json.dumps(r, ensure_ascii=False)}")
    return r


# ------------------------------------------------------------------ main

def main() -> int:
    acao = sys.argv[1] if len(sys.argv) > 1 else "estado"
    if acao == "aplicar":
        feitos = aplicar_config()
        log(f"config aplicada ({', '.join(feitos) or 'já estava'}): {valores_atuais()}")
        novas = coletar_panes(enviar=_enviar_s3)
        if novas:
            ESTADO.mkdir(parents=True, exist_ok=True)
            PANE.write_text(json.dumps(novas[-1], ensure_ascii=False, indent=1), encoding="utf-8")
            for r in novas:
                log(f"pane de {r['quando']}: {frase_pane(r)} (pilha: {' < '.join(r['pilha'][:6])}; {r['s3'] or 'sem S3'})")
            avisar(mensagem_pane(novas[-1]))
        return 0
    if acao == "limpar":
        limpar()
        return 0
    print(json.dumps({"sysctl": valores_atuais(), "ultima_pane": json.loads(PANE.read_text()) if PANE.exists() else None},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
