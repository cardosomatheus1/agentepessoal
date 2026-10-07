# Infra AWS — agente sob demanda

VM EC2 com o Agent Zero que liga só quando você usa, e desliga sozinha.

## O que é criado (`python infra/deploy.py`)

| Recurso | Nome | Para quê |
|---|---|---|
| EC2 `t3.large` (Ubuntu 24.04, disco 40 GB criptografado) | `agentepessoal-agent` | Roda o Agent Zero (imagem Docker `agent0ai/agent-zero:v2.13`) |
| Security group sem nenhuma porta de entrada | `agentepessoal-vm` | Acesso só pelo túnel HTTPS e pelo AWS Systems Manager |
| Role IAM da VM | `agentepessoal-vm` | Bedrock (GPT-6.1 Sol / GPT-6 Luna), backup no S3, parâmetros SSM |
| Lambda + Function URL | `agentepessoal-control` | Página de controle (link pessoal): Ligar / Desligar / Abrir o agente |
| Bucket S3 privado e versionado | `agentepessoal-backup-<conta>` | Backup dos dados do agente |
| Parâmetros SSM | `/agentepessoal/password`, `/agentepessoal/agent-url` | Chave do link pessoal (criptografada) e endereço atual do agente |

Rodar de novo atualiza o que já existe, sem duplicar. `python infra/destroy.py` remove tudo (mantém os backups; use `--delete-backups` para apagar também).

## Como usar

1. Abra o **link pessoal** (Function URL + `#k=<chave>`, impresso pelo deploy) e salve nos favoritos. Não pede senha nem login.
2. **Ligar** → em ~1,5 min o agente abre sozinho. Se já estiver ligado, clique em **Abrir o agente**.
3. Sem uso por 30 min, a VM faz backup e desliga sozinha. Também dá para **Desligar agora**.

O agente não tem tela de login (uso individual). A proteção é: a VM não tem portas abertas, o endereço do agente é aleatório e muda a cada boot, e só a página de controle o revela — e ela só responde a quem tem a chave do link pessoal. A chave fica no AWS Systems Manager → Parameter Store → `/agentepessoal/password`; quem tiver o link pessoal consegue ligar e usar o agente, então não compartilhe.

## Memória e dados

Tudo o que o agente sabe fica em `/opt/a0/usr` na VM: conversas, memória de longo prazo, projetos, arquivos enviados, configurações.

- **O disco da VM continua existindo quando ela desliga**, então nada se perde entre usos.
- **Backup no S3** a cada hora, antes do desligamento por inatividade e em todo desligamento. O bucket guarda versões antigas por 30 dias.
- Se a VM for recriada, o primeiro boot **restaura** tudo do S3.

### Projeto "Carreira"

Criado no primeiro boot (`vm/project-carreira/`). No agente, escolha o projeto **Carreira** no canto superior direito da conversa:

- `perfil.md` — sua ficha (dados, experiência, preferências, respostas padrão de formulário). O agente lê antes de qualquer candidatura e atualiza sempre que você contar algo novo.
- `documentos/` — currículo e outros arquivos; ao anexar um currículo, o agente copia para cá e preenche o perfil.
- `candidaturas.md` — registro de cada candidatura e status.
- Regras: nunca envia candidatura, cria conta ou aceita termos sem sua confirmação.

## Como funciona por dentro

- `vm/user-data.sh.tpl` — configuração do primeiro boot (Docker, serviços, restauração, projeto).
- `vm/bedrock_proxy.py` — gera tokens temporários do Bedrock com a role da VM (sem chave guardada) e registra a última atividade.
- `vm/report_url.py` — liga o túnel Cloudflare do próprio Agent Zero e publica o link no SSM.
- `vm/watchdog.sh` — a cada 5 min: se não houve uso em 30 min (chamadas ao modelo, conversas gravadas ou CPU ocupada), faz backup e desliga.
- `vm/backup.sh` — `aws s3 sync` de `/opt/a0/usr`.
- `control/index.py` — a página de controle (Lambda).

Administração da VM: AWS Systems Manager → Session Manager (não há SSH aberto).
