"""Tests of the guests' isolated boxes (infra/vm/caixa_convidados.py) with no Docker: every flag of the box, the
logins, which files may go in and out, the firewall rules. Run from the repository root:
python3 infra/vm/tests/test_caixa.py"""

import importlib.util
import os
import shlex
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
falhas = []


def carregar(nome, caminho):
    spec = importlib.util.spec_from_file_location(nome, caminho)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


c = carregar("caixa_teste", RAIZ / "infra" / "vm" / "caixa_convidados.py")
conv = carregar("convidados_caixa_teste", RAIZ / "infra" / "vm" / "plugins" / "login_usuarios" / "helpers" / "convidados.py")

if set(c.CONVIDADOS) != set(conv.CONVIDADOS):
    falhas.append(f"convidados da caixa {c.CONVIDADOS} diferentes do plugin {list(conv.CONVIDADOS)}")
if "terminal_isolado" not in conv.FERRAMENTAS or "code_execution_tool" in conv.FERRAMENTAS or "text_editor" in conv.FERRAMENTAS:
    falhas.append("convidado tem a caixa, nunca o terminal ou o editor do agente")

# the box: nothing of the agent inside, no privileges, limits, its own network
a = c.argumentos_run("will")
linha = " ".join(a)
for preciso in ("--cap-drop ALL", "--security-opt no-new-privileges", "--user 1000:1000", "--network caixas",
                "--memory 2g", "--memory-swap 2g", f"--label caixa-versao={c.VERSAO}", "--pids-limit 256", "--dns 1.1.1.1", "--cpus 1", "--restart no", f"/opt/caixas/will:{c.HOME}"):
    if preciso not in linha:
        falhas.append(f"caixa sem {preciso!r}: {linha}")
volumes = [a[i + 1] for i, x in enumerate(a) if x in ("-v", "--volume", "--mount")]
if volumes != [f"/opt/caixas/will:{c.HOME}"]:
    falhas.append(f"a caixa só monta a pasta dela: {volumes}")
for proibido in ("--privileged", "docker.sock", "/opt/a0", "/a0/", "--network host", "--pid ", "--ipc", "/var/lib/agentepessoal",
                 "SYS_ADMIN", "--cap-add", "--device"):
    if proibido in linha + " ":
        falhas.append(f"caixa com {proibido!r}")

for ruim in ("matheus", "fernanda", "../will", "will/..", "", "WILL;rm"):
    try:
        c.conferir_login(ruim)
        falhas.append(f"login aceito: {ruim!r}")
    except c.Recusa:
        pass
if c.conferir_login(" Will ") != "will":
    falhas.append("login do convidado normalizado")

# files in: only the guest's own folders; never another person's, a link or a path that climbs out
tmp = Path(tempfile.mkdtemp())
c.USR_HOST = tmp
(tmp / "whatsapp" / "will").mkdir(parents=True)
(tmp / "whatsapp" / "matheus").mkdir(parents=True)
(tmp / "projects" / "convidado-will").mkdir(parents=True)
(tmp / "projects" / "convidado-ilia").mkdir(parents=True)
(tmp / "whatsapp" / "will" / "foto.jpg").write_bytes(b"x")
(tmp / "projects" / "convidado-will" / "rel.pdf").write_bytes(b"x")
(tmp / "whatsapp" / "matheus" / "segredo.txt").write_text("nao")
(tmp / "projects" / "convidado-ilia" / "dele.txt").write_text("nao")
(tmp / "segredos.json").write_text("nao")
os.symlink(tmp / "segredos.json", tmp / "whatsapp" / "will" / "atalho.txt")
os.symlink(tmp / "whatsapp" / "matheus", tmp / "whatsapp" / "will" / "pasta")
for bom in ("/a0/usr/whatsapp/will/foto.jpg", "/a0/usr/projects/convidado-will/rel.pdf"):
    try:
        c.origem_permitida("will", bom)
    except c.Recusa as exc:
        falhas.append(f"arquivo dele recusado: {bom} ({exc})")
for ruim in ("/a0/usr/whatsapp/matheus/segredo.txt", "/a0/usr/projects/convidado-ilia/dele.txt", "/a0/usr/segredos.json",
             "/a0/usr/whatsapp/will/../matheus/segredo.txt", "/a0/usr/whatsapp/will/atalho.txt",
             "/a0/usr/whatsapp/will/pasta/segredo.txt", "/etc/passwd", "whatsapp/will/foto.jpg",
             "/a0/usr/whatsapp/will-x/foto.jpg"):
    try:
        c.origem_permitida("will", ruim)
        falhas.append(f"arquivo de fora aceito: {ruim}")
    except c.Recusa:
        pass

# files out: only from inside the box's home, checked before anything runs
chamou = []
c.garantir_caixa = lambda login: chamou.append(login)
for ruim in ("/etc/passwd", "/home/node/../../etc/passwd", "/home/nodex/a", "/proc/self/environ"):
    try:
        c.trazer("will", ruim)
        falhas.append(f"trouxe de fora da casa: {ruim}")
    except c.Recusa:
        pass
if chamou:
    falhas.append(f"caminho de fora nem liga a caixa: {chamou}")

# network: internet only
regras = [" ".join(r) for r in c.regras_isolamento("172.30.0.0/16")]
for preciso in ("INPUT -s 172.30.0.0/16 -j DROP", "DOCKER-USER -s 172.30.0.0/16 -d 169.254.0.0/16 -j DROP",
                "DOCKER-USER -s 172.30.0.0/16 -d 172.16.0.0/12 -j DROP", "DOCKER-USER -s 172.30.0.0/16 -d 10.0.0.0/8 -j DROP"):
    if preciso not in regras:
        falhas.append(f"regra de isolamento faltando: {preciso}")
fw = (RAIZ / "infra" / "vm" / "firewall.sh").read_text()
for regra in c.regras_isolamento("$CAIXAS"):
    cadeia, *resto = regra
    if cadeia == "INPUT" and 'regra=(INPUT -s "$CAIXAS" -j DROP)' not in fw:
        falhas.append("firewall.sh não fecha o host para as caixas")
if "exit 0" in fw.split("CAIXAS=")[0]:
    falhas.append("firewall.sh sai antes de isolar as caixas quando a rede do celular não existe")
if "8790" not in fw:
    falhas.append("o celular virtual também não alcança o serviço das caixas")
fonte = (RAIZ / "infra" / "vm" / "caixa_convidados.py").read_text()
if '("172.17.0.1", PORTA)' not in fonte or '("0.0.0.0"' in fonte or '("", PORTA)' in fonte:
    falhas.append("o serviço escuta só na ponte do Docker (o agente chega por host.docker.internal)")
if "not isolada()" not in fonte:
    falhas.append("a caixa não roda sem conferir as regras de rede")

# secret: created once, readable by root only
c.SEGREDO = tmp / "caixa" / "segredo.txt"
s1, s2 = c.segredo(), c.segredo()
if s1 != s2 or len(s1) < 30 or oct(c.SEGREDO.stat().st_mode)[-3:] != "600":
    falhas.append("segredo do serviço: fixo, longo e só do root")

imp = (RAIZ / "infra" / "operador" / "implantar.py").read_text()
if '"caixa_convidados.py"' not in imp or not (RAIZ / "infra" / "vm" / "unidades" / "agentepessoal-caixas.service").exists():
    falhas.append("serviço implantável por implantar.py --host caixa_convidados.py --unidade agentepessoal-caixas.service")

print("\n".join("FALHOU: " + f for f in falhas) or "caixa: ok")
sys.exit(1 if falhas else 0)
