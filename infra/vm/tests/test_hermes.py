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
checa(cfg["approvals"]["timeout"] >= 3600, "o ok pelo celular tem horas para chegar, como no A0")
checa("agentepessoal" in cfg["plugins"]["enabled"], "o plugin com as nossas ferramentas ligado")
checa((H / "plugins" / "agentepessoal" / "plugin.yaml").exists(), "o plugin está na pasta que o subir.sh copia")
sh = (H / "subir.sh").read_text()
checa("AWS_ENDPOINT_URL_BEDROCK_RUNTIME=http://host.docker.internal:8787/hermes/bedrock" in sh, "modelo só pelo proxy")
checa("ANTHROPIC_BEDROCK_BASE_URL=http://host.docker.internal:8787/hermes/bedrock" in sh,
      "Claude no Bedrock (SDK AnthropicBedrock, que ignora o endpoint do boto3) também pelo proxy")
checa("PONTE OK" in sh, "a instalação só passa com uma resposta de verdade do modelo")
checa("AWS_ACCESS_KEY_ID=proxy" in sh and "AWS_EC2_METADATA_DISABLED=true" in sh, "nenhuma credencial real no Hermes")
checa("-p 127.0.0.1:8642:8642" in sh, "API server só no loopback do host")
checa("-v /opt/hermes/a0usr:/a0/usr" in sh, "dados vivos no mesmo caminho, pela vista com dono do Hermes")
un = (H / "agentepessoal-hermes-dados.service").read_text()
checa("--create-for-user=0" in un and "--force-user=10000" in un and "Before=docker.service" in un,
      "a vista: o Hermes vê como dono, o disco continua root, e sobe antes do docker")
checa("--enable-lock-forwarding" not in un or "--multithreaded" in un,
      "repasse de trava só com --multithreaded (o bindfs recusa subir sem ele: 23/10)")
checa(sh.index("mountpoint -q /opt/hermes/a0usr ||") < sh.index("docker run"), "o container só sobe com a vista montada")
checa(re.search(r'BASE="nousresearch/hermes-agent:v\d+\.\d+\.\d+"', sh), "imagem com versão fixa")
df = (H / "imagem" / "Dockerfile").read_text()
base = re.search(r'BASE="([^"]+)"', sh).group(1)
checa(f"FROM {base}\n" in df, "a nossa imagem parte da mesma versão do script")
pacotes = [t for t in df.split("uv pip install", 1)[1].split("&&", 1)[0].split() if t[0] not in "-/\\"]
checa(len(pacotes) >= 5 and all("==" in t for t in pacotes), f"pacotes com versão fixa: {pacotes}")
checa(re.search(r"FROM ghcr.io/astral-sh/uv:\d+\.\d+\.\d+ AS uv", df), "uv com versão fixa")
checa(subprocess.run(["bash", "-n", str(H / "subir.sh")]).returncode == 0, "sintaxe do script")
for d in (".aws", "whatsapp", "segredos", "navegador", "mcp", "celular", "delegados"):
    checa(re.search(rf"for d in (?:[^;]*\s)?{re.escape(d)}(?=[\s;])", sh), f"no ensaio {d} aparece vazio no Hermes")
for f in ("/.env ", "/secrets.env ", "/settings.json ", "/usuarios.json*;"):
    checa(re.search(rf"for caminho in [^;]*{re.escape(f.rstrip(';'))}", sh), f"no ensaio {f.strip('/ ;')} aparece vazio no Hermes")
ue = (H / "agentepessoal-hermes.service").read_text()
checa("--restart no" in sh and "agentepessoal-firewall.service" in ue and "ExecStartPre=" in ue,
      "na subida da VM o Hermes só liga depois do firewall (não pelo reinício do Docker)")
checa('"${ESCONDIDOS[@]}"' in sh and "--network hermes" in sh, "o container usa a rede própria e os escondidos")
checa(sh.index("HERMES_SEM_FIREWALL") < sh.index("docker run"), "não sobe sem a rede fechada")
fw = (RAIZ / "infra" / "vm" / "firewall.sh").read_text()
checa("docker network inspect hermes" in fw and '-s "$HERMES" -j DROP' in fw and "--dport 8787" in fw
      and '-s "$HERMES" -d "$destino" -j DROP' in fw, "firewall: rede hermes só com o proxy e a internet")
