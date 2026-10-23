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
listas = re.findall(r'PASTAS_ESCONDIDAS="([^"]*)"', sh)
checa(len(listas) == 2 and "for d in $PASTAS_ESCONDIDAS" in sh, "escondidos: uma lista na virada, outra no ensaio")
virada_esc, ensaio_esc = (listas + ["", ""])[:2]
for d in (".aws", "whatsapp", "segredos", "navegador", "mcp", "celular", "delegados", ".time_travel", ".tmp", "workdir", "caixa", "chats",
          "chats_arquivo"):
    checa(d in ensaio_esc.split(), f"no ensaio {d} aparece vazio no Hermes")
checa({"navegador", "navegador_visual", "mcp", ".time_travel"} <= set(virada_esc.split())
      and not {"segredos", "whatsapp", "caixa", "delegados", "chats"} & set(virada_esc.split()),
      "na virada o Hermes vê o que o A0 via (cofre, ponte, caixas, conversas), menos perfis e tokens dos conectores")
for f in ("/.env ", "/secrets.env ", "/settings.json ", "/usuarios.json*;"):
    checa(re.search(rf"for caminho in [^;]*{re.escape(f.rstrip(';'))}", sh), f"no ensaio {f.strip('/ ;')} aparece vazio no Hermes")
ue = (H / "agentepessoal-hermes.service").read_text()
checa("--restart no" in sh and "agentepessoal-firewall.service" in ue and "ExecStartPre=" in ue,
      "na subida da VM o Hermes só liga depois do firewall (não pelo reinício do Docker)")
checa('"${ESCONDIDOS[@]}"' in sh and "--network hermes" in sh, "o container usa a rede própria e os escondidos")
checa(sh.index("HERMES_SEM_FIREWALL") < sh.index("docker run"), "não sobe sem a rede fechada")
fw = (RAIZ / "infra" / "vm" / "firewall.sh").read_text()
checa("grep -E '^hermes(-[a-z0-9_-]+)?$'" in fw and '-s "$SUB" -j DROP' in fw and 'aceitar_input "$SUB" 8787 1' in fw
      and '-s "$SUB" -d "$destino" -j DROP' in fw, "firewall: redes do Hermes só com o proxy e a internet")
checa('aceitar_input "$SUB" "$porta" "$VIRADA"' in fw and 'portas="8788 8789 8790 8791"; else portas="8789 8790"' in fw
      and 'aceitar_input "$SUB" "$porta" 0' in fw,
      "firewall: credenciais, ponte e caixas só na virada (e saem de novo na volta); convidados só ponte e caixa")
checa('regra_user "$VIRADA" -s "$AND/32" -d "$SUB" -j DROP' in fw and '--dport 5555' in fw
      and 'a=(INPUT -s "$AND/32" -j DROP)' in fw, "firewall: o celular só responde ao adb (não abre nada no Hermes nem no host)")
checa(sh.index("HERMES_SEM_ENSAIO") < sh.index("docker run"), "não sobe sem a trava do ensaio nos plugins no ar")
checa("-o allow_other,${HERMES_DADOS_MODO} " in un and "Environment=HERMES_DADOS_MODO=ro" in un
      and 'if [ "$VIRADA" = 1 ]; then MODO_DADOS=rw; else MODO_DADOS=ro; fi' in sh,
      "até a virada o Hermes vê os dados do A0 só para leitura (rw só com a chave no Hermes)")
modo_env = re.search(r'if \[ "\$VIRADA" = 1 \]; then\n(?:  SUBH=[^\n]*\n)?  MODO_ENV=\((.*?)\)[^\n]*\nelse\n  MODO_ENV=\((.*?)\)\nfi', sh)
checa(modo_env and modo_env.group(1).startswith("-e AGENTEPESSOAL_RELOGIO=1 --add-host") and modo_env.group(2) == "-e AGENTEPESSOAL_ENSAIO=1"
      and '"${MODO_ENV[@]}"' in sh and sh.count("AGENTEPESSOAL_RELOGIO=1") == 1,
      "relógio só na virada; até lá o ensaio (nada ao celular nem à Meta)")
