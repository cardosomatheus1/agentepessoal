# Arquitetura da prospecção (Raiz Connect)

**Implantado em 09/11/2026:** plugin `128b004` pelo implantador oficial, com
121/121 testes em cópia isolada da VM e 12/12 testes novos. ERP `4d36c68`,
migrations 0124–0127 aplicadas. Conexão no cofre exclusivo do Matheus,
configurada pelo helper sem reiniciar Hermes nem compartilhar com convidados.
757 registros sincronizados pela ponte canônica e 308 posses comerciais da
Raiz conferidas; nenhum estado vivo foi editado à mão e nenhuma mensagem foi
enviada pela implantação. As notas de preparação abaixo são históricas.

## Peças e quem é dono de quê

| Peça | Onde | Dono / quem escreve |
|---|---|---|
| Regras do negócio (cliente ideal, tom, modelos, limites) | `plugins/prospeccao/playbook.md` | Matheus decide; Claude edita com teste |
| Lógica e estado (nota, sequência, limites, travas, revisor) | `plugins/prospeccao/helpers/prospeccao.py` | código; a única coisa que escreve `/a0/usr/prospeccao/<login>.json` |
| Fontes de leads fora do Instagram | `plugins/prospeccao/helpers/fontes.py` | código; escreve `<login>_fontes.json` |
| Ferramenta do agente | `plugins/prospeccao/tools/prospeccao.py` | expõe as funções acima ao modelo |
| Como fazer no Instagram | skill `prospeccao-instagram` do Hermes (`infra/vm/hermes/skills/`, semeada uma vez; a do A0 em `skills/` é legado) | o modelo segue; nada de regra de negócio aqui |
| Rodadas agendadas | cron do Hermes, fonte em `infra/vm/hermes/rotinas/` (laMIuaPt buscar, F9Ku9frw executar, aPzaUZiW resumo; `rodadas.py` era o do A0) | cron do Hermes (desde 23/10) |
| Diário | `/a0/usr/prospeccao/<login>_eventos.jsonl` | append-only, gravado por `salvar()` |

Princípio: **o modelo decide o texto e opera o navegador; o código decide o que pode acontecer.** Quem pode receber o
quê, quando, quantas vezes e em que ordem é regra do código, nunca do modelo.

## Estados de uma ação

```
(nova) → proposta → aprovada → executada → apagada
             │          │  └──→ falhou
             │          └──→ cancelada | proposta (texto editado)
             └──→ pulada | expirada | cancelada | proposta (editada)
```

- A tabela `TRANSICOES` é a única fonte. `_mudar()` recusa qualquer salto (`TransicaoInvalida`) e registra no
  diário quem mudou, de onde para onde e por quê.
- Falhou não se repete: uma tentativa nova é uma ação nova.
- Executada que foi apagada no Instagram vira `apagada` (ação `apagada`) e deixa de contar como enviada.

## Travas (invariantes que o código garante)
- Remetente sempre a conta da Raiz; a pessoal é recusada.
- No máximo 2 mensagens sem resposta por lead. Uma resposta por fala da pessoa; robô (Manychat) não é fala.
- Limites por dia por tipo, com as primeiras mensagens subindo por semana (5 → 8 → 10 → 12; um degrau abaixo depois
  de bloqueio); das 9h às 20h, e depois só respostas até 22h; domingo só respostas; de 2 a 6 min entre ações, variando;
  `caixa_lida` (Direct e notificações lidos; antigo `conferido`) antes de executar.
- Vaga de «aquecer» livre (descarte na visita) é reposta pela `proxima` com o melhor lead novo, sem texto, um por vez
  (só com a pré-aprovação ligada); visita que falhou não é tentada de novo.
- Esperas em dias de calendário (aquecido no dia D → primeira mensagem a partir do dia D+2; lembrete D+3).
- Estoque de 100 leads prontos **dividido por fonte** (`ESTOQUE_FONTES`: Instagram 60, planilha 40, catálogo fora da divisão;
  config `estoque_fontes`). Cada lead guarda a `origem`; a reposição de «aquecer» alterna as fontes pela parte de
  cada uma (quem interagiu com a Raiz passa na frente) e `metricas_fontes` mede o funil de cada fonte.
- Achar o Instagram de uma empresa: o @ da fonte, depois o site da empresa (grátis), por último a busca paga (teto
  por dia). Empresa já contatada pelo WhatsApp não entra.
- Bloqueio de ação do Instagram pausa 48 h. O 429 de consulta não é bloqueio: volta às fontes, e nenhum «aquecer»
  sai até o dia seguinte.
- Descarte na visita por perfil parado ou pequeno/grande volta ao estoque em 60 dias (outro negócio, rede e quem disse
  não, nunca). Comentário só em post de até 7 dias, com a data na `base`.
- Texto pré-aprovado passa pelo revisor (modelo independente). Se o motivo dele contradiz o texto (regra simples
  comprova o que ele diz faltar), há uma 2ª revisão com o fato. Sem revisor, nada sai sozinho (vai ao ✅).

