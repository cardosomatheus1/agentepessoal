# Creates/updates the prospecting rounds (scheduled tasks) through the agent API; run from the operator machine.
import asyncio, boto3, json, os, sys
from playwright.async_api import async_playwright
URL = boto3.client("ssm", region_name="us-east-1").get_parameter(Name="/agentepessoal/agent-url")["Parameter"]["Value"].rstrip("/")

SIS_BUSCA = ("Você é o prospector da Raiz Connect. Nesta rodada você só NAVEGA E LÊ no Instagram (pesquisar, abrir perfis, "
             "ler bio e posts): não siga, não curta, não comente, não mande mensagem — quem executa é outra rodada, depois "
             "da aprovação (automática pelo revisor, dentro dos limites do dia, ou do Matheus). A única coisa que você grava é o registro da ferramenta `prospeccao`.")

BUSCAR = """Rodada de busca da prospecção Raiz Connect.

0. Espere um tempo sorteado (o horário das rodadas não fica fixo): rode no terminal (code_execution_tool) `for i in $(seq $((RANDOM % 19))); do sleep 10; echo $i; done`. Depois carregue a skill `prospeccao-instagram` (skills_tool load) e siga o método dela; ela tem o COMO no Instagram.
1. CONTA: skill, seção 1 (tem de ser @raiz.connect, nunca a pessoal). Depois `prospeccao` acao "playbook" (leia inteiro: muda) e acao "contexto".
2. QUEM DEVE RECEBER (skill, seção 4; textos pelo playbook, seção 5), na ordem do contexto:
   - «dm_abertura»: abra o perfil, leia a bio e os posts recentes e escreva na variante que o contexto indica, citando UMA coisa que está escrita no perfil ou no post (a descrição automática do Instagram não conta). Sem link. Em `base`, o trecho copiado entre aspas e a data do post.
   - «dm_lembrete» (só para quem interagiu) e «seguimento» (2 dias depois do link): pelo playbook, SEM link.
3. As mensagens do passo 2 com `prospeccao` acao "propor" em lotes de até 5, à medida que você lê os perfis (lead_id, tipo, texto, base; variante em branco). "REESCREVA": corrija pelo motivo e mande de novo só esse item (até 3 versões).
4. ESTOQUE DE LEADS (skill, seções 2 e 3; o contexto mostra cada parte e quanto falta): `fontes` (limite 20) e `fontes_instagram` (Apify), de novo até encher; depois `conferir_estoque` (no máximo 3 vezes). Script com a nossa conta só se o Matheus ligou. Não proponha «aquecer»: a execução tira do estoque sozinha. Veja a hora (terminal: `date`) antes de cada lote: termine até 9h03 (de manhã) ou 14h03 (à tarde), antes da execução; o que faltar fica para a próxima busca.
5. Resposta final, uma linha: SEM NOVIDADE; ou CONSULTA LIMITADA (429); ou "PRECISA DE VOCÊ:" e o que travou (conta, bloqueio, verificação, captcha)."""

SIS_EXEC = ("Você executa a prospecção da Raiz Connect pela conta de Instagram da Raiz (nunca pela pessoal do Matheus). Só executa ações que a ferramenta "
            "`prospeccao` entregar como APROVADAS, com o texto exatamente igual. Nada além disso.")

EXECUTAR = """Rodada de execução da prospecção Raiz Connect.

0. Espere um tempo sorteado (o horário das rodadas não fica fixo): rode no terminal (code_execution_tool) `for i in $(seq $((RANDOM % 19))); do sleep 10; echo $i; done`. Depois carregue a skill `prospeccao-instagram` (skills_tool load) e siga o método dela.
1. CONTA: skill, seção 1 (tem de ser @raiz.connect, nunca a pessoal).
2. RESPOSTAS: skill, seção 6. `prospeccao` acao "contexto" diz quais conversas do Direct abrir nesta rodada (ou a VARREDURA COMPLETA); veja também o contador de não lidas, as solicitações e as notificações. Registre cada fala com `etapa` (ou `entrou`, para quem não está no registro): resposta ao nosso comentário vai como etapa "interagiu" (ou "respondeu" com onde "comentario" e negocio: true, se a pessoa falou de preço, custo, lucro ou do sistema); fala no Direct, pela etapa que o playbook manda (seção 6), e então proponha a `resposta` pelo playbook. Reação (❤️, 👍) da pessoa à nossa última mensagem conta como fala; resposta automática não. Quem não está no registro e escreveu: `entrou` (skill, seção 6). Depois `caixa_lida` (direct, notificacoes, interagiram, varredura). Sem ela, a `proxima` não libera nada.
3. EXECUÇÃO: skill, seção 5. `proxima` com conta_ativa; leia a conversa antes de digitar; faça exatamente a ação com o texto exato; confira na tela; `resultado`. "ESPERE": espere com o comando que a ferramenta mostra e chame de novo. No máximo 3 ações feitas por rodada. "NADA AGORA": termine. Bloqueio ou verificação: pare e mande `resultado` com bloqueio: true.
4. Resposta final, uma linha: SEM NOVIDADE; ou "PRECISA DE VOCÊ:" e o que precisa dele (conta, bloqueio, verificação, captcha, erro que impede seguir)."""

