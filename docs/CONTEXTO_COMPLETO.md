# Contexto completo da conversa com o Claude (conta antiga, até 10/10/2026)

Complementa `HANDOFF_CONTA_NOVA.md` (como operar). Aqui está o histórico: o que o Matheus pediu, o que foi feito,
o que deu errado e como foi corrigido, e como ele gosta de trabalhar. Nenhuma senha, token ou código está aqui.

## Como o Matheus trabalha (ler primeiro)

- Escreve curto, pelo celular, com erros de digitação; responda em português, curto, sem jargão técnico.
- Quer que as coisas sejam feitas, não planos: "pode implementar", "sim", "trocar msm". Pergunte só o que for
  decisão dele de verdade.
- Quer testes profundos ("os testes pra essas funcionalidades precisam ser mais profundos") e avaliação real do
  resultado ("avaliar se funcionou td"), não só código.
- Avisos no celular (Telegram): só o que importa, objetivos ("toma cuidado pra oq for avisar de resumo, ser mais
  objetivo e filtrar oq de fato importa"). Resposta de lead: avisar na hora. Fim do dia: relatório do que foi feito.
- Arquivos preparados vão como anexo no celular (.md vira PDF), nunca como caminho de pasta.
- Voz do resumo em áudio: fluida, nunca robótica (Polly Camila generative; sem troca silenciosa para voz neural).
- Revisor de mensagens proativas: Luna ou Haiku 5.5, nunca Sol. Luna venceu a bateria (12/12 contra 11/12).
- Senhas: o que ele cadastrou no cofre e mandou usar, o agente usa direto, sabendo de qual site/conta é (o cofre
  guarda a descrição de cada senha). Para só em captcha, 2FA ou senha errada.
- Captcha: nunca resolver nem contornar; ele resolve pela tela do navegador do agente.

## Restrições permanentes

- Segredos só no cofre/SSM. Nunca repetir senhas/tokens (Facebook, Gmail, bot do Telegram, TypeSafe, NEXOS, app
  secret, PATs do GitHub, entradas do cofre) no chat, em arquivo ou no git.
- Nada de pagamento, meio de pagamento ou campanha com gasto ("garanta que n vai gastar do cartao e sim dos
  créditos").
- Nunca mexer no app Barber Dock (2229462691177967), nos WABAs/números dele, nem nas contas de anúncio reais
  act_1384895845137880 / act_1749449932839674 — análise de anúncios só leitura.
- Mensagem a terceiros só com aprovação dele, exceto a prospecção pré-aprovada (abaixo).
- Não apagar ativos/dados sem cuidado; não buscar endpoints de execução remota; não usar WhatsApp Web para
  automação; nenhum piloto real do IA Business antes da ROS-F9-013.
- Prospecção nunca pelo Instagram pessoal @cardosomatheus1; só @raiz.connect.
- Logins pelo servidor da AWS podem disparar verificação; o agente pode usar o cofre quando o site pede senha.
- Sem identificador de modelo em commits; PR só se ele pedir.

## Linha do tempo do que foi construído

1. **Base do agente (fases 1–9):** Agent Zero na EC2, proxy de modelos (Bedrock/OpenAI-compatível, TypeSafe),
   ponte WhatsApp/Telegram, cofre de senhas com 2FA, rotinas ("salvar como rotina", correções), gatilhos por
   evento, resumo diário, conectores Google (MCP com trava por dono), agentes com função, voz, navegador separado
   por pessoa, avisos por tipo e horário de silêncio, pesquisa proativa em Gmail/Agenda, painel, memória,
   conferência, e-mail do agente (encaminhar → agir), escrita em Docs/Planilhas/Drive.
2. **Iniciativa (o auxiliar proativo):** candidatos com nota, revisor Luna, arquivos anexados. Problema resolvido:
   respondia sempre SEM NOVIDADE (panorama cortado e contexto ancorado) → passo de candidatos com nota.
3. **As 8 ideias do auxiliar** (plugin `auxiliar`): rascunhos de e-mail no estilo dele; briefing antes e pergunta
   depois da reunião; vigia do Google por Apps Script (**ele ainda precisa instalar o `vigia_google.gs`**);
   esperando terceiros; contas com lembrete (Decimal + moeda); revisão da semana; resumo da manhã em áudio; perfil
   de estilo de escrita (só com o que ele digitou no celular). Suíte de 21 testes + e2e de 12 cenários.
   Correções do e2e: instrução do gatilho presa a "Matheus" → modelo por login; reunião cancelada mantinha
   tarefas → `cancelar`; tarefa planejada sem dono → contexto pré-criado; aviso duplicado → mensagem única
   "⚡ Aviso"; rascunho vago → citar cada ponto; pós-reunião não registrado → extensão determinística.
   Voz: "IA" lida como "ea" → mapa de pronúncia.
4. **Faturamento Vertex/Gemini:** Google bloqueou login pela AWS; ele logou no navegador do agente; saldo zerado,
   orçamento de R$ 50 → `vertex_ok`.
5. **Cofre:** descrições de cada senha, regra de uso automático, `/senha` pergunta de qual site e conta é.
   Senhas conhecidas por nome: DNA (exames), Gmail ("falha no sistema"), Instagram (Raiz Connect).
6. **Radar:** não repete alertas já resolvidos (`resolvidos_recentes` no prompt).
7. **Raiz Connect (o SaaS dele, ERP para produtores de alimentos):** dificuldade de conseguir clientes. Ele não
   quer o agente montando funil (já fez 4 funis com muita visita e nenhum cadastro). Análise dos anúncios (só
   leitura): muito LPV e pouco cadastro, pixel ausente no cadastro, otimização em LPV, ~277 LPV no total;
   sugestões: Lead Ads, calculadora como destino. "Problema n é atender, problema é o lead chegar" → rotinas de
   geração de leads (prospecção).
8. **Prospecção Raiz** (plugin `prospeccao`, detalhes no handoff): playbook, nota do lead 0–100, aprovação
   automática com revisor Luna dentro dos limites, rotina diária, resumo das 20h17 no Telegram, aviso imediato
   de resposta (Direct e comentários), conferência obrigatória do Direct/notificações antes de executar, primeira
   mensagem em pergunta (variante A) × oferta (B), links só da calculadora e do simulador de delivery no
   lembrete/respostas, quem interagiu vai primeiro. Primeira rodada (10/10): 34 perfis abertos, 9 leads em
   Salvador, 8 aquecidos (limite do piloto), comentários publicados em @emporiodacau, @fit_plusoficial e
   @heyhey_food. Erros corrigidos: conta pessoal logada → trava de conta ativa; campo de comentário não abria →
   comentar pela página do post; post fixado confundia "mais recente"; busca achava 1 lead → meta e método;
   rodada abria notificações sem ler → `conferido` obrigatório; revisor rigoroso demais → recalibrado (30/30).
9. **Iscas do site da Raiz** (abertas e percorridas até o fim): calculadora
   `/materiais/precificacao/calculadora` (melhor, começa sem cadastro, conta certa); simulador
   `/materiais/quanto-sobra-no-delivery` (resultado na hora); planilha `/materiais/precificacao` (pede dados antes:
   mais atrito); Raio-X e 15 erros (marcam "às vezes" como erro inteiro → "8 de 8"/"15 de 15"; falam "restaurante").
10. **Troca de conta do Claude (10/10):** créditos da conta antiga acabando. Navegador do agente logado no
    claude.ai como sejaorbyte@gmail.com; máquina de build do IA Business logada na conta nova; ambiente
    "Agente pessoal e NEXOS" criado; sessões abertas na conta nova: construtora (Main Opus, na máquina),
    orquestradora/vigia (libera toda aprovação humana por delegação — pedido dele: "não precisa dessa aprovação
    de humano, ele libera sempre que a sessão parar") e esta (agente pessoal).

## Pendências

- Primeiras DMs da prospecção saem segunda 12/10 (variantes A/B, revisor); conferir qualidade e resultado; relatório
  semanal compara variantes e faixas de nota.
- @zen.marmitas (aquecimento aprovado) sai no domingo.
- Vigia do Google (Apps Script) ainda precisa ser instalado por ele.
- Tarefa #5 antiga: WhatsApp ponta a ponta (hoje o canal principal é o Telegram).
- Apagar `/agentepessoal/transferencia/*` do SSM depois de confirmar a AWS na sessão nova.
- Avisar o Matheus: a conta nova tem redução de Max 20x para Max 5x agendada para 13/10.
- O trabalho está no branch `ccr-bcbe3101-9u4klv`; perguntar se ele quer mesclar no principal.
