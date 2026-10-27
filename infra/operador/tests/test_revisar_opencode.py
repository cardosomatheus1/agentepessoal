"""The OpenCode review command (infra/operador/revisar_opencode.py): on the host it moves its managed service off the
port the phone's OpenCode holds (27/10), and only a run that ended well with the verdict as its last line counts.
Run from the repository root: python3 infra/operador/tests/test_revisar_opencode.py"""
import importlib.util
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("revisar_opencode", RAIZ / "infra" / "operador" / "revisar_opencode.py")
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)
falhas = []
cmd = r.comando_vm("x.patch", "/a0/usr/workdir/revisao_opencode/t", "teste")
no_host = cmd.split("else", 1)[1]
if f"service set port {r.PORTA_SERVICO}" not in no_host or no_host.index("service set port") > no_host.index("run --model"):
    falhas.append("no host o revisor troca a porta do serviço antes de rodar")
if r.PORTA_SERVICO == 49374:
    falhas.append("a porta do revisor não pode ser a do OpenCode do celular")
if r.veredito("...\nVEREDITO: APROVADO\n__FIM_OPENCODE=0") != "aprovado":
    falhas.append("veredito aprovado no fim de uma execução boa")
if r.veredito("Error: Bedrock is unable to process your request.\n__FIM_OPENCODE=1") != "":
    falhas.append("execução que caiu não vale como veredito")
# 27/10: the global Opus profile was down for half an hour while the us one answered
if not r.fora_do_ar("\x1b[91mError: \x1b[0mBedrock is unable to process your request.\n__FIM_OPENCODE=1"):
    falhas.append("Bedrock fora do ar é reconhecido")
if r.fora_do_ar("VEREDITO: REPROVADO — x\n__FIM_OPENCODE=0") or r.fora_do_ar("Error: model not found\n__FIM_OPENCODE=1"):
    falhas.append("veredito ou outro erro não troca de perfil")
if r.MODELOS[0] != r.MODELO or not r.MODELOS[1].endswith("us.anthropic.claude-opus-5-5"):
    falhas.append("tenta o global e depois o us, o mesmo Opus 5.5")
if f"run --model {r.MODELOS[1]} " not in r.comando_vm("x.patch", "/p", "m", r.MODELOS[1]):
    falhas.append("o comando usa o perfil pedido")
if falhas:
    sys.exit("test_revisar_opencode: " + "; ".join(falhas))
print("test_revisar_opencode: ok")