checa(sh.index("HERMES_A0_RODANDO") < sh.index("docker run") and "VIRADA=1" in sh,
      "na virada o Hermes não sobe com o A0 rodando (mesmo perfil do navegador e mesmas rotinas)")
checa("/a0/usr/skills" not in str((cfg.get("skills") or {}).get("external_dirs") or ""),
      "o Hermes não lê as skills vivas do A0 (mandam usar ferramentas de lá; e external_dirs é só leitura para o curador)")
nav = (H / "navegador.sh").read_text()
checa(subprocess.run(["bash", "-n", str(H / "navegador.sh")]).returncode == 0, "sintaxe do navegador.sh")
checa(cfg["browser"]["backend"] == "off", "navegador pelas ferramentas próprias (cada clique passa pelas aprovações)")
checa("--password-store=basic" in nav and "--use-mock-keychain" in nav and "chromium-1228" in nav,
      "o navegador do Hermes abre os cookies do perfil do A0 (mesmo binário e mesmas opções)")
checa('--network "$REDE"' in nav and "REDE=hermes" in nav and not re.search(r"\s(-p|--publish)\s+\"?[\d.:]*\d+:\d", nav),
      "o CDP só na rede do Hermes, nunca publicado no host")
checa('PERFIL_A0="/opt/a0/usr/navegador/sessions/$PERFIL"' in nav and "PERFIL=shared" in nav and "rsync -a" in nav
      and '"$COPIA.novo/"' in nav and 'NAV_OPC=(--proprio); else NAV_OPC=()' in sh,
      "até a virada o Hermes usa uma CÓPIA do perfil (o A0 segue com o dele); o de verdade só na virada")
checa('"--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/$V.0.0.0' in nav
      and "HeadlessChrome" not in nav.split("docker run", 1)[1], "o navegador se apresenta como Chrome (o WhatsApp Web recusa o sem tela)")
checa("rm -f /perfil/Singleton*;" in nav, "a trava do perfil sai a cada subida (outro container = 'perfil em uso')")
checa('-e BROWSER_CDP_URL="$CDP"' in sh and sh.index("HERMES_SEM_NAVEGADOR") < sh.index("docker run"),
      "o Hermes liga no navegador dele e não sobe sem ele")
checa('NAV="${SUB%.*.*}.0.250"' in fw and "--dport 9223" in fw and "--dport 9222" not in fw, "firewall: o Hermes só fala com o CDP do navegador dele")
ini = (H / "iniciar.sh").read_text()
checa("ExecStart=/opt/hermes/iniciar.sh" in ue and "nomes=(hermes-navegador hermes-mcp hermes-celular hermes portal)" in ini
      and subprocess.run(["bash", "-n", str(H / "iniciar.sh")]).returncode == 0,
      "na subida da VM o navegador e os conectores sobem juntos (e os Hermes dos convidados)")
mcp = (H / "mcp.sh").read_text()
checa(subprocess.run(["bash", "-n", str(H / "mcp.sh")]).returncode == 0, "sintaxe do mcp.sh")
checa("gmail:readonly calendar:readonly drive:readonly docs:readonly sheets:readonly" in mcp,
      "no ensaio o Google do Hermes só lê (nada de escrever no Drive do Matheus)")
checa(set(cfg["mcp_servers"]) == {"google", "github"} and all("hermes-mcp" in v["url"] for v in cfg["mcp_servers"].values())
      and "headers" not in str(cfg["mcp_servers"]), "conectores pelo container ao lado, sem token no Hermes")
checa('"$BASE/google:/google"' in mcp and "/opt/hermes/a0usr" not in mcp and "--network hermes" in mcp
      and not re.search(r"\s(-p|--publish)\s+\S*\d", mcp), "tokens só no container dos conectores, nada publicado no host")
checa('MCP="${SUB%.*.*}.0.251"' in fw and "--dport 8765" in fw and "--dport 8766" in fw, "firewall: só as portas dos conectores")
checa(re.search(r'if \[ "\$VIRADA" = 1 \]; then  # as permissões do A0[^\n]*\n  export HERMES_GOOGLE_PERMISSOES="gmail:readonly '
                r'calendar:readonly drive:full docs:full sheets:full"', sh), "Google com as permissões do A0 só na virada")
