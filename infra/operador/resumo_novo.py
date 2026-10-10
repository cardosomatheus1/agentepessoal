import os
import asyncio, boto3, json
from playwright.async_api import async_playwright
URL = boto3.client("ssm", region_name="us-east-1").get_parameter(Name="/agentepessoal/agent-url")["Parameter"]["Value"].rstrip("/")
RESUMO = """Monte o resumo da manhã do Matheus. Ele quer OBJETIVIDADE: só o que de fato importa hoje. Em caso de dúvida, deixe de fora.

Fontes (só leitura):
1. `fios` acao "listar" (pendências abertas) — e o prompt já mostra os fios resolvidos nos últimos 7 dias: o que está lá NÃO entra.
2. `contas` acao "listar" e `reuniao` acao "listar".
3. Tarefas agendadas: /a0/usr/scheduler/tasks.json (last_run, last_result) — só para achar bloqueios que precisam DELE.
4. Ações das últimas 24 h que esperam ele: /a0/usr/aprovacoes/atividade/matheus.jsonl (sem resposta / bloqueadas).
5. Objetivos (/goal) bloqueados: /a0/usr/plugins/_goal/goals/*.json.

O que ENTRA:
- o que precisa de uma decisão ou ação dele e ainda está em aberto (confira nas conversas recentes se ele já resolveu);
- compromissos de hoje e contas que vencem hoje ou amanhã;
- no máximo 2 avanços que mudam algo para ele (um resultado, não um processo).
O que NÃO entra: o que já foi resolvido ou dispensado; alerta já avisado que não mudou; rotinas que rodaram normalmente; andamento técnico (códigos de etapa como ROS-…, testes, ciclos, webhooks, placeholders, nomes de ferramentas); linhas vazias como "nenhuma reunião hoje"; sugestões genéricas.

Formato (no máximo 8 linhas além do título; cada item em 1 linha, linguagem de gente: o quê + o que fazer):
*Bom dia! <dia da semana>, <dd/mm>*
*Precisa de você:* …
*Hoje:* … (só se houver)
*Avançou:* … (só se houver algo que valha)
*Posso adiantar:* 1 sugestão concreta (só se for realmente útil)
Seção sem item: omita. Se nada importa hoje, a resposta inteira é: "*Bom dia!* Nada que precise de você hoje. 👍"
Entregue só o resumo na resposta final (ele também vira um áudio curto automaticamente)."""
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=os.environ.get("CHROMIUM", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"), headless=True)
        a = await (await b.new_context()).new_page()
        await a.goto(URL + "/login", timeout=120000); await a.wait_for_selector("#username")
        await a.fill("#username", os.environ.get("A0_LOGIN", "matheus")); await a.fill("#password", os.environ["A0_SENHA"]); await a.click("button[type=submit]")
        await a.wait_for_selector("#chat-input", timeout=90000)
        print(await a.evaluate("async (p) => { const api = await import('/js/api.js'); const r = await api.callJsonApi('scheduler_task_update', {task_id: 'nW924Nkj', prompt: p}); return String(!!(r.task||r.ok)); }", RESUMO))
        await b.close()
asyncio.run(main())
