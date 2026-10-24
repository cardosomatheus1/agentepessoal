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
    estabilidade.py rede      (a cada minuto, agentepessoal-vigia-rede.timer; 24/10, ver abaixo)
    estabilidade.py estado    (só mostra)

24/10, 23:22 UTC de 23/10: a VM "perdeu a rede" com as checagens da AWS "ok": o journal parou no meio de uma rajada de
erros do binder (o driver do celular virtual: "undelivered death notification", "cannot find target node",
"transaction failed"), um núcleo ficou a 100% e a saída de rede caiu a ~4 KB a cada 5 min (só o kernel respondendo ARP).
Ou seja: o kernel travou por dentro sem dar pane, e nada religou. Desde então:
    - travas do kernel viram pane (e a pane religa em 10 s, com rastro no pstore): CPU presa no kernel (softlockup),
      RCU parado, tarefa presa em D por 10 min (hung task);
    - o systemd é vigiado pelo softdog (o "cão de guarda" de software do kernel): se o PID 1 parar de responder por
      2 min, pane e religa (soft_panic: fica o rastro);
    - o vigia da rede (`rede`): sem alcançar a AWS nem a internet por 4 min, refaz a rede; por 10 min (e a VM no ar há
      15+ min), guarda o diagnóstico e religa — no máximo 3 vezes em 6 h (sem ciclo). No boot seguinte o diagnóstico
      vai ao S3 (incidentes/rede-*.txt) e o Matheus é avisado;
    - fora da VM, o alarme `agentepessoal-vm-sem-rede` (infra/control/recuperar.py) religa se a saída de rede ficar
      quase zero por 15 min (pega o caso em que nem este vigia roda).

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
    # 24/10 (travada de 23/10 23:22 sem pane): trava do kernel = pane = religa em 10 s com rastro no pstore
    "kernel.softlockup_panic": "1",  # um núcleo preso no kernel por 20 s
    "kernel.panic_on_rcu_stall": "1",  # RCU parado (o kernel não avança)
    "kernel.hung_task_panic": "1",  # tarefa presa em D (sem poder ser morta) ...
    "kernel.hung_task_timeout_secs": "600",  # ... por 10 min
}
# 24/10: o systemd (PID 1) vigiado pelo softdog; soft_panic=1 faz pane (rastro no pstore) em vez de religar seco
SOFTDOG_MODULO = Path("/etc/modules-load.d/agentepessoal-softdog.conf")
SOFTDOG_OPCOES = Path("/etc/modprobe.d/agentepessoal-softdog.conf")
SYSTEMD_VIGIA = Path("/etc/systemd/system.conf.d/agentepessoal-vigia.conf")
JOURNALD_ARQ = Path("/etc/systemd/journald.conf.d/agentepessoal.conf")
JOURNAL_MAX = "800M"
# 24/10: o /var/log/syslog chegou a 967 MB (o rsyslog só girava por semana, ~160 MB/dia de systemd); o journal já guarda
# tudo, então o syslog gira todo dia, guarda 3 e tem teto
LOGROTATE_SYSLOG = Path("/etc/logrotate.d/rsyslog")
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


def texto_logrotate_syslog() -> str:
    arquivos = [f"/var/log/{n}" for n in ("syslog", "mail.info", "mail.warn", "mail.err", "mail.log", "daemon.log",
                                          "kern.log", "auth.log", "user.log", "lpr.log", "cron.log", "debug", "messages")]
    return ("# infra/vm/estabilidade.py (24/10): todo dia, 3 cópias, teto de 200 MB por arquivo\n"
            + "\n".join(arquivos) + "\n{\n\trotate 3\n\tdaily\n\tmaxsize 200M\n\tmissingok\n\tnotifempty\n\tcompress\n"
            "\tdelaycompress\n\tsharedscripts\n\tpostrotate\n\t\t/usr/lib/rsyslog/rsyslog-rotate\n\tendscript\n}\n")