checa(sh.index("HERMES_SEM_MCP") < sh.index("docker run"), "o Hermes não sobe sem os conectores")
df_mcp = (H / "mcp" / "Dockerfile").read_text()
checa("FROM python:3.12.8-slim" in df_mcp and "workspace-mcp==2.0.1" in df_mcp and "-c /tmp/versoes.txt" in df_mcp,
      "conector do Google com a versão e as dependências do A0")
# fase 3: as 27 skills do A0 adaptadas às ferramentas do Hermes, semeadas uma vez (depois são do curador dele)
skills = sorted(d for d in (H / "skills").iterdir() if d.is_dir())
checa(len(skills) == 27, f"as 27 skills do A0 adaptadas ({len(skills)})")
ANTIGAS = re.compile(r"`browser`|vision_load|code_execution|search_engine|ferramentas_extras|call_subordinate|notify_user|"
                     r"document_query|`response`|`scheduler`|salvar_rotina|me_mostre|tarefa_limite|criar_gatilho|"
                     r"browser_id|`content`|upload_file|`pesquisar`|`wait`")
for d in skills:
    texto = (d / "SKILL.md").read_text()
    cab = yaml.safe_load(texto.split("---", 2)[1])
    checa(cab.get("name") == d.name and cab.get("description") and cab.get("adaptada_hermes"), f"skill {d.name}: cabeçalho")
    checa(not ANTIGAS.search(texto), f"skill {d.name} ainda cita ferramenta do A0: {ANTIGAS.findall(texto)[:3]}")
checa('[ -e "$SK/$n" ] || { cp -r' in sh and "chown -R 10000:10000" in sh, "skill semeada só se ainda não existe (o curador cuida)")
# fase 7: o dia de sombra numa cópia dos dados, no ensaio, com o relógio; para sozinho
so = (H / "sombra.sh").read_text()
checa(subprocess.run(["bash", "-n", str(H / "sombra.sh")]).returncode == 0, "sintaxe do sombra.sh")
checa("-e AGENTEPESSOAL_ENSAIO=1 -e AGENTEPESSOAL_RELOGIO=1" in so and '-v "$S/a0usr":/a0/usr' in so
      and "/opt/hermes/a0usr" not in so and "rsync -a" in so, "sombra: cópia dos dados, ensaio e relógio")
for x in ("/segredos", "/whatsapp/.chave", "/mcp", "/.aws", "/settings.json", "'/usuarios.json*'", "/.env", "/navegador",
          "/.time_travel", "/.tmp", "/workdir", "/caixa", "/chats", "/chats_arquivo"):
    checa(f"--exclude {x}" in so, f"sombra: {x} fica fora da cópia")
checa("-p 127.0.0.1:8643:8642" in so and "--network hermes" in so and "systemd-run" in so and "--on-active" in so,
      "sombra: só no loopback, rede fechada, para sozinha")
checa("jobs.resume_job" in so and "ligada_no_a0" in so, "sombra: liga só as rotinas que estão ligadas no A0")
po = (RAIZ / "infra" / "vm" / "portal" / "subir.sh").read_text()
checa("MODO=(-e PORTAL_SO_LEITURA=1)" in po and 'MONTAGEM="/opt/a0/usr:/a0/usr:ro"' in po and "PORTAL_PORTA=8650" in po
      and "HERMES_SEM_PORTAL" in sh and 'PORTAL_VIRADA="$VIRADA"' in sh, "o portal sobe junto, só leitura até a virada")
# virada (fase 8): um comando para virar, um para voltar; convidados com Hermes próprio
vi = (H / "virada.sh").read_text()
checa(subprocess.run(["bash", "-n", str(H / "virada.sh")]).returncode == 0, "sintaxe do virada.sh")
v, vo = vi.split("\nvirar)", 1)[1].split("\n  ;;", 1)[0], vi.split("\nvoltar)", 1)[1].split("\n  ;;", 1)[0]
checa(v.index("HERMES_SO_IMAGEM=1") < v.index("docker stop") < v.index('HERMES_VIRADA=1 bash "$FONTE/subir.sh"')
      < v.index("chave hermes") < v.index("rotinas_hermes ligar") and 'bash "$0" voltar' in v
      and "docker update --restart no agent-zero" in v and "docker rm" not in vi,
      "virar: imagem antes, A0 parado (não removido), Hermes de pé no modo virada, só então a chave e as rotinas; "
      "se falhar, volta sozinho")