## Mudanças: como se faz
1. `git pull`; confira no `git log` se outra sessão mexeu na prospecção nas últimas horas.
2. Mude o código com teste novo em `tests/suite.py`; a suíte inteira passa.
3. Commit + push.
4. `python3 infra/operador/implantar.py prospeccao`. Ele testa numa cópia de estágio na VM (container descartável)
   antes de trocar a viva e grava a versão em `.versao`; o Hermes usa o código novo na próxima chamada. Rodada nova ou
   mudada: `infra/vm/hermes/rotinas/` + `implantar.py --hermes`.
5. Correção de dado vivo: função do helper (com teste), nunca edição do JSON.

## Erros de 11/10 que esta estrutura impede
- **Duas sessões implantando por cima uma da outra** → `implantar.py` recusa versão desconhecida na VM.
- **Registro editado à mão ("duplicada")** → dado só por função; `_mudar()` recusa saltos; diário mostra quem fez.
- **Trava que não solta (mensagem apagada, falhas antigas)** → estado `apagada`; falha antiga não bloqueia depois de
  um envio.
- **Revisor barrando por um motivo falso** → 2ª revisão quando o motivo contradiz o texto.
- **Agente apagando mensagem** → skill proíbe sem ordem explícita e sem ver duas iguais.


## Coordenação comercial com parceiros (fase 1, implementação ainda não publicada)

O ERP mantém a identidade e posse comercial em `ops_leads` e
`ops_commercial_ownership`. O JSON do agente mantém apenas seu diário de execução.
`registrar` sincroniza os registros aceitos com o ERP; falhas ficam indicadas como
`erp_pendente` para repetição por `sincronizar_erp`. `helpers/coordenacao.py` envia
dados públicos, fonte, evidência e nota existente
pela ingestão central; consulta recusa e reserva, e reivindica a posse antes de
liberar a abordagem. `proxima` verifica também ações aprovadas anteriormente;
`comentar` verifica novamente. Falha de rede ou configuração bloqueia a ação.

Configurar na VM, pelo gerenciador de segredos:
- `RAIZ_CRM_URL`: origem HTTPS da API, sem `/api/v1`.
- `PROSPECTING_BRIDGE_TOKEN`: mesmo segredo forte configurado na API.

Antes de retomar abordagens após implantação coordenada, suspender a execução e
rodar `prospeccao(acao="sincronizar_erp", login=...)` para importar o histórico
existente e conferir os bloqueios. Não há credencial padrão. Não publicar o
segredo em prompt, código ou relatório. Esta alteração não foi aplicada na VM.

Testes novos: `python -m unittest discover -s infra/vm/plugins/prospeccao/tests -p test_coordenacao.py -v`.
A suíte legada isola o transporte comercial; os testes novos verificam seu bloqueio
inclusive para uma ação já aprovada que depois tenha sido reservada no ERP.


## Ampliação para restaurantes — 08/11/2026

Por decisão do Matheus, restaurantes, pizzarias, hamburguerias, lanchonetes,
churrascarias e bistrôs integram as buscas. As especialidades usam a rubrica
restaurante existente (15 pontos), sem elevar pesos ou reduzir a nota mínima.
Fontes mantêm a rotação anterior e acrescentam CNAEs 5611201/5611203 e os termos
dessas especialidades. Coordenação com o ERP, reservas, recusa de contato e aprovação
continuam obrigatórias. Alterações locais ainda não foram implantadas na VM.


A referência institucional enviada depois também inclui bares, cafeterias,
sorveterias e açaí. Esses negócios usam a rubrica de atendimento (restaurante,
mesmos 15 pontos). A rotação de diretório inclui CNAEs de bares e palavras desses
ramos. Atender no salão/balcão/delivery não exige que o estabelecimento fabrique
os alimentos: o playbook agora separa esses dois perfis de cliente. Aprovações,
opt-out e coordenação com o CRM permanecem obrigatórios. Validação: 120 casos
legados e 8 casos novos passaram localmente. Nada foi implantado na VM.

### Preparação da integração real — 08/11/2026

A inspeção confirmou Hermes usando a ponte A0 e o plugin instalado em
`/opt/a0/usr/plugins/prospeccao` (versão d9fa99c, ancestral conferido). A base de
prospecção ativa encontrada é a do Matheus. A coordenação agora recebe o login
real e lê a conexão no cofre dessa pessoa: Matheus é obrigado a conferir o ERP;
convidados não herdam a conexão global da Raiz nem têm sua prospecção bloqueada
por essa integração. Não precisa reiniciar os Hermes para atualizar o cofre.

Removidos os descartes antigos de nomes de bares, pizzarias, hamburguerias,
lanchonetes e churrascarias nas fontes; mercados e distribuidores continuam
fora. Testes: 120/120 da suíte original em pasta temporária e 12 testes dirigidos
passaram. Reintroduzir a herança de credenciais globais e os descartes de bares
fez os testes novos falharem; arquivos restaurados e testes verdes.

Implantação e bootstrap concluídos conforme o registro atual no início deste
documento. A conexão autenticada com a ponte foi conferida antes da troca, e
a base foi sincronizada pelo helper, preservando os arquivos de estado locais.
