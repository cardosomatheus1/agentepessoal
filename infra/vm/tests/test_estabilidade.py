"""infra/vm/estabilidade.py (incidente de 23/10: pane do kernel no io_uring), sem tocar na VM.
Run from the repository root: python3 infra/vm/tests/test_estabilidade.py"""

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]

# trecho real do dmesg que o pstore guardou na pane de 23/10 21:49 UTC (systemd-pstore junta as partes assim)
PANE = """Oops#1 Part1
<1>[648778.523101] Unable to handle kernel paging request at virtual address 0000000020170001
<0>[648778.532136] Internal error: Oops: 0000000096000006 [#1] SMP
<4>[648778.541379] CPU: 3 PID: 1737895 Comm: DelayedTaskSche Not tainted 6.8.0-1066-aws #69~22.04.1-Ubuntu
<4>[648778.542605] Hardware name: Amazon EC2 m8g.xlarge/, BIOS 1.0 11/1/2018
<4>[648778.544428] pc : do_raw_spin_lock+0xc/0xa0
<4>[648778.544983] lr : __queue_work+0xbc/0x4a0
<4>[648778.555701] Call trace:
<4>[648778.556047]  do_raw_spin_lock+0xc/0xa0
<4>[648778.556561]  queue_work_on+0xb8/0x108
<4>[648778.557056]  io_ring_ctx_wait_and_kill+0x110/0x168
<4>[648778.557715]  io_uring_release+0x24/0x50
<4>[648778.558239]  __fput+0x94/0x318
<4>[648778.559135]  __arm64_sys_close+0x44/0xa0
<4>[648778.562334]  el0t_64_sync+0x1b0/0x1b8
<0>[648778.715535] Kernel panic - not syncing: Oops: Fatal exception
"""


