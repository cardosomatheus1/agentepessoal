"""The Segundo Cérebro's Pasta on the VM (plugin cerebro), only through the plugin's own functions (CLAUDE.md: live
data is never edited by hand). Usage, from the repository root:

    python3 infra/operador/cerebro.py migrar --motivo "<por quê>" [--simular]   (one-time move of the old stores)
    python3 infra/operador/cerebro.py estado                                     (counts, pending context, last note)
    python3 infra/operador/cerebro.py auditoria                                  (writes Documentos/auditoria-<data>.md)
    python3 infra/operador/cerebro.py nota                                       (writes today's nota do dia now)
    python3 infra/operador/cerebro.py copia-github                               (creates the private repo once, pushes)
    python3 infra/operador/cerebro.py semear-raiz --motivo "<por quê>"           (fills the Cérebro da Raiz once)

semear-raiz: Raiz/ (helpers/raiz.py) from the prospecção playbook and the competitor list on the VM, plus the brand
identity notes that live only in this repository (infra/reels/README.md and the Raiz molde's marca.json), sent along;
what has no source stays PENDENTE for the interview. Refuses a second time."""

import base64
import json
import re
import sys
import time
from pathlib import Path

import boto3

VM = "i-0498b4f39560b01a9"
ssm = boto3.client("ssm", region_name="us-east-1")

PROGRAMA = r"""
import importlib.util, json, sys
p = json.loads(sys.argv[1])
s = importlib.util.spec_from_file_location("cerebro_modulos", "/a0/usr/plugins/cerebro/helpers/modulos.py")
m = importlib.util.module_from_spec(s); s.loader.exec_module(m); sys.modules["cerebro_modulos"] = m
pasta = m.m("pasta")
if p["op"] == "migrar":
    print("MIGRACAO", json.dumps(m.m("migracao").migrar("operador: " + p["motivo"], simular=p["simular"]), ensure_ascii=False))
    if not p["simular"]:
        r = m.m("auditoria").gravar(pasta)
        print("AUDITORIA", r["nota"], r["arquivo"])
elif p["op"] == "auditoria":
    r = m.m("auditoria").gravar(pasta)
    print("AUDITORIA", r["nota"], r["arquivo"])
    for a in r["achados"][:30]:
        print(" -", a["checagem"], a["arquivo"], a["motivo"])
elif p["op"] == "copia-github":
    import subprocess, urllib.request
    sys.path.insert(0, "/a0/usr/plugins/cofre/helpers"); import cofre
    tok = cofre.carregar("matheus").get("GITHUB_TOKEN") or ""
    def api(metodo, url, corpo=None):
        req = urllib.request.Request("https://api.github.com" + url, method=metodo, data=json.dumps(corpo).encode() if corpo else None,
                                     headers={"Authorization": "Bearer " + tok, "Accept": "application/vnd.github+json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")
    _st, eu = api("GET", "/user")
    dono = eu.get("login")
    st, repo = api("GET", f"/repos/{dono}/segundo-cerebro")
    if st == 404:
        st, repo = api("POST", "/user/repos", {"name": "segundo-cerebro", "private": True, "auto_init": False,
                                               "description": "Segundo Cérebro do Matheus (cópia diária da Pasta do agente)"})
        print("REPO CRIADO", st, repo.get("full_name"), "privado:", repo.get("private"))
    else:
        print("REPO JA EXISTE", repo.get("full_name"), "privado:", repo.get("private"))
    if not repo.get("private"):
        print("PARADO: o repositório não é privado; nada foi enviado")
    else:
        pasta.versionar("cópia inicial")
        if subprocess.run(["git", "-C", str(pasta.RAIZ), "remote", "get-url", "origin"], capture_output=True).returncode:
            subprocess.run(["git", "-C", str(pasta.RAIZ), "remote", "add", "origin", f"https://github.com/{dono}/segundo-cerebro.git"])
        print("ENVIO", pasta.enviar_copia(tok) or "ok")
elif p["op"] == "semear-raiz":
    r = m.m("raiz").semear("operador: " + p["motivo"], marca_visual=p.get("marca_visual", ""))
    print("RAIZ", json.dumps(r, ensure_ascii=False))
    a = m.m("auditoria").gravar(pasta)
    print("AUDITORIA", a["nota"], a["arquivo"], "mapa:", [x["motivo"] for x in a["achados"] if x["checagem"] == "mapa"])
elif p["op"] == "nota":
    n = m.m("dia").escrever(pasta)
    print("NOTA", n["data"]); print(n["resumo"])
else:
    print("ATIVA", pasta.ativa("matheus"))
    if pasta.ativa("matheus"):
        for c in ("decisoes", "pendencias", "assuntos"):
            itens = pasta.ler(c)
            print(c, len(itens), "abertos/ativos:", sum(1 for x in itens if x.get("estado") in ("ativa", "aberto", "andamento", "adiado")))
        print("contexto pendente:", pasta.contexto_pendente())
        notas = sorted((pasta.RAIZ / "Notas-do-dia").glob("????-??-??.md"))
        print("última nota:", notas[-1].name if notas else "nenhuma")
"""


