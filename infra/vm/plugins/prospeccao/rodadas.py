# Creates/updates the prospecting rounds (scheduled tasks) through the agent API; run from the operator machine.
import asyncio, boto3, json, os, sys
from playwright.async_api import async_playwright
URL = boto3.client("ssm", region_name="us-east-1").get_parameter(Name="/agentepessoal/agent-url")["Parameter"]["Value"].rstrip("/")

SIS_BUSCA = ("Você é o prospector da Raiz Connect. Nesta rodada você só NAVEGA E LÊ no Instagram (pesquisar, abrir perfis, "
             "ler bio e posts): não siga, não curta, não comente, não mande mensagem — quem executa é outra rodada, depois "
             "da aprovação (automática pelo revisor, dentro dos limites do dia, ou do Matheus). A única coisa que você grava é o registro da ferramenta `prospeccao`.")

BUSCAR = """Rodada de busca da prospecção Raiz Connect.

0. Carregue a skill `prospeccao-instagram` (skills_tool load) e siga o método dela; ela tem o COMO no Instagram.
1. `prospeccao` acao "playbook" (leia inteiro: muda) e acao "contexto" (cotas de hoje, leads com passo devido, @ conhecidos e rejeitados).
2. Leads com passo devido ("Devem receber"), na ordem do contexto (maiores notas e quem interagiu primeiro):
   - «dm_abertura»: abra o perfil, veja os 3 posts mais recentes NÃO fixados e escreva no modelo do playbook, alternando A (pergunta sobre como precificam, sem oferta) e B (oferta direta), citando UMA coisa concreta que você viu agora. Sem link. Em `base`, o que viu e em que post (data).
   - «dm_lembrete»: o lembrete do playbook com o link da calculadora (ou o do simulador de delivery para quem vende no iFood), diferente para cada pessoa.
3. Leads novos — META: tantos CRIADOS quanto a cota de «aquecer» de hoje (até 10). PRIMEIRO `prospeccao` acao "fontes" (catálogo de CNPJ + buscador, sem Instagram; chame de novo até a meta ou a fila acabar); só se faltar, a busca no Instagram (skill, seções 2b e 3) até 30 perfis examinados. "http 429" no Instagram não é problema seu: volte para "fontes".
   Para cada lead criado, proponha «aquecer» (maiores notas primeiro); comentário só se houver algo genuíno sobre o post_recente (leads de "fontes" não têm: aquecer sem comentário), sem citar a Raiz; em `base`, o post (data e assunto) ou "achado em fontes".
4. Tudo em UMA chamada `prospeccao` acao "propor" (lead_id, tipo, texto, variante, base). Recusou? Corrija pelo motivo e proponha de novo uma vez.
5. Resposta final: exatamente SEM NOVIDADE. Só se travou (login, bloqueio, verificação, captcha): "PRECISA DE VOCÊ:" e o que aconteceu."""

SIS_EXEC = ("Você executa a prospecção da Raiz Connect pela conta de Instagram da Raiz (nunca pela pessoal do Matheus). Só executa ações que a ferramenta "
            "`prospeccao` entregar como APROVADAS, com o texto exatamente igual. Nada além disso.")

EXECUTAR = """Rodada de execução da prospecção Raiz Connect.

0. Carregue a skill `prospeccao-instagram` (skills_tool load) e siga o método dela.
1. CONTA: skill, seção 1 — tem que ser @raiz.connect, nunca a pessoal.
2. RESPOSTAS: skill, seção 5 — Direct e notificações; registre cada resposta com `etapa` (onde: direct|comentario), proponha a `resposta` (vai pro ✅ do Matheus) e registre `conferido` (direct, notificacoes copiadas, interagiram). Sem `conferido`, `proxima` não libera nada.
3. EXECUÇÃO: skill, seção 4 — `proxima` com conta_ativa; faça exatamente a ação com o texto exato; confira na tela; `resultado`. Espere 3 min entre ações; no máximo 3 por rodada. "NADA AGORA": termine. Bloqueio: pare e mande bloqueio: true.
4. Resposta final: exatamente SEM NOVIDADE. Só se travou (login, bloqueio, captcha, erro que impede seguir): "PRECISA DE VOCÊ:" e o que aconteceu."""

SEMANA = """Relatório semanal da prospecção Raiz Connect (segunda de manhã). Só leitura.

1. `prospeccao` acao "metricas" com dias 7 e de novo com dias 28.
2. Resposta final (vai inteira ao celular do Matheus), objetiva, no máximo 12 linhas, sem jargão:
*Semana em números:* perfis aquecidos, abordados, responderam (%), leads (%), demos.
*O que funcionou:* variante A × B (taxa de resposta de cada uma; só diga que uma é melhor se houver pelo menos 15 abordados em cada), segmento e cidade que mais responderam.
*O que não funcionou:* propostas que ele pulou (taxa de aprovação), falhas e bloqueios.
*Mudança para esta semana:* 1 a 3 ajustes concretos (ex.: "focar em confeitarias de Salvador", "usar a variante B", "comentários antes da DM"), cada um com o número que justifica.
Se ainda houver menos de 20 abordados no total, diga que é cedo para conclusões e só mostre os números."""

HOJE = """Resumo do dia da prospecção Raiz Connect. Só leitura.

1. Chame `prospeccao` acao "hoje".
2. Se a ferramenta devolver NADA HOJE, responda exatamente SEM NOVIDADE.
3. Senão, responda com o texto que ela devolveu, exatamente como veio (já está no formato do celular). Não acrescente nada."""

TAREFAS = {
    "🎯 Prospecção — buscar": (SIS_BUSCA, BUSCAR, {"minute": "23", "hour": "9", "day": "*", "month": "*", "weekday": "*", "timezone": "America/Bahia"}),
    "🎯 Prospecção — executar": (SIS_EXEC, EXECUTAR, {"minute": "50,20", "hour": "9-19", "day": "*", "month": "*", "weekday": "*", "timezone": "America/Bahia"}),
    "🎯 Prospecção — resumo do dia": ("Você só repassa o resumo do dia da prospecção, sem acrescentar nada.", HOJE, {"minute": "17", "hour": "20", "day": "*", "month": "*", "weekday": "*", "timezone": "America/Bahia"}),
    "🎯 Prospecção — semana": ("Você faz o relatório semanal da prospecção, só leitura.", SEMANA, {"minute": "41", "hour": "8", "day": "*", "month": "*", "weekday": "1", "timezone": "America/Bahia"}),
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
