"""The marketing routines of the Raiz plan (14/10, "atividades diária, semanal e mensal" from the plan doc
"Plano de marketing Raiz Connect — Lucro na Mão em 30 Dias"): created or updated through the scheduler's own API,
never by editing tasks.json. All three only read; nothing is sent, scheduled or published by them. Usage:

    A0_SENHA=$(aws ssm get-parameter ... /agentepessoal/operador-senha ...) python3 infra/operador/rotinas_marketing.py [--rodar "<nome>"]

Then `python3 infra/operador/rotinas.py exportar` keeps the live copy in git."""

import asyncio
import json
import os
import sys

import boto3
from playwright.async_api import async_playwright

URL = boto3.client("ssm", region_name="us-east-1").get_parameter(Name="/agentepessoal/agent-url")["Parameter"]["Value"].rstrip("/")
FUSO = "America/Bahia"
SISTEMA = "Você acompanha o marketing da Raiz Connect em modo só leitura: não envia, publica, agenda, apaga nem altera nada."

DIA = """Fechamento do dia do marketing da Raiz Connect (plano: 1 post por dia na @raiz.connect). Só leitura.

1. `conteudo` acao "agenda" dias 2.
2. Se o post de hoje estiver "falhou" ou "incerta" e ainda não foi avisado, ou se amanhã não tiver post marcado, responda começando com "PRECISA DE VOCÊ:" em 1 linha por item (o quê e o que fazer: amanhã sem post = pedir o post à sessão do Claude que cuida do conteúdo).
3. Senão, responda exatamente "SEM NOVIDADE"."""

SEMANA = """Números da semana do marketing da Raiz Connect (segunda de manhã). Rotina do plano: montar o resumo da semana, dizer o que funcionou e o que não, e propor UMA mudança para o Matheus aprovar ou não (uma por vez, para saber o que fez efeito). Só leitura.

1. `conteudo` acao "desempenho" dias 7 e acao "agenda" dias 7.
2. `prospeccao` acao "metricas" dias 7.
3. Compare com as metas do plano: de 100 primeiras mensagens no Direct, 15 respostas (15%), 5 leads (5%) e 1 teste aberto; pelo menos 5 salvamentos por post de "como fazer"; 5 testes com receitas enviadas por semana (o limite de implementações). O que você não consegue medir daqui (usos da calculadora, testes, assinaturas), diga "sem dado" em vez de inventar.
4. Leia as decisões em vigor (oferta Lucro na Mão em 30 Dias, garantia, cliente, conteúdo): a mudança proposta tem de caber nelas.
5. Escreva um roteiro curto (30 a 45 s, 5 a 7 frases faladas) para o vídeo do Matheus falando para a câmera, tema tirado da dúvida, objeção ou resposta mais comum da semana na prospecção, no tom de "dar" (ensinar algo útil), sem vender, sem jargão e terminando na calculadora grátis.
6. Resposta final (vai ao celular), no máximo 14 linhas, linguagem de gente, sem nome de ferramenta:
*Semana em uma linha:* …
*Instagram:* alcance, salvamentos e seguidores (e o melhor post, pelo salvamento).
*Direct:* mensagens, respostas e leads, com as taxas contra a meta.
*Funcionou / não funcionou:* 1 linha cada.
*Mudança da semana (sim ou não?):* uma só, concreta.
*Próximos 7 dias:* dias sem post, se houver.
*Vídeo da semana:* o roteiro."""