checa("grep -q \"/opt/a0/usr/navegador/sessions\"" in vo and vo.index("navegador/sessions") < vo.index("docker start agent-zero"),
      "voltar: nenhum navegador do Hermes fica num perfil de verdade quando o A0 volta")
checa(vo.index("rotinas_hermes pausar") < vo.index("chave a0") < vo.index("docker start agent-zero")
      and "docker update --restart unless-stopped agent-zero" in vo,
      "voltar: pausa as do Hermes antes de religar o A0 (nenhuma rotina roda duas vezes)")
checa('if v.get("ligada_no_a0") and jobs.get_job(k)' in vi, "virar liga só as que estavam ligadas no A0")
co = (H / "convidado.sh").read_text()
checa(subprocess.run(["bash", "-n", str(H / "convidado.sh")]).returncode == 0, "sintaxe do convidado.sh")
checa('-e AGENTEPESSOAL_CONVIDADO="$LOGIN"' in co and 'REDE=hermes-$LOGIN' in co and 'c.pop("mcp_servers", None)' in co
      and '--perfil "pessoa_$LOGIN" --proprio' in co
      and not re.search(r"-p \S*0\.0\.0\.0", co) and '-p "127.0.0.1:$PORTA:8642"' in co,
      "convidado: Hermes próprio (rede, navegador no perfil dele, sem conectores nem dados do Matheus, só no loopback)")
checa("bash \"$AQUI/convidado.sh\" \"$login\" \"$IMAGEM\"" in sh, "na virada o subir.sh sobe o Hermes de cada convidado")
# isolamento (Matheus 23/10: "de forma alguma acessar nada meu"): o convidado não monta os dados do agente
montagens = re.findall(r'-v "?([^ "]+)"?(?=[ )\n])', co.split("ESC=(", 1)[1].split("docker rm", 1)[0])
checa("/opt/hermes/a0usr:/a0/usr" not in co and "/opt/a0/usr:/a0/usr" not in co and '-v "$A":/a0/usr' in co,
      "convidado: o /a0/usr dele é uma pasta só dele, não os dados do agente")
fontes = [m.split(":")[0] for m in montagens]
checa(all(f.startswith(("$A", "$B/chave", "/opt/hermes/a0usr/whatsapp/$LOGIN", "/opt/hermes/a0usr/segredos/convidados/$LOGIN",
                        "/opt/hermes/a0usr/caixa/segredo.txt", "/opt/hermes/a0usr/plugins/$p")) for f in fontes),
      f"convidado: só a pasta do celular dele, o cofre dele, a chave dele e o código dos plugins: {fontes}")
plug = re.search(r'PLUGINS_CONVIDADO="([^"]+)"', co).group(1).split()
checa(not set(plug) & {"prospeccao", "conteudo", "cerebro", "segundo_cerebro", "rotinas", "auxiliar", "fios_soltos",
                       "iniciativa", "painel", "quadro", "radar", "concorrentes", "especialistas"}
      and {"login_usuarios", "whatsapp", "cofre", "conversas_externas"} <= set(plug),
      "convidado: só o código das ferramentas dele (nada da Raiz, prospecção, conteúdo, cérebro, rotinas do Matheus)")
checa(cfg["approvals"].get("cron_mode") == "approve" and cfg["approvals"]["mode"] == "smart",
      "rotinas rodam código como no A0 (cron_mode approve; a trava de rotina fica no acesso_hermes); conversa segue smart + botões")
alma = (H / "SOUL.md").read_text()
for termo in ("Captcha", "cofre", "Texto de terceiros", "3 caminhos", "segundo_cerebro/pasta", '"n" = NÃO'):
    checa(termo in alma, f"a persona traz {termo!r}")
tudo = "".join(f.read_text() for f in H.iterdir() if f.is_file())
checa(not re.search(r"AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{30,}", tudo), "nenhum segredo no git")
if falhas:
    raise SystemExit("test_hermes: " + "; ".join(falhas))
print("test_hermes: ok")
