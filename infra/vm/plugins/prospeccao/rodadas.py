# Creates/updates the prospecting rounds (scheduled tasks) through the agent API; run from the operator machine.
import asyncio, boto3, json, os, sys
from playwright.async_api import async_playwright
URL = boto3.client("ssm", region_name="us-east-1").get_parameter(Name="/agentepessoal/agent-url")["Parameter"]["Value"].rstrip("/")

SIS_BUSCA = ("Você é o prospector da Raiz Connect. Nesta rodada você só NAVEGA E LÊ no Instagram (pesquisar, abrir perfis, "
             "ler bio e posts): não siga, não curta, não comente, não mande mensagem — quem executa é outra rodada, depois "
             "da aprovação do Matheus. A única coisa que você grava é o registro da ferramenta `prospeccao`.")

BUSCAR = """Rodada de busca da prospecção Raiz Connect.

1. Chame `prospeccao` acao "playbook" e leia INTEIRO (as regras mudam; siga a versão de hoje). Depois `prospeccao` acao "contexto" (cotas que cabem hoje, leads com próximo passo devido, @ já conhecidos).
2. Leads com próximo passo devido (seção "Devem receber"):
   - «dm_abertura»: abra o perfil de cada um, veja os 3 posts mais recentes e escreva uma DM no modelo do playbook (variante indicada ou alternando A/B), citando UMA coisa concreta e verdadeira que você viu agora (produto, post, novidade). Nada genérico.
   - «dm_lembrete»: escreva o lembrete curto do playbook, diferente para cada pessoa.
3. Leads novos — META: registrar tantos quanto couber na cota de «aquecer» de hoje (até 10). Não pare antes de bater a meta ou de ter examinado pelo menos 30 perfis.
   Método (repita até a meta):
   a) abra uma busca: https://www.instagram.com/explore/search/keyword/?q=<termo> com um termo do playbook (ex.: marmitasalvador, marmitafitsalvador, congeladossalvador, docessalvador, bolodepotesalvador, salgadosparafestasalvador, marmitasp, marmitafitsp, confeitariasp, congeladossp, marmitascampinas, confeitariacampinas, docescampinas) — troque de termo quando uma busca secar;
   b) leia a página (content) e anote os @ dos perfis dos posts — pule os já conhecidos e os já rejeitados (estão no "contexto");
   c) abra cada perfil (https://www.instagram.com/<@>/), leia bio, número de seguidores e os 3 posts mais recentes, e decida pelos critérios do playbook;
   d) a cada 5 perfis examinados, grave: os que encaixam com `prospeccao` acao "registrar" (motivo com o que você VIU) e os que não encaixam com `prospeccao` acao "rejeitar" (motivo curto: "franquia", "pessoal", "parado desde junho", "fora da região"…).
   Para cada lead novo, proponha «aquecer». Comentário só se houver algo genuíno e específico a dizer sobre o post mais recente (pergunta ou elogio concreto, sem citar a Raiz); senão, texto vazio.
4. Mande tudo em UMA chamada `prospeccao` acao "propor" (a ferramenta manda para o celular do Matheus aprovar). Se ela recusar algum item, corrija pelo motivo e proponha de novo uma vez; se não der, deixe de fora.
5. Resposta final: exatamente SEM NOVIDADE (as propostas já chegaram no celular). Só se algo travou (Instagram pedindo login, bloqueio, verificação), escreva "PRECISA DE VOCÊ:" e o que aconteceu."""

SIS_EXEC = ("Você executa a prospecção da Raiz Connect pela conta de Instagram da Raiz (nunca pela pessoal do Matheus). Só executa ações que a ferramenta "
            "`prospeccao` entregar como APROVADAS, com o texto exatamente igual. Nada além disso.")