def texto_systemd_vigia() -> str:
    return ("# infra/vm/estabilidade.py (24/10): o PID 1 avisa o softdog; parado 2 min = pane e religa.\n"
            "[Manager]\nRuntimeWatchdogSec=2min\nRebootWatchdogSec=10min\n")


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
    if _gravar_se_mudou(LOGROTATE_SYSLOG, texto_logrotate_syslog()):
        feitos.append(str(LOGROTATE_SYSLOG))
    novo_softdog = _gravar_se_mudou(SOFTDOG_OPCOES, "options softdog soft_panic=1\n")
    novo_softdog |= _gravar_se_mudou(SOFTDOG_MODULO, "softdog\n")
    _cmd("modprobe", "softdog")
    if _gravar_se_mudou(SYSTEMD_VIGIA, texto_systemd_vigia()) or novo_softdog:
        feitos.append(str(SYSTEMD_VIGIA))
        if Path("/dev/watchdog").exists():
            # o PID 1 relê o system.conf e passa a avisar o softdog; fora deste job (que pode ser um `systemctl restart`)
            _cmd("systemd-run", "--on-active=20", "--unit=agentepessoal-reexec", "/bin/systemctl", "daemon-reexec")
        else:
            log("softdog não carregou (/dev/watchdog ausente): o systemd fica sem cão de guarda")
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


# ------------------------------------------------------------------ vigia da rede (24/10)

REDE_ALVOS = (("ssm.us-east-1.amazonaws.com", 443), ("s3.us-east-1.amazonaws.com", 443), ("www.google.com", 443))
REDE_ESTADO = ESTADO / "rede_vigia.json"  # {"falhando_desde": epoch | None, "consertou": bool, "segurou": bool}
REDE_REINICIOS = ESTADO / "rede_reinicios.json"  # [epoch, ...] (sobrevive ao reinício)
REDE_PENDENTE = ESTADO / "rede_pendente.json"  # gravado antes de religar; no boot seguinte vai ao S3 e vira aviso
REDE_ULTIMO = ESTADO / "rede_ultimo.json"  # o último religamento pela rede (o saude.py mostra por 2 dias)
INCIDENTES = ESTADO / "incidentes"
REDE_CONSERTAR_S = 4 * 60
REDE_REINICIAR_S = 10 * 60
REDE_BOOT_S = 15 * 60  # logo depois de ligar, não religa por rede (tudo ainda subindo)
REDE_LIMITE, REDE_JANELA = 3, 6 * 3600


def alcanca(alvos=REDE_ALVOS, conectar=None, timeout: float = 5) -> bool:
    """Rede de pé = pelo menos um alvo (nome resolvido pelo DNS + conexão TCP) responde."""
    import socket

    conectar = conectar or (lambda host, porta: socket.create_connection((host, porta), timeout=timeout).close())
    for host, porta in alvos:
        try:
            conectar(host, porta)
            return True
        except OSError:
            continue
    return False


def decidir_rede(ok: bool, estado: dict, reinicios: list, agora: float, no_ar_s: float) -> tuple[str, dict]:
    """Uma rodada do vigia: ("nada" | "voltou" | "consertar" | "reiniciar" | "segurar", estado novo). Puro (testável)."""
    if ok:
        return ("voltou" if estado.get("falhando_desde") else "nada"), {}
    desde = estado.get("falhando_desde") or agora
    novo = {**estado, "falhando_desde": desde}
    fora = agora - desde
    if fora >= REDE_REINICIAR_S and no_ar_s >= REDE_BOOT_S:
        recentes = [t for t in reinicios if agora - t < REDE_JANELA]
        if len(recentes) >= REDE_LIMITE:
            return ("nada" if estado.get("segurou") else "segurar"), {**novo, "segurou": True}
        return "reiniciar", novo
    if fora >= REDE_CONSERTAR_S and not estado.get("consertou"):
        return "consertar", {**novo, "consertou": True}
    return "nada", novo