REPO = Path(__file__).resolve().parents[2]


def marca_visual() -> str:
    """The Raiz brand identity notes kept in this repository (not on the VM): the fixed part of the kit rule in
    infra/reels/README.md and the Raiz molde's marca.json. '' when neither can be read (marca.md keeps PENDENTE)."""
    partes = []
    leia = REPO / "infra" / "reels" / "README.md"
    if leia.exists():
        texto = leia.read_text(encoding="utf-8")
        for comeco in ("> **Regra do Matheus (14/10/2026)", "> **Padrão x liberdade criativa"):
            i = texto.find(comeco)
            if i >= 0:
                bloco = texto[i:].split("\n>\n", 1)[0]
                partes.append(re.sub(r"^> ?", "", bloco, flags=re.M).strip())
    marca = REPO / "infra" / "reels" / "moldes" / "marcas" / "raiz" / "marca.json"
    if marca.exists():
        try:
            j = json.loads(marca.read_text(encoding="utf-8"))
            # the molde's colors and font are the old video ones (the kit replaced them): only who speaks and the call
            partes.append(f"Perfil {j.get('perfil', '')}; chamada dos posts \"{j.get('chamada', '')}\"; "
                          f"voz dos vídeos: {j.get('voz', {}).get('id', '')}")
        except ValueError:
            pass
    return ("_Do repositório: infra/reels/README.md e infra/reels/moldes/marcas/raiz/marca.json._\n\n" + "\n\n".join(partes)
            if partes else "")


def vm(comando: str, timeout: int = 600) -> str:
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
    motivo = ""
    if "--motivo" in args:
        i = args.index("--motivo")
        motivo = args[i + 1]
        del args[i:i + 2]
    simular = "--simular" in args
    args = [a for a in args if a != "--simular"]
    if not args or args[0] not in ("migrar", "estado", "auditoria", "nota", "copia-github", "semear-raiz"):
        raise SystemExit(__doc__)
    if args[0] in ("migrar", "semear-raiz") and not motivo:
        raise SystemExit("diga o motivo com --motivo \"...\" (fica registrado em quem migrou)")
    p = {"op": args[0], "motivo": motivo, "simular": simular}
    if args[0] == "semear-raiz":
        p["marca_visual"] = marca_visual()
    programa = base64.b64encode(PROGRAMA.encode()).decode()
    dados = base64.b64encode(json.dumps(p, ensure_ascii=False).encode()).decode()
    print(vm(f"echo {programa} | base64 -d > /tmp/cerebro_operador.py && "
             "docker cp /tmp/cerebro_operador.py agent-zero:/tmp/cerebro_operador.py && "
             f"docker exec agent-zero /opt/venv-a0/bin/python /tmp/cerebro_operador.py "
             f"\"$(echo {dados} | base64 -d)\""))


if __name__ == "__main__":
    main()