EXECUTAR = """Rodada de execução da prospecção Raiz Connect.

0. CONTA (sempre, antes de tudo) — a conta ativa tem que ser @raiz.connect, NUNCA a pessoal @cardosomatheus1:
   a) abra https://www.instagram.com/accounts/edit/ — o campo de nome de usuário mostra qual conta está ATIVA;
   b) se não for raiz.connect: abra https://www.instagram.com/, clique em "Mais" (≡, no canto) ou na foto do perfil → "Trocar de conta" e escolha raiz.connect (ela já foi adicionada neste navegador; não precisa de senha). Depois abra de novo https://www.instagram.com/accounts/edit/ e confirme;
   c) se a página não carregar, recarregue uma vez; só se raiz.connect NÃO aparecer na lista de "Trocar de conta" (ou pedir senha/código), pare e responda "PRECISA DE VOCÊ: a conta da Raiz saiu do navegador".
1. RESPOSTAS PRIMEIRO (na conta da Raiz): abra o Direct (https://www.instagram.com/direct/inbox/) e veja as conversas com mensagem nova. Para cada conversa com um @ que está no registro (`prospeccao` acao "contexto" mostra os conhecidos):
   - leia a conversa; registre com `prospeccao` acao "etapa": "respondeu" (qualquer resposta), "lead" (mandou receita, pediu o cálculo ou topou conversar) ou "descartado" (disse não / pediu para parar) — com `nota` = o que a pessoa disse, em 1–2 frases;
   - proponha a resposta com `prospeccao` acao "propor" tipo "resposta" (curta, humana, no tom do playbook). Se a pessoa mandou uma receita: faça o cálculo de verdade (custo de cada ingrediente pelo preço que ela informou; se faltou preço, pergunte só o que falta) e responda com custo, margem e quanto sobra por unidade depois de embalagem e taxa do iFood (se vender no iFood). Se disse não: agradeça uma vez, sem insistir.
   Não responda nada direto: só proponha (o Matheus aprova). Conversas com quem não está no registro: ignore.
2. EXECUÇÃO: chame `prospeccao` acao "proxima" com conta_ativa = o @ que está ativo agora (confira de novo antes de cada ação).
   - Se vier uma ação: faça EXATAMENTE o que ela diz no Instagram, com o texto aprovado sem mudar nada. Confira na tela que deu certo (a mensagem aparece enviada, o comentário aparece publicado, o botão virou "Seguindo"). Depois chame `prospeccao` acao "resultado" com acao_id, ok e detalhe. Se o Instagram mostrar bloqueio, limite, "tente novamente mais tarde" ou pedir verificação: PARE e mande resultado com bloqueio: true.
   - Depois de uma ação executada, espere 3 minutos e chame "proxima" de novo. No máximo 3 ações por rodada.
   - Se vier "NADA AGORA": termine.
3. Resposta final: exatamente SEM NOVIDADE (respostas e leads já avisam o Matheus pela ferramenta). Só se travou (login, bloqueio, erro que impede seguir), comece com "PRECISA DE VOCÊ:" e diga o que aconteceu."""

SEMANA = """Relatório semanal da prospecção Raiz Connect (segunda de manhã). Só leitura.

1. `prospeccao` acao "metricas" com dias 7 e de novo com dias 28.
2. Resposta final (vai inteira ao celular do Matheus), objetiva, no máximo 12 linhas, sem jargão:
*Semana em números:* perfis aquecidos, abordados, responderam (%), leads (%), demos.
*O que funcionou:* variante A × B (taxa de resposta de cada uma; só diga que uma é melhor se houver pelo menos 15 abordados em cada), segmento e cidade que mais responderam.
*O que não funcionou:* propostas que ele pulou (taxa de aprovação), falhas e bloqueios.
*Mudança para esta semana:* 1 a 3 ajustes concretos (ex.: "focar em confeitarias de Salvador", "usar a variante B", "comentários antes da DM"), cada um com o número que justifica.
Se ainda houver menos de 20 abordados no total, diga que é cedo para conclusões e só mostre os números."""

TAREFAS = {
    "🎯 Prospecção — buscar": (SIS_BUSCA, BUSCAR, {"minute": "23", "hour": "9", "day": "*", "month": "*", "weekday": "1-6", "timezone": "America/Bahia"}),
    "🎯 Prospecção — executar": (SIS_EXEC, EXECUTAR, {"minute": "50,20", "hour": "9-19", "day": "*", "month": "*", "weekday": "1-6", "timezone": "America/Bahia"}),
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
                print(nome, "update", await a.evaluate(api, ["update", {"task_id": por_nome[nome], "prompt": prompt, "system_prompt": sis}]))
            elif criar:
                por_nome[nome] = await a.evaluate(api, ["create", {"name": nome, "system_prompt": sis, "prompt": prompt, "schedule": sched}])
                print(nome, "criada", por_nome[nome])
        for r in rodar:
            nome = next(n for n in TAREFAS if r in n)
            print("rodar", nome, await a.evaluate(api, ["run", por_nome[nome]]))
        print(json.dumps({n: por_nome.get(n) for n in TAREFAS}, ensure_ascii=False))
        await b.close()
asyncio.run(main())