checa(sh.index("HERMES_SEM_ENSAIO") < sh.index("docker run"), "não sobe sem a trava do ensaio nos plugins no ar")
checa("-o allow_other,ro " in un, "até a virada o Hermes vê os dados do A0 só para leitura")
checa("AGENTEPESSOAL_RELOGIO=1" not in sh, "até a virada o relógio (post na hora, nota do dia…) é do A0, não do Hermes")
checa("-e AGENTEPESSOAL_ENSAIO=1" in sh, "até a virada o Hermes está em ensaio: nada vai ao celular nem à Meta")
checa("/a0/usr/skills" not in str((cfg.get("skills") or {}).get("external_dirs") or ""),
      "o Hermes não lê as skills vivas do A0 (mandam usar ferramentas de lá; e external_dirs é só leitura para o curador)")
nav = (H / "navegador.sh").read_text()
checa(subprocess.run(["bash", "-n", str(H / "navegador.sh")]).returncode == 0, "sintaxe do navegador.sh")
checa(cfg["browser"]["backend"] == "off", "navegador pelas ferramentas próprias (cada clique passa pelas aprovações)")
checa("--password-store=basic" in nav and "--use-mock-keychain" in nav and "chromium-1228" in nav,
      "o navegador do Hermes abre os cookies do perfil do A0 (mesmo binário e mesmas opções)")
checa("--network hermes" in nav and not re.search(r"\s(-p|--publish)\s+\S*\d", nav), "o CDP só na rede hermes, nunca publicado no host")
checa("PERFIL_A0=/opt/a0/usr/navegador/sessions/shared" in nav and "rsync -a" in nav and "perfil.novo" in nav,
      "até a virada o Hermes usa uma CÓPIA do perfil (o A0 segue com o dele)")
checa("rm -f /perfil/Singleton*;" in nav, "a trava do perfil sai a cada subida (outro container = 'perfil em uso')")
checa('-e BROWSER_CDP_URL="$CDP"' in sh and sh.index("HERMES_SEM_NAVEGADOR") < sh.index("docker run"),
      "o Hermes liga no navegador dele e não sobe sem ele")
checa('NAV="${HERMES%.*.*}.0.250"' in fw and "--dport 9223" in fw and "--dport 9222" not in fw, "firewall: o Hermes só fala com o CDP do navegador dele")
checa("docker start hermes-navegador hermes-mcp hermes" in ue, "na subida da VM o navegador e os conectores sobem juntos")
mcp = (H / "mcp.sh").read_text()
checa(subprocess.run(["bash", "-n", str(H / "mcp.sh")]).returncode == 0, "sintaxe do mcp.sh")
checa("gmail:readonly calendar:readonly drive:readonly docs:readonly sheets:readonly" in mcp,
      "no ensaio o Google do Hermes só lê (nada de escrever no Drive do Matheus)")
checa(set(cfg["mcp_servers"]) == {"google", "github"} and all("hermes-mcp" in v["url"] for v in cfg["mcp_servers"].values())
      and "headers" not in str(cfg["mcp_servers"]), "conectores pelo container ao lado, sem token no Hermes")
checa('"$BASE/google:/google"' in mcp and "/opt/hermes/a0usr" not in mcp and "--network hermes" in mcp
      and not re.search(r"\s(-p|--publish)\s+\S*\d", mcp), "tokens só no container dos conectores, nada publicado no host")
checa('MCP="${HERMES%.*.*}.0.251"' in fw and "--dport 8765" in fw and "--dport 8766" in fw, "firewall: só as portas dos conectores")
checa(sh.index("HERMES_SEM_MCP") < sh.index("docker run"), "o Hermes não sobe sem os conectores")
df_mcp = (H / "mcp" / "Dockerfile").read_text()
checa("FROM python:3.12.8-slim" in df_mcp and "workspace-mcp==2.0.1" in df_mcp and "-c /tmp/versoes.txt" in df_mcp,
      "conector do Google com a versão e as dependências do A0")
alma = (H / "SOUL.md").read_text()
for termo in ("Captcha", "cofre", "Texto de terceiros", "3 caminhos", "segundo_cerebro/pasta", '"n" = NÃO'):
    checa(termo in alma, f"a persona traz {termo!r}")
tudo = "".join(f.read_text() for f in H.iterdir() if f.is_file())
checa(not re.search(r"AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{30,}", tudo), "nenhum segredo no git")
if falhas:
    raise SystemExit("test_hermes: " + "; ".join(falhas))
print("test_hermes: ok")
