"""The person's ficha ("Sobre você", plugin memoria_pessoal) on the VM, through the helper's own functions; the file is
never edited by hand (CLAUDE.md). Usage, from the repository root, after memoria_pessoal 1.2.0 is deployed:

    python3 infra/operador/ficha.py ver [--login matheus]                 (shows what the migration would do; writes nothing)
    python3 infra/operador/ficha.py migrar --motivo "<por quê>" [--login matheus]

`migrar` turns the old free-text ficha into entries (one per line, for the `ficha` tool), keeps the original as
usuarios/<login>.antes-ficha-<data>.md and records it in usuarios/<login>.diario.jsonl with por="operador: <motivo>".
Running it twice changes nothing ("ja_migrada")."""

import base64
import json
import sys

from decisoes import vm  # same SSM helper

HELPER = "/a0/usr/plugins/memoria_pessoal/helpers/ficha.py"

PROGRAMA = """
import importlib.util, json, sys
p = json.loads(sys.argv[1])
s = importlib.util.spec_from_file_location("ficha_operador", %r)
f = importlib.util.module_from_spec(s); s.loader.exec_module(f)
r = f.migrar(p["login"], por="operador: " + p["motivo"], simular=p["op"] == "ver")
print(json.dumps({k: v for k, v in r.items() if k != "lista"}, ensure_ascii=False, indent=1))
for i, e in enumerate(r.get("lista") or [], 1):
    print(i, e)
""" % HELPER


def main() -> None:
    args = sys.argv[1:]
    opcoes = {}
    for chave in ("--login", "--motivo"):
        if chave in args:
            i = args.index(chave)
            opcoes[chave] = args[i + 1]
            del args[i:i + 2]
    if not args or args[0] not in ("ver", "migrar"):
        raise SystemExit(__doc__)
    if args[0] == "migrar" and not opcoes.get("--motivo"):
        raise SystemExit("diga o motivo com --motivo \"...\" (fica registrado no diário da ficha)")
    p = {"op": args[0], "login": opcoes.get("--login", "matheus"), "motivo": opcoes.get("--motivo", "ver")}
    programa = base64.b64encode(PROGRAMA.encode()).decode()
    dados = base64.b64encode(json.dumps(p, ensure_ascii=False).encode()).decode()
    print(vm(f"echo {programa} | base64 -d > /tmp/ficha_operador.py && "
             "docker cp /tmp/ficha_operador.py agent-zero:/tmp/ficha_operador.py && "
             f"docker exec agent-zero /opt/venv-a0/bin/python /tmp/ficha_operador.py "
             f"\"$(echo {dados} | base64 -d)\""))


if __name__ == "__main__":
    main()
