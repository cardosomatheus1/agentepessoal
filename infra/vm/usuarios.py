#!/usr/bin/env python3
"""Add or change agent logins without storing passwords: prints/merges PBKDF2 hashes.

  python3 usuarios.py matheus "Matheus" <senha> [arquivo]   # default /opt/a0/usr/usuarios.json
  python3 usuarios.py --remover fernanda [arquivo]
  python3 usuarios.py --operador matheus <salt hex> <hash hex> [arquivo]   # second password, for the operator scripts
  python3 usuarios.py --sem-operador matheus [arquivo]
"""
import hashlib
import json
import os
import sys

ITER = 310_000


def main(argv: list[str]) -> None:
    if argv and argv[0] == "--remover":
        login, arquivo = argv[1].lower(), (argv[2] if len(argv) > 2 else "/opt/a0/usr/usuarios.json")
        dados = json.load(open(arquivo))
        dados["usuarios"].pop(login, None)
    elif argv and argv[0] in ("--operador", "--sem-operador"):  # only the hash comes here; the password stays in SSM
        login = argv[1].lower()
        resto = argv[4:] if argv[0] == "--operador" else argv[2:]
        arquivo = resto[0] if resto else "/opt/a0/usr/usuarios.json"
        dados = json.load(open(arquivo))
        if argv[0] == "--operador":
            salt, h = bytes.fromhex(argv[2]), bytes.fromhex(argv[3])
            if len(salt) != 16 or len(h) != 32:
                raise SystemExit("salt de 16 bytes e hash de 32 bytes, em hex")
            dados["usuarios"][login]["operador"] = {"salt": argv[2], "iter": ITER, "hash": argv[3]}
        else:
            dados["usuarios"][login].pop("operador", None)
    else:
        login, nome, senha = argv[0].strip().lower(), argv[1], argv[2]
        arquivo = argv[3] if len(argv) > 3 else "/opt/a0/usr/usuarios.json"
        try:
            dados = json.load(open(arquivo))
        except FileNotFoundError:
            dados = {"usuarios": {}}
        salt = os.urandom(16)
        dados["usuarios"][login] = {
            "nome": nome, "salt": salt.hex(), "iter": ITER,
            "hash": hashlib.pbkdf2_hmac("sha256", senha.encode(), salt, ITER).hex(),
        }
    tmp = arquivo + ".tmp"
    with open(tmp, "w") as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)
    os.chmod(tmp, 0o600)
    os.replace(tmp, arquivo)
    print("usuários:", ", ".join(dados["usuarios"]))


if __name__ == "__main__":
    main(sys.argv[1:])