MES = """Revisão do mês do marketing da Raiz Connect (dia 1). Só leitura.

1. `conteudo` acao "desempenho" dias 30 e acao "agenda" dias 14.
2. `prospeccao` acao "metricas" dias 30.
3. Cronograma de 90 dias do plano (datas fixas): fase 1 "Oferta no ar" até 13/11 (envio de receitas e fila no app, importação de ficha técnica, Raio-X e garantia, landing e planos na oferta, cadastro curto e Fernanda livre, sequência do teste ligada, 2 primeiros casos em andamento); fase 2 "Provar" até 13/12 (2 casos reais publicados, calculadora para quem fabrica, 1 vídeo do Matheus por semana, 5 parceiros abordados por semana, 20 implementações no mês); fase 3 "Escalar" até 12/01 (indicação no dia 28 do cliente, anúncio com o vídeo que vende, página para pequenas fábricas, revisar a oferta pelos números). Portões: o site só é publicado com a ordem do Matheus; anúncio pago só depois de 10 clientes pagantes. Diga em que fase estamos pela data e o que você sabe que já aconteceu (pelas conversas e decisões); o que não dá para saber daqui, marque "confirmar com o Matheus".
4. Os 3 posts que mais salvaram ou compartilharam (formatos para repetir) e os 2 que menos renderam (formatos para evitar).
5. Proposta de temas para as próximas 4 semanas, 1 post por dia na proporção dar, dar, dar, pedir: por semana, 3 temas de valor (dúvidas e dores de quem produz alimento, inclusive pequenas fábricas que vendem para loja) e 1 de oferta (Lucro na Mão, garantia ou implementação). Cada tema numa linha, com o formato sugerido (vídeo ou carrossel), variando o conceito visual.
6. Resposta final, no máximo 18 linhas, linguagem de gente, sem nome de ferramenta:
*Mês em uma linha:* …
*Números:* Instagram (alcance, salvamentos, seguidores) e Direct (mensagens, respostas, leads), contra as metas.
*Fase do plano:* onde estamos e o que falta para o próximo portão.
*Repetir / evitar:* formatos.
*Temas do próximo mês:* as 4 semanas."""

ROTINAS = {
    "📣 Raiz — fechamento do dia": (DIA, {"minute": "53", "hour": "16", "day": "*", "month": "*", "weekday": "*"}),
    "📈 Raiz — números da semana": (SEMANA, {"minute": "52", "hour": "8", "day": "*", "month": "*", "weekday": "1"}),
    "🗓️ Raiz — revisão do mês": (MES, {"minute": "7", "hour": "9", "day": "1", "month": "*", "weekday": "*"}),
}


async def main():
    rodar = sys.argv[sys.argv.index("--rodar") + 1] if "--rodar" in sys.argv else ""
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=os.environ.get("CHROMIUM", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"), headless=True)
        a = await (await b.new_context()).new_page()
        await a.goto(URL + "/login", timeout=120000)
        await a.wait_for_selector("#username")
        await a.fill("#username", os.environ.get("A0_LOGIN", "matheus"))
        await a.fill("#password", os.environ["A0_SENHA"])
        await a.click("button[type=submit]")
        await a.wait_for_selector("#chat-input", timeout=90000)
        await a.wait_for_timeout(2000)
        api = """async ([op, dados]) => { const api = await import('/js/api.js');
            if (op === 'lista') { const l = await api.callJsonApi('scheduler_tasks_list', {}); return JSON.stringify((l.tasks||[]).map(t => [t.uuid, t.name])); }
            if (op === 'update') { const r = await api.callJsonApi('scheduler_task_update', dados); return String(!!(r.task || r.ok)) + (r.error ? ' ' + r.error : ''); }
            if (op === 'create') { const r = await api.callJsonApi('scheduler_task_create', dados); return (r.task || {}).uuid || ('ERRO ' + (r.error || JSON.stringify(r).slice(0,200))); }
            if (op === 'run') { const r = await api.callJsonApi('scheduler_task_run', {task_id: dados}); return String(r.ok ?? r.error ?? JSON.stringify(r).slice(0,100)); } }"""
        por_nome = {n: u for u, n in json.loads(await a.evaluate(api, ["lista", None]))}
        for nome, (prompt, horario) in ROTINAS.items():
            sched = {**horario, "timezone": FUSO}
            if nome in por_nome:
                print(nome, "atualizada:", await a.evaluate(api, ["update", {"task_id": por_nome[nome], "prompt": prompt,
                                                                             "system_prompt": SISTEMA, "schedule": sched}]))
            else:
                por_nome[nome] = await a.evaluate(api, ["create", {"name": nome, "system_prompt": SISTEMA, "prompt": prompt,
                                                                    "schedule": sched}])
                print(nome, "criada:", por_nome[nome])
        if rodar:
            print("rodar", rodar, await a.evaluate(api, ["run", por_nome.get(rodar, rodar)]))
        await b.close()


if __name__ == "__main__":
    asyncio.run(main())