def _ler_json(arq: Path, padrao):
    try:
        return json.loads(arq.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return padrao


def _gravar_json(arq: Path, dados) -> None:
    arq.parent.mkdir(parents=True, exist_ok=True)
    tmp = arq.with_name(arq.name + ".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    tmp.replace(arq)


def _no_ar_s() -> float:
    try:
        return float(Path("/proc/uptime").read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return 0.0


def diagnostico_rede() -> str:
    partes = []
    for cmd in (["date", "-u"], ["uptime"], ["ip", "-s", "link"], ["ip", "addr"], ["ip", "route"],
                ["resolvectl", "status"], ["ss", "-s"], ["free", "-m"], ["sysctl", "net.netfilter.nf_conntrack_count",
                "net.netfilter.nf_conntrack_max"], ["docker", "ps", "--format", "{{.Names}} {{.Status}}"],
                ["journalctl", "-k", "-b", "-n", "300", "--no-pager"]):
        partes.append(f"$ {' '.join(cmd)}\n{_cmd(*cmd, timeout=20)}")
    return "\n".join(partes)


def vigiar_rede(agora: float | None = None) -> str:
    agora = agora or time.time()
    estado = _ler_json(REDE_ESTADO, {})
    reinicios = _ler_json(REDE_REINICIOS, [])
    acao, novo = decidir_rede(alcanca(), estado, reinicios, agora, _no_ar_s())
    _gravar_json(REDE_ESTADO, novo)
    if acao == "voltou":
        log(f"vigia da rede: a rede voltou depois de {int((agora - estado['falhando_desde']) / 60)} min")
    elif acao == "consertar":
        log("vigia da rede: sem AWS nem internet há 4 min; refazendo a rede (networkctl reconfigure)")
        for iface in sorted(p.name for p in Path("/sys/class/net").glob("e*")):
            _cmd("networkctl", "reconfigure", iface, timeout=30)
        _cmd("systemctl", "restart", "systemd-resolved", timeout=30)
    elif acao == "segurar":
        log(f"vigia da rede: sem rede há {int((agora - novo['falhando_desde']) / 60)} min, mas já religuei "
            f"{REDE_LIMITE} vezes em 6 h: não religo de novo (fica para o alarme da AWS e o operador)")
    elif acao == "reiniciar":
        quando = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(agora))
        INCIDENTES.mkdir(parents=True, exist_ok=True)
        arq = INCIDENTES / f"rede-{quando}.txt"
        arq.write_text(diagnostico_rede(), encoding="utf-8")
        _gravar_json(REDE_PENDENTE, {"quando": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(agora)),
                                     "sem_rede_desde": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(novo["falhando_desde"])),
                                     "diagnostico": str(arq)})
        _gravar_json(REDE_REINICIOS, [t for t in reinicios if agora - t < REDE_JANELA] + [agora])
        _gravar_json(REDE_ESTADO, {})
        log(f"vigia da rede: sem AWS nem internet há {int((agora - novo['falhando_desde']) / 60)} min; religando a VM "
            f"(diagnóstico em {arq})")
        _cmd("sync")
        if subprocess.run(["systemctl", "reboot"], check=False).returncode != 0:
            subprocess.run(["reboot", "-f"], check=False)
    return acao


def mensagem_rede(r: dict) -> str:
    from datetime import datetime, timedelta, timezone

    try:
        quando = datetime.strptime(r["sem_rede_desde"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        hora = (quando - timedelta(hours=3)).strftime("%d/%m %H:%M")
    except (KeyError, ValueError):
        hora = "há pouco"
    return (f"⚠️ A máquina do agente ficou sem internet desde {hora} (Bahia) e se reiniciou sozinha; já voltou. "
            "Está tudo de pé; o registro técnico ficou guardado para o operador.")


def entregar_rede(enviar=None) -> dict | None:
    """No boot: o religamento pela rede que ficou pendente vai ao S3 e vira o último (o aviso é com quem chama)."""
    r = _ler_json(REDE_PENDENTE, None)
    if not r:
        return None
    arq = Path(r.get("diagnostico") or "")
    r["s3"] = (enviar or _enviar_incidente)(arq) if arq.exists() else ""
    _gravar_json(REDE_ULTIMO, r)
    REDE_PENDENTE.unlink(missing_ok=True)
    return r


def _enviar_incidente(arq: Path) -> str:
    bucket = _bucket()
    if not bucket:
        return ""
    destino = f"s3://{bucket}/incidentes/{arq.name}"
    ok = subprocess.run(["/usr/local/bin/aws", "s3", "cp", "--only-show-errors", str(arq), destino],
                        capture_output=True, timeout=120).returncode == 0
    return destino if ok else ""


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
        if rede := entregar_rede():
            log(f"religamento pela rede de {rede['quando']} entregue ({rede['s3'] or 'sem S3'})")
            avisar(mensagem_rede(rede))
        return 0
    if acao == "rede":
        vigiar_rede()
        return 0
    if acao == "limpar":
        limpar()
        return 0
    print(json.dumps({"sysctl": valores_atuais(), "ultima_pane": json.loads(PANE.read_text()) if PANE.exists() else None},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