# The weekly prospecting report ("🎯 Prospecção — semana", Monday 8:41, gOqdMBE3) became a section of the weekly
# review ("🗓️ Revisão da semana", Sunday 19:47, infra/vm/rotinas/bMU33E1T.json): one message instead of two
# (12/10 review §6). The old task stays disabled on the VM and is no longer managed here.

HOJE = """Resumo do dia da prospecção Raiz Connect. Só leitura.

1. Chame `prospeccao` acao "hoje".
2. Se a ferramenta devolver NADA HOJE, responda exatamente SEM NOVIDADE.
3. Senão, responda com o texto que ela devolveu, exatamente como veio (já está no formato do celular). Não acrescente nada."""

TAREFAS = {
    "🎯 Prospecção — buscar": (SIS_BUSCA, BUSCAR, {"minute": "7", "hour": "8,13", "day": "*", "month": "*", "weekday": "*", "timezone": "America/Bahia"}),
    "🎯 Prospecção — executar": (SIS_EXEC, EXECUTAR, {"minute": "8,38", "hour": "9-12,14-21", "day": "*", "month": "*", "weekday": "*", "timezone": "America/Bahia"}),
    "🎯 Prospecção — resumo do dia": ("Você só repassa o resumo do dia da prospecção, sem acrescentar nada.", HOJE, {"minute": "17", "hour": "20", "day": "*", "month": "*", "weekday": "*", "timezone": "America/Bahia"}),
}


async def main():
    criar = "--criar" in sys.argv
    rodar = [a for a in sys.argv[1:] if not a.startswith("--")]
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome", headless=True)
        a = await (await b.new_context()).new_page()
        await a.goto(URL + "/login", timeout=120000); await a.wait_for_selector("#username")
        await a.fill("#username", os.environ.get("A0_LOGIN", "matheus")); await a.fill("#password", os.environ["A0_SENHA"]); await a.click("button[type=submit]")
        await a.wait_for_selector("#chat-input", timeout=90000); await a.wait_for_timeout(1500)
        api = """async ([op, dados]) => { const api = await import('/js/api.js');
            if (op === 'lista') { const l = await api.callJsonApi('scheduler_tasks_list', {}); return JSON.stringify((l.tasks||[]).map(t => [t.uuid, t.name])); }
            if (op === 'update') { const r = await api.callJsonApi('scheduler_task_update', dados); return String(!!(r.task || r.ok)) + (r.error ? ' ' + r.error : ''); }
            if (op === 'create') { const r = await api.callJsonApi('scheduler_task_create', dados); return (r.task || {}).uuid || ('ERRO ' + (r.error || JSON.stringify(r).slice(0,200))); }
            if (op === 'run') { const r = await api.callJsonApi('scheduler_task_run', {task_id: dados}); return String(r.success ?? r.error ?? ''); } }"""
        por_nome = {n: u for u, n in json.loads(await a.evaluate(api, ["lista", None]))}
        for nome, (sis, prompt, sched) in TAREFAS.items():
            if nome in por_nome:
                print(nome, "update", await a.evaluate(api, ["update", {"task_id": por_nome[nome], "prompt": prompt, "system_prompt": sis, "schedule": sched}]))
            elif criar:
                por_nome[nome] = await a.evaluate(api, ["create", {"name": nome, "system_prompt": sis, "prompt": prompt, "schedule": sched}])
                print(nome, "criada", por_nome[nome])
        for r in rodar:
            nome = next(n for n in TAREFAS if r in n)
            print("rodar", nome, await a.evaluate(api, ["run", por_nome[nome]]))
        print(json.dumps({n: por_nome.get(n) for n in TAREFAS}, ensure_ascii=False))
        await b.close()
asyncio.run(main())
