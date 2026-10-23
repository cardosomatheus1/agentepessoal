"""The person's decisions register on the VM (plugin memoria_pessoal), through the helper's own functions; the JSON is
never edited by hand (CLAUDE.md). Usage, from the repository root:

    python3 infra/operador/decisoes.py listar [--login matheus]
    python3 infra/operador/decisoes.py registrar <tema> <tipo> "<decisão>" ["<palavras dele>"] --motivo "<por quê>"
    python3 infra/operador/decisoes.py revogar <número|tema> --motivo "<por quê>"
    python3 infra/operador/decisoes.py semear infra/operador/decisoes_iniciais.json --motivo "<por quê>"

tipo: decisao | permissao | proibicao | preferencia. Changes are recorded with por="operador: <motivo>"; the same text
on the same tema again changes nothing, so "semear" can run twice."""

import base64
import json
import sys
import time
from pathlib import Path

import boto3

VM = "i-0498b4f39560b01a9"
HELPER = "/a0/usr/plugins/memoria_pessoal/helpers/decisoes.py"
ssm = boto3.client("ssm", region_name="us-east-1")

PROGRAMA = """
import importlib.util, json, sys
p = json.loads(sys.argv[1])
s = importlib.util.spec_from_file_location("decisoes_operador", %r)
d = importlib.util.module_from_spec(s); s.loader.exec_module(d)
por = "operador: " + p["motivo"]
if p["op"] == "listar":
    for x in d.ativas(p["login"]):
        print(d.linha(x) + (' — palavras: "%%s"' %% x["citacao"] if x.get("citacao") else ""))
    print("EM VIGOR", len(d.ativas(p["login"])))
elif p["op"] == "revogar":
    x = d.revogar(p["login"], p["ref"], motivo=p["motivo"], por=por)
    print("REVOGADA", x["id"], x["tema"]) if x else print("NADA EM VIGOR COM", p["ref"])
else:
    for it in p["itens"]:
        r = d.registrar(p["login"], it["tema"], it["decisao"], tipo=it.get("tipo", "decisao"),
                        citacao=it.get("citacao", ""), origem=p["motivo"], por=por)
        print(r["efeito"].upper(), "#%%s" %% r["id"], r["tema"])
    print("EM VIGOR", len(d.ativas(p["login"])))
""" % HELPER


def vm(comando: str, timeout: int = 300) -> str:
    cid = ssm.send_command(InstanceIds=[VM], DocumentName="AWS-RunShellScript",
                           Parameters={"commands": [comando]}, TimeoutSeconds=timeout)["Command"]["CommandId"]
    for _ in range(timeout // 3):
        time.sleep(3)
        try:
            r = ssm.get_command_invocation(CommandId=cid, InstanceId=VM)
        except ssm.exceptions.InvocationDoesNotExist:
            continue
        if r["Status"] not in ("Pending", "InProgress", "Delayed"):
            return (r["StandardOutputContent"] + r["StandardErrorContent"]).strip()
    raise SystemExit("a VM não respondeu a tempo")


def main() -> None:
    args = sys.argv[1:]
    opcoes = {}
    for chave in ("--login", "--motivo"):
        if chave in args:
            i = args.index(chave)
            opcoes[chave] = args[i + 1]
            del args[i:i + 2]
    if not args or args[0] not in ("listar", "registrar", "revogar", "semear"):
        raise SystemExit(__doc__)
    op, login, motivo = args[0], opcoes.get("--login", "matheus"), opcoes.get("--motivo", "")
    if op != "listar" and not motivo:
        raise SystemExit("diga o motivo com --motivo \"...\" (fica registrado em quem mudou)")
    p = {"op": op, "login": login, "motivo": motivo}
    if op == "registrar":
        if len(args) < 4:
            raise SystemExit(__doc__)
        p["itens"] = [{"tema": args[1], "tipo": args[2], "decisao": args[3], "citacao": args[4] if len(args) > 4 else ""}]
    elif op == "semear":
        p["itens"] = json.loads(Path(args[1]).read_text(encoding="utf-8"))
        p["op"] = "registrar"
    elif op == "revogar":
        p["ref"] = args[1]
    programa = base64.b64encode(PROGRAMA.encode()).decode()
    dados = base64.b64encode(json.dumps(p, ensure_ascii=False).encode()).decode()
    print(vm(f"echo {programa} | base64 -d > /tmp/decisoes_operador.py && "
             f"/opt/agentepessoal/a0py /tmp/decisoes_operador.py "
             f"\"$(echo {dados} | base64 -d)\""))


if __name__ == "__main__":
    main()