def main() -> int:
    spec = importlib.util.spec_from_file_location("estabilidade_teste", RAIZ / "infra" / "vm" / "estabilidade.py")
    e = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(e)
    falhas = []

    def checa(ok, msg):
        if not ok:
            falhas.append(msg)

    # 1. sysctl: io_uring desligado para todos, pane religa, Oops vira pane; journal persistente com teto
    t = e.texto_sysctl()
    for linha in ("kernel.io_uring_disabled = 2", "kernel.panic = 10", "kernel.panic_on_oops = 1"):
        checa(linha in t.splitlines(), f"sysctl sem «{linha}»: {t!r}")
    j = e.texto_journald()
    checa("[Journal]" in j and "Storage=persistent" in j and "SystemMaxUse=" in j, f"journald: {j!r}")
    lr = e.texto_logrotate_syslog()
    checa("/var/log/syslog" in lr and "\tdaily" in lr and "maxsize 200M" in lr and "rotate 3" in lr
          and "rsyslog-rotate" in lr and "su root syslog" in lr and lr.count("{") == 1 == lr.count("}"), f"logrotate do syslog: {lr!r}")

    tmp = Path(tempfile.mkdtemp(prefix="estab-"))
    arq = tmp / "etc" / "x.conf"
    checa(e._gravar_se_mudou(arq, "a\n") and not e._gravar_se_mudou(arq, "a\n") and e._gravar_se_mudou(arq, "b\n"),
          "_gravar_se_mudou: grava só quando muda")
    proc = tmp / "proc"
    (proc / "kernel").mkdir(parents=True)
    (proc / "kernel" / "io_uring_disabled").write_text("2\n")
    (proc / "kernel" / "panic").write_text("-1\n")
    v = e.valores_atuais(proc)
    checa(v["kernel.io_uring_disabled"] == "2" and v["kernel.panic"] == "-1" and v["kernel.panic_on_oops"] is None
          and set(v) == set(e.SYSCTLS), f"valores_atuais: {v}")

    # 1b. 24/10 (travada de 23/10 23:22 sem pane): trava do kernel vira pane; systemd vigiado pelo softdog
    for linha in ("kernel.softlockup_panic = 1", "kernel.panic_on_rcu_stall = 1", "kernel.hung_task_panic = 1",
                  "kernel.hung_task_timeout_secs = 600"):
        checa(linha in t.splitlines(), f"sysctl sem «{linha}»")
    sv = e.texto_systemd_vigia()
    checa("[Manager]" in sv and "RuntimeWatchdogSec=2min" in sv and "RebootWatchdogSec=" in sv, f"systemd vigia: {sv!r}")

    # 2. resumo da pane: processo, onde parou, pilha, que foi no io_uring
    r = e.resumo_pane(PANE)
    checa(r["processo"] == "DelayedTaskSche", f"processo: {r}")
    checa(r["onde"] == "do_raw_spin_lock" and r["kernel"] == "6.8.0-1066-aws", f"onde/kernel: {r}")
    checa(r["pane"] == "Oops: Fatal exception" and r["erro"].startswith("Unable to handle kernel paging request"), f"pane/erro: {r}")
    checa(r["pilha"][:4] == ["do_raw_spin_lock", "queue_work_on", "io_ring_ctx_wait_and_kill", "io_uring_release"],
          f"pilha: {r['pilha']}")
    checa(r["io_uring"] is True and "io_uring" in e.frase_pane(r), f"io_uring: {r}")
    checa(e.resumo_pane("<4>[1.0]  foo+0x1/0x2\nKernel panic - not syncing: x\n")["io_uring"] is False, "sem io_uring na pilha")

    # 3. pstore: cada pasta nova vai uma vez ao S3 e vira resumo; a já vista não volta
    pst = tmp / "pstore"
    (pst / "179279219").mkdir(parents=True)
    (pst / "179279219" / "dmesg.txt").write_text(PANE)
    (pst / "111").mkdir()
    (pst / "111" / "dmesg.txt").write_text(PANE)
    (pst / "111" / ".agentepessoal").write_text("{}")
    (pst / "222").mkdir()
    (pst / "222" / "dmesg-efi_pstore-1").write_text("<4>[1.0]  foo+0x1/0x2\n")
    quando = 1792792184  # 2026-10-23T21:49:44Z
    os.utime(pst / "222" / "dmesg-efi_pstore-1", (quando, quando))
    enviados = []
    novas = e.coletar_panes(pst, enviar=lambda pasta, texto: enviados.append(pasta.name) or f"s3://b/incidentes/{pasta.name}.txt")
    checa([n["pstore"].rsplit("/", 1)[1] for n in novas] == ["179279219", "222"], f"coletar: {novas}")
    checa(enviados == ["179279219", "222"], f"enviados: {enviados}")
    checa((pst / "179279219" / ".agentepessoal").exists(), "marca da pasta coletada")
    checa(json.loads((pst / "179279219" / ".agentepessoal").read_text())["s3"].endswith("179279219.txt"), "marca com o S3")
    checa(novas[1]["quando"] == "2026-10-23T21:49:44Z", f"quando = data dos arquivos da pane: {novas[1]['quando']}")
    checa(e.coletar_panes(pst, enviar=lambda *a: "x") == [], "segunda coleta não repete")
    checa(e.coletar_panes(tmp / "nao_existe") == [], "sem pstore: nada")
    m = e.mensagem_pane({**r, "quando": "2026-10-23T21:49:44Z"})
    checa("23/10 18:49" in m and "io_uring" in m and "voltou" in m, f"mensagem: {m}")

    # 4. imagens antigas do Hermes: ficam a em uso e as 2 mais novas; outras imagens nunca
    imgs = [
        {"ref": "agentepessoal/hermes:aaa", "id": "sha:1", "criada": "2026-10-23 16:00:00 +0000 UTC"},
        {"ref": "agentepessoal/hermes:bbb", "id": "sha:2", "criada": "2026-10-23 15:00:00 +0000 UTC"},
        {"ref": "agentepessoal/hermes:ccc", "id": "sha:3", "criada": "2026-10-23 11:00:00 +0000 UTC"},
        {"ref": "agentepessoal/hermes:ddd", "id": "sha:4", "criada": "2026-10-23 09:00:00 +0000 UTC"},
        {"ref": "agentepessoal/hermes:teste", "id": "sha:5", "criada": "2026-10-22 22:00:00 +0000 UTC"},
        {"ref": "agentepessoal/hermes:eee", "id": "sha:5", "criada": "2026-10-22 22:00:00 +0000 UTC"},
        {"ref": "agentepessoal/hermes-mcp:x", "id": "sha:6", "criada": "2026-10-23 07:00:00 +0000 UTC"},
        {"ref": "agent0ai/agent-zero:v2.13", "id": "sha:7", "criada": "2026-09-23 07:00:00 +0000 UTC"},
        {"ref": "nousresearch/hermes-agent:v0.22.2", "id": "sha:8", "criada": "2026-10-15 07:00:00 +0000 UTC"},
    ]
    tirar = e.imagens_a_remover(imgs, em_uso={"sha:3", "sha:7"})
    checa(sorted(tirar) == ["agentepessoal/hermes:ddd", "agentepessoal/hermes:eee", "agentepessoal/hermes:teste"],
          f"imagens a remover: {tirar}")
    checa(e.imagens_a_remover(imgs[:2], em_uso=set()) == [], "com só 2 imagens do Hermes nada sai")

    # 5. vigia da rede (24/10): conserta aos 4 min, religa aos 10 (não logo depois de ligar), no máximo 3 vezes em 6 h
    T0 = 1_800_000_000.0
    checa(e.decidir_rede(True, {}, [], T0, 9999) == ("nada", {}), "rede ok: nada")
    checa(e.decidir_rede(True, {"falhando_desde": T0 - 300}, [], T0, 9999)[0] == "voltou", "rede voltou")
    a, st = e.decidir_rede(False, {}, [], T0, 9999)
    checa(a == "nada" and st["falhando_desde"] == T0, f"primeira falha só marca: {a} {st}")
    a, st = e.decidir_rede(False, st, [], T0 + 250, 9999)
    checa(a == "consertar" and st["consertou"], f"4 min: conserta: {a} {st}")
    a, st2 = e.decidir_rede(False, st, [], T0 + 300, 9999)
    checa(a == "nada", f"conserta uma vez só: {a}")
    a, _ = e.decidir_rede(False, st, [], T0 + 601, 9999)
    checa(a == "reiniciar", f"10 min: religa: {a}")
    a, _ = e.decidir_rede(False, st, [], T0 + 601, 600)
    checa(a == "nada", f"VM no ar há só 10 min: não religa (tudo subindo): {a}")
    tres = [T0 - 3600, T0 - 1800, T0 - 600]
    a, st3 = e.decidir_rede(False, st, tres, T0 + 601, 9999)
    checa(a == "segurar" and st3["segurou"], f"3 religadas em 6 h: segura: {a}")
    checa(e.decidir_rede(False, st3, tres, T0 + 700, 9999)[0] == "nada", "segura avisando uma vez só")
    antigos = [T0 - 7 * 3600] * 5
    checa(e.decidir_rede(False, st, antigos, T0 + 601, 9999)[0] == "reiniciar", "religadas antigas não contam")
    chamados = []

    def conectar(host, porta):
        chamados.append(host)
        if host != "s3.us-east-1.amazonaws.com":
            raise OSError("sem rota")
    checa(e.alcanca(conectar=conectar) is True and chamados[:2] == ["ssm.us-east-1.amazonaws.com", "s3.us-east-1.amazonaws.com"],
          f"alcanca: basta um alvo: {chamados}")
    checa(e.alcanca(conectar=lambda h, p: (_ for _ in ()).throw(OSError("x"))) is False, "alcanca: nenhum responde")

    # 6. no boot, o religamento pendente vai ao S3 e vira o último (com aviso)
    e.ESTADO = tmp / "estado"
    e.REDE_PENDENTE, e.REDE_ULTIMO = e.ESTADO / "rede_pendente.json", e.ESTADO / "rede_ultimo.json"
    checa(e.entregar_rede(enviar=lambda a: "x") is None, "sem pendente: nada")
    diag = tmp / "rede-20261023T234000Z.txt"
    diag.write_text("diag")
    e._gravar_json(e.REDE_PENDENTE, {"quando": "2026-10-23T23:40:00Z", "sem_rede_desde": "2026-10-23T23:22:00Z",
                                     "diagnostico": str(diag)})
    r = e.entregar_rede(enviar=lambda a: f"s3://b/incidentes/{a.name}")
    checa(r and r["s3"].endswith("rede-20261023T234000Z.txt") and not e.REDE_PENDENTE.exists()
          and json.loads(e.REDE_ULTIMO.read_text())["s3"] == r["s3"], f"entregar_rede: {r}")
    m = e.mensagem_rede(r)
    checa("23/10 20:22" in m and "sem internet" in m and "voltou" in m, f"mensagem_rede: {m}")

    # 27/10: limpeza das cópias do OpenCode e do cache em /tmp: só sai o que não tem nada a perder
    import subprocess
    import time as _t
    base = Path(tempfile.mkdtemp())
    g = lambda *a, cwd=None: subprocess.run(["git", "-c", "commit.gpgsign=false", *a], cwd=cwd, check=True,
                                            capture_output=True)
    remoto = base / "remoto.git"
    g("init", "-q", "--bare", str(remoto))
    proj = base / "projects"
    proj.mkdir()
    principal = proj / "erp-saas"
    g("clone", "-q", str(remoto), str(principal))
    for k, v in (("user.email", "t@t"), ("user.name", "t"), ("commit.gpgsign", "false")):
        g("config", k, v, cwd=principal)
    (principal / "a.txt").write_text("a")
    (principal / ".gitignore").write_text("node_modules/\n")
    g("add", ".", cwd=principal); g("commit", "-qm", "a", cwd=principal); g("push", "-q", "origin", "HEAD:master", cwd=principal)
    for nome in ("velha-limpa", "velha-suja", "velha-sem-push", "recente", "velha-env", "velha-outro-ramo"):
        g("worktree", "add", "-q", "-b", nome, str(proj / nome), "master", cwd=principal)
        g("config", "commit.gpgsign", "false", cwd=proj / nome)
    (proj / "velha-suja" / "a.txt").write_text("mudou")
    (proj / "velha-sem-push" / "b.txt").write_text("b")
    g("add", ".", cwd=proj / "velha-sem-push"); g("commit", "-qm", "b", cwd=proj / "velha-sem-push")
    (proj / "velha-env" / ".gitignore").write_text("node_modules/\n.env\n")
    g("add", ".", cwd=proj / "velha-env"); g("commit", "-qm", "ign", cwd=proj / "velha-env")
    g("push", "-q", "origin", "velha-env", cwd=proj / "velha-env")
    (proj / "velha-env" / ".env").write_text("SEGREDO=1")
    g("branch", "lateral", cwd=proj / "velha-outro-ramo")
    (proj / "velha-outro-ramo" / "c.txt").write_text("c")
    g("checkout", "-q", "lateral", cwd=proj / "velha-outro-ramo")
    g("add", ".", cwd=proj / "velha-outro-ramo"); g("commit", "-qm", "c", cwd=proj / "velha-outro-ramo")
    g("checkout", "-q", "velha-outro-ramo", cwd=proj / "velha-outro-ramo")
    (proj / "velha-limpa" / ".gitignore").write_text("node_modules/\n*.tsbuildinfo\ne2e/.auth/\ne2e-artifacts/\n")
    g("add", ".", cwd=proj / "velha-limpa"); g("commit", "-qm", "ign", cwd=proj / "velha-limpa")
    g("push", "-q", "origin", "velha-limpa", cwd=proj / "velha-limpa")
    (proj / "velha-limpa" / "web.tsbuildinfo").write_text("{}")
    (proj / "velha-limpa" / "e2e" / ".auth").mkdir(parents=True)
    (proj / "velha-limpa" / "e2e" / ".auth" / "dono.json").write_text("{}")
    (proj / "velha-limpa" / "e2e-artifacts").mkdir()
    (proj / "velha-limpa" / "node_modules").mkdir()
    (proj / "velha-limpa" / "node_modules" / "x").write_text("x")
    avulso = proj / "clone-avulso"  # clone (não worktree) com um ramo local não enviado: fica
    g("clone", "-q", str(remoto), str(avulso))
    for k, v in (("user.email", "t@t"), ("user.name", "t"), ("commit.gpgsign", "false")):
        g("config", k, v, cwd=avulso)
    g("checkout", "-q", "-b", "so-local", cwd=avulso)
    (avulso / "d.txt").write_text("d")
    g("add", ".", cwd=avulso); g("commit", "-qm", "d", cwd=avulso)
    g("checkout", "-q", "master", cwd=avulso)
    velho = _t.time() - 3 * 86400
    for raiz, dirs, arqs in os.walk(proj):
        for n in dirs + arqs:
            os.utime(os.path.join(raiz, n), (velho, velho), follow_symlinks=False)
    (proj / "recente" / "a.txt").write_text("a")  # mexida agora (mesmo conteúdo: git limpo)
    motivos = {p.name: e.projeto_parado(p) for p in proj.iterdir()}
    checa(motivos == {"erp-saas": "principal", "velha-limpa": "", "velha-suja": "tem mudança ou arquivo novo",
                      "velha-sem-push": "último commit não está no GitHub", "recente": "mexida nas últimas 24 h",
                      "velha-env": "arquivo ignorado pelo git que não se refaz (.env)",
                      "velha-outro-ramo": "", "clone-avulso": "algum ramo tem commit que não está no GitHub"},
          f"projeto_parado: {motivos}")
    tirados = e.limpar_projetos(proj)
    lista = subprocess.run(["git", "-C", str(principal), "worktree", "list"], capture_output=True, text=True).stdout
    checa(tirados == ["velha-limpa", "velha-outro-ramo"] and not (proj / "velha-limpa").exists()
          and "lateral" in subprocess.run(["git", "-C", str(principal), "branch"], capture_output=True, text=True).stdout and "velha-limpa" not in lista
          and (proj / "velha-suja").exists() and (proj / "velha-sem-push").exists(),
          f"limpar_projetos tira só a limpa, parada e no GitHub: {tirados} / {lista}")
    tmp = base / "tmp"
    (tmp / "jest_rt" / "antigo").mkdir(parents=True)
    (tmp / "jest_rt" / "novo").mkdir()
    (tmp / "tmpvelho").mkdir()
    (tmp / "outra-coisa").mkdir()
    (tmp / "tmpvivo").mkdir()
    (tmp / "tmpvivo" / "em-uso").write_text("x")  # pasta antiga com arquivo mexido agora: fica
    for p in (tmp / "jest_rt" / "antigo", tmp / "tmpvelho", tmp / "outra-coisa", tmp / "tmpvivo"):
        os.utime(p, (velho, velho))
    checa(e.limpar_cache_tmp(tmp) == 2 and (tmp / "jest_rt" / "novo").exists() and (tmp / "outra-coisa").exists()
          and not (tmp / "tmpvelho").exists() and (tmp / "tmpvivo").exists(), "cache: só jest_rt e tmp* antigos")
    imgs_a0 = [{"ref": "agent0ai/agent-zero:v2.13", "id": "sha:a0", "criada": "2026-09-01"}]
    checa(e.imagens_a_remover(imgs_a0, em_uso=set()) == [], "a imagem do A0 (base da cópia de teste) nunca sai")

    print(f"TESTES {'ok' if not falhas else 'FALHOU'}")
    for f in falhas:
        print("  ✗", f)
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
