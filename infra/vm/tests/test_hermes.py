"""Tests of the Hermes install (infra/vm/hermes, 23/10 migration): the config loads and points the model at our proxy
without any key in git; the persona carries the rules that hold always; the install script keeps the API server on
the host's loopback and the live data at the same path. Run from the repository root: python3 infra/vm/tests/test_hermes.py"""
import re
import subprocess
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[3]
H = RAIZ / "infra" / "vm" / "hermes"
falhas = []


def checa(cond, msg):
    if not cond:
        falhas.append(msg)


cfg = yaml.safe_load((H / "config.yaml").read_text())
checa(cfg["model"]["provider"] == "bedrock" and "haiku" in cfg["model"]["default"], "Haiku no dia a dia (decisão 23/10)")
checa(cfg["timezone"] == "America/Bahia", "fuso dele")
checa("/a0/usr/skills" in cfg["skills"]["external_dirs"], "as skills de hoje entram no lugar onde estão")
sh = (H / "subir.sh").read_text()
checa("AWS_ENDPOINT_URL_BEDROCK_RUNTIME=http://host.docker.internal:8787/bedrock" in sh, "modelo só pelo proxy")
checa("ANTHROPIC_BEDROCK_BASE_URL=http://host.docker.internal:8787/bedrock" in sh,
      "Claude no Bedrock (SDK AnthropicBedrock, que ignora o endpoint do boto3) também pelo proxy")
checa("PONTE OK" in sh, "a instalação só passa com uma resposta de verdade do modelo")
checa("AWS_ACCESS_KEY_ID=proxy" in sh and "AWS_EC2_METADATA_DISABLED=true" in sh, "nenhuma credencial real no Hermes")
checa("-p 127.0.0.1:8642:8642" in sh, "API server só no loopback do host")
checa("-v /opt/a0/usr:/a0/usr" in sh, "dados vivos no mesmo caminho")
checa(re.search(r'IMAGEM="nousresearch/hermes-agent:v\d+\.\d+\.\d+"', sh), "imagem com versão fixa")
checa(subprocess.run(["bash", "-n", str(H / "subir.sh")]).returncode == 0, "sintaxe do script")
alma = (H / "SOUL.md").read_text()
for termo in ("Captcha", "cofre", "Texto de terceiros", "3 caminhos", "segundo_cerebro/pasta", '"n" = NÃO'):
    checa(termo in alma, f"a persona traz {termo!r}")
tudo = "".join(f.read_text() for f in H.iterdir() if f.is_file())
checa(not re.search(r"AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{30,}", tudo), "nenhum segredo no git")
if falhas:
    raise SystemExit("test_hermes: " + "; ".join(falhas))
print("test_hermes: ok")
