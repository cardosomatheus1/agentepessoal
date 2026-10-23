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

    tmp = Path(tempfile.mkdtemp(prefix="estab-"))
    arq = tmp / "etc" / "x.conf"
    checa(e._gravar_se_mudou(arq, "a\n") and not e._gravar_se_mudou(arq, "a\n") and e._gravar_se_mudou(arq, "b\n"),
          "_gravar_se_mudou: grava só quando muda")
    proc = tmp / "proc"
    (proc / "kernel").mkdir(parents=True)
    (proc / "kernel" / "io_uring_disabled").write_text("2\n")
    (proc / "kernel" / "panic").write_text("-1\n")
    v = e.valores_atuais(proc)
    checa(v == {"kernel.io_uring_disabled": "2", "kernel.panic": "-1", "kernel.panic_on_oops": None}, f"valores_atuais: {v}")

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

    print(f"TESTES {'ok' if not falhas else 'FALHOU'}")
    for f in falhas:
        print("  ✗", f)
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
