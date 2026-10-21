"""Independent review of a fix by OpenCode 2 with Claude Opus 5.5 on the VM, before it stays live.

Matheus's standing decision (Segundo Cérebro #35): "Para qualquer alteração de código, usar OpenCode 2 com Opus 5.5 e
informar Matheus que esse modelo foi utilizado". 21/10: "N consegue ele chamar o opencode2 com opus 5.5 p verificar?".
The nightly fix session (docs/CONSERTO_NOTURNO.md) and any operator session send the diff of their commits here; the
reviewer reads it next to the live code (/a0/usr/plugins) and Agent Zero's code (/a0/plugins), changes nothing, and
ends with "VEREDITO: APROVADO" or "VEREDITO: REPROVADO".

Usage, from the repository root:  python3 infra/operador/revisar_opencode.py [git range, default HEAD~1..HEAD] ["what
the fix is for"]   -> prints the review; exit 0 approved, 1 rejected, 2 the review did not run."""

import base64
import re
import subprocess
import sys
import time
from pathlib import Path

OPENCODE = "/root/.opencode/bin/opencode2"
MODELO = "amazon-bedrock/global.anthropic.claude-opus-5-5"
DIFF_MAX = 120_000
BUCKET = "s3://agentepessoal-backup-964862484412/operador"

PEDIDO = """Você é o revisor independente de uma correção no agente pessoal do Matheus (plugins do Agent Zero).
NÃO altere nenhum arquivo e não rode nada que mude o sistema: só leia. O diff está em {diff}.
Contexto: o código que roda hoje está em /a0/usr/plugins (os plugins) e o do Agent Zero em /a0/plugins e /a0/helpers.
Motivo da correção: {motivo}

Confira, nesta ordem:
1. A correção resolve a falha descrita, inclusive na chamada real que o teste reproduz?
2. Quebra algo que funcionava (outras ações, outros sites, o servidor que já está rodando sem reiniciar: correção que
   embrulha método precisa de marca com versão e do original guardado)?
3. O teste falharia sem a correção (ou passa de qualquer jeito)?
4. Algum risco de segurança ou de agir sem querer (clicar, enviar, apagar)?
Seja objetivo: só aponte problema real, com arquivo e linha. Termine com UMA linha exatamente assim:
VEREDITO: APROVADO   (nada que impeça ficar no ar)
ou
VEREDITO: REPROVADO — <o problema principal em uma frase>"""


FIM = "__FIM_OPENCODE="
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def veredito(saida: str) -> str:
    """'aprovado', 'reprovado' or '' (the review did not finish: opencode exited with an error or timed out, or its LAST
    line is not the verdict). The prompt and the files the reviewer reads also contain "VEREDITO:" (OpenCode review of
    this script, 21/10): only the final line of a run that ended well counts."""
    texto = _ANSI.sub("", str(saida or ""))
    fim = re.findall(rf"{FIM}(\d+)", texto)
    if not fim or fim[-1] != "0":
        return ""
    linhas = [re.sub(r"[*`_]", "", l).strip() for l in texto[:texto.rindex(FIM)].splitlines() if l.strip()]
    m = re.match(r"VEREDITO:\s*(APROVADO|REPROVADO)\b", linhas[-1], re.I) if linhas else None
    return m.group(1).lower() if m else ""


def comando_vm(chave_s3: str, pasta: str, motivo: str) -> str:
    pedido = PEDIDO.format(diff=f"{pasta}/diff.patch", motivo=motivo or "(não informado)")
    p64 = base64.b64encode(pedido.encode("utf-8")).decode()
    return (f"aws s3 cp {BUCKET}/{chave_s3} /tmp/{chave_s3} >/dev/null && "
            f"docker exec agent-zero mkdir -p {pasta} && docker cp /tmp/{chave_s3} agent-zero:{pasta}/diff.patch && "
            f"echo {p64} | base64 -d > /tmp/{chave_s3}.pedido && docker cp /tmp/{chave_s3}.pedido agent-zero:{pasta}/pedido.md && "
            f"docker exec -w /a0/usr agent-zero sh -c 'timeout 900 {OPENCODE} run --model {MODELO} "
            f"\"$(cat {pasta}/pedido.md)\" > {pasta}/revisao.md 2>&1; rc=$?; tail -c 6000 {pasta}/revisao.md; echo; echo {FIM}$rc'")


def main(argv: list) -> int:
    faixa = argv[0] if argv else "HEAD~1..HEAD"
    motivo = argv[1] if len(argv) > 1 else ""
    raiz = Path(__file__).resolve().parents[2]
    diff = subprocess.run(["git", "-C", str(raiz), "log", "-p", "--format=commit %h%n%B", faixa],
                          capture_output=True, text=True, check=True).stdout
    if not diff.strip():
        print("nada a revisar nessa faixa")
        return 2
    if len(diff) > DIFF_MAX:
        diff = diff[:DIFF_MAX] + "\n[... diff cortado ...]\n"
    chave = f"revisao_{int(time.time())}.patch"
    local = Path("/tmp") / chave
    local.write_text(diff, encoding="utf-8")
    subprocess.run(["aws", "s3", "cp", str(local), f"{BUCKET}/{chave}"], check=True, capture_output=True)
    pasta = f"/a0/usr/workdir/revisao_opencode/{chave[:-6]}"
    vm = Path(__file__).resolve().parent / "vmcmd.py"
    saida = subprocess.run([sys.executable, str(vm), comando_vm(chave, pasta, motivo)],
                           capture_output=True, text=True).stdout
    print(saida.strip())
    print(f"\n(revisão completa na VM: {pasta}/revisao.md; revisor: OpenCode 2 com {MODELO.split('/')[-1]})")
    v = veredito(saida)
    return 0 if v == "aprovado" else 1 if v == "reprovado" else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
