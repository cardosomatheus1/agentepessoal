import os
import asyncio, boto3, json, sys
from playwright.async_api import async_playwright
URL = boto3.client("ssm", region_name="us-east-1").get_parameter(Name="/agentepessoal/agent-url")["Parameter"]["Value"].rstrip("/")
import importlib.util
spec = importlib.util.spec_from_file_location("cf", "criar_fios.py")
src = open("criar_fios.py").read()
FIOS = src[src.index('PROMPT = """') + 11: src.index('"""', src.index('PROMPT = """') + 11)]
FIOS = FIOS.replace("""   e) LIGAÇÕES:""", """   e) ESPERANDO DE TERCEIROS: com o conector `google`, e-mails que o Matheus enviou entre 3 e 14 dias atrás (busca "in:sent newer_than:14d older_than:3d") cuja conversa não teve resposta depois da mensagem dele, e pedidos dele a outras pessoas/empresas citados nas conversas (análise da Meta, orçamento, entrega). Fio com dono "terceiro: <quem>", detalhe dizendo desde quando espera, e proximo_passo "rascunhar uma cobrança gentil para <quem>" (o botão ✅ Faz pra mim rascunha). Só avise quando a espera passar de 5 dias ou houver prazo;
   f) LIGAÇÕES:""")
assert "ESPERANDO DE TERCEIROS" in FIOS

RADAR = """Radar do Matheus — você é o auxiliar dele: lê tudo e já deixa pronto, mas NUNCA envia, responde, aceita, paga, apaga ou altera nada.

1. Leia /a0/usr/radar/matheus.json: "monitores" (o que o Matheus pediu para vigiar) e "avisados" (ids de e-mail/evento já tratados — não repita).
2. Com o conector `google` (user_google_email = falhanosistema1111@gmail.com):
   - Gmail: e-mails recebidos nas últimas 12 h na caixa de entrada (ignore promoções, redes sociais, newsletters e alertas automáticos sem ação). Leia o conteúdo dos que parecerem importantes.
   - Agenda: eventos de hoje e das próximas 48 h (e mudanças em relação ao que você já tratou).
3. Para cada item NOVO:
   - alguém esperando resposta ou decisão dele → leia o e-mail inteiro e entregue a resposta pronta, no estilo dele, com `rascunho` acao "criar" (se a ferramenta disser que já foi tratado, pule);
   - conta/fatura/boleto/renovação com vencimento → `contas` acao "salvar" (o lembrete sai sozinho no celular; não repita na resposta);
   - reunião nas próximas 48 h com outras pessoas ou pauta → `reuniao` acao "agendar" (briefing 30 min antes e a pergunta do pós); reunião cancelada → `reuniao` acao "cancelar";
   - o resto que pede atenção (prazo, documento pedido, conflito de agenda, evento mudado/cancelado, cobrança estranha, alerta de segurança real, algo que bate com um monitor) → entra na resposta final com uma sugestão curta do que você pode fazer. Monitor com "o_que_fazer" diferente de avisar: sugira a ação, não execute.
4. Acrescente os ids que você tratou em "avisados" no arquivo (mantenha "monitores" como está).
5. Resposta final: se nada além do que as ferramentas já entregaram, exatamente "SEM NOVIDADE". Se algo vence hoje/amanhã, é urgente ou um monitor pediu aviso imediato, comece com "PRECISA DE VOCÊ:". Senão, no máximo 3 itens, do mais importante para o menos, cada um em 1 linha (o quê + o que fazer). Seja objetivo: só o que de fato importa; o que já foi resolvido ou avisado não entra."""

RESUMO_EXTRA = """
6. Contas e reuniões: ferramenta `contas` acao "listar" (o que vence nos próximos 7 dias) e `reuniao` acao "listar" (reuniões de hoje). Ponha as de hoje em *Hoje:* logo depois do título.

O resumo também vira um áudio de ~1 minuto automaticamente: escreva frases claras, sem depender de tabelas."""

REVISAO = """Revisão da semana do Matheus (domingo à noite). Só leitura: não envie, responda, pague, apague nem altere nada.

1. `fios` acao "coletar" com horas 168 (a semana inteira: conversas, tarefas, objetivos, aprovações, memória e fios).
2. `iniciativa` acao "contexto" (o que você sugeriu e como ele reagiu) e `contas` acao "listar".
3. Com o conector `google` (user_google_email = falhanosistema1111@gmail.com): a agenda dos próximos 7 dias.
4. Procure PADRÕES: pedidos parecidos que ele fez 2+ vezes na semana (mesmo tipo de pesquisa, relatório, conferência, mensagem) — candidatos a virar rotina automática.
5. Resposta final (vai inteira ao celular). Ele quer OBJETIVIDADE: só o que importa, no máximo 12 linhas, cada item em 1 linha, linguagem de gente (nada de códigos de etapa, testes, ciclos, nomes de ferramentas):
*Semana em uma linha:* …
*Andou:* até 3 resultados que mudam algo para ele.
*Travado / esperando:* até 3, dizendo de quem depende.
*Semana que vem:* compromissos, prazos e contas que importam.
*Posso virar rotina:* até 2 padrões, cada um com a proposta ("toda segunda às 9h eu…") — ele responde "pode" e você cria. Só se houver padrão de verdade.
*1 foco:* a coisa que mais destrava se ele fizer.
Seção sem item: omita. Sem caminhos de pasta; não invente o que não está nas fontes."""

ESTILO = """Aprenda (ou atualize) como o Matheus escreve, para os rascunhos soarem como ele e não como robô. Só leitura: não envie nem altere nada.

1. Com o conector `google` (user_google_email = falhanosistema1111@gmail.com), leia 30 a 40 e-mails que ELE enviou nos últimos 6 meses (busque "in:sent"; se vier vazio, "from:me"), variados. Ignore encaminhamentos sem texto dele.
2. `rascunho` acao "amostras": o que ele de fato digitou no celular. SÓ isso conta como a voz dele no chat — nunca use prompts de tarefas agendadas, mensagens de teste ou textos de botões.
3. Escreva o perfil e salve com `rascunho` acao "estilo_salvar", `perfil` em português, em duas partes:
   - *E-mail:* saudações e despedidas, tamanho, tom, tratamento, como pede/cobra/recusa/agradece, 2–3 trechos curtos de exemplo. Se não houver e-mails enviados, diga isso e defina um padrão coerente com ele: curto, direto, cordial, português correto (sem as abreviações do chat), saudação "Oi, <nome>!" ou "Olá, <nome>," e despedida "Abraço," / "Obrigado," + "Matheus";
   - *Chat:* como ele escreve no celular (abreviações, pontuação, tamanho, tom), com 3 exemplos curtos reais.
   Sem nomes de terceiros, valores, telefones ou dados sensíveis nos exemplos.
4. Resposta final: exatamente SEM NOVIDADE."""


async def main():
    rodar = [a for a in sys.argv[1:]]
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=os.environ.get("CHROMIUM", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"), headless=True)
        a = await (await b.new_context()).new_page()
        await a.goto(URL + "/login", timeout=120000); await a.wait_for_selector("#username")
        await a.fill("#username", os.environ.get("A0_LOGIN", "matheus")); await a.fill("#password", os.environ["A0_SENHA"]); await a.click("button[type=submit]")
        await a.wait_for_selector("#chat-input", timeout=90000); await a.wait_for_timeout(2000)
        api = """async ([op, dados]) => { const api = await import('/js/api.js');
            if (op === 'lista') { const l = await api.callJsonApi('scheduler_tasks_list', {}); return JSON.stringify((l.tasks||[]).map(t => [t.uuid, t.name, (t.prompt||'').length])); }
            if (op === 'prompt') { const l = await api.callJsonApi('scheduler_tasks_list', {}); return ((l.tasks||[]).find(t => t.uuid === dados) || {}).prompt || ''; }
            if (op === 'update') { const r = await api.callJsonApi('scheduler_task_update', dados); return String(!!(r.task || r.ok)) + (r.error ? ' ' + r.error : ''); }
            if (op === 'create') { const r = await api.callJsonApi('scheduler_task_create', dados); return (r.task || {}).uuid || ('ERRO ' + (r.error || JSON.stringify(r).slice(0,200))); }
            if (op === 'run') { const r = await api.callJsonApi('scheduler_task_run', {task_id: dados}); return String(r.ok ?? r.error ?? JSON.stringify(r).slice(0,100)); } }"""
        lista = json.loads(await a.evaluate(api, ["lista", None]))
        por_nome = {n: u for u, n, _ in lista}
        print("radar:", await a.evaluate(api, ["update", {"task_id": "HL76nfIg", "prompt": RADAR}]))
        print("fios:", await a.evaluate(api, ["update", {"task_id": "8COQyGTD", "prompt": FIOS}]))
        novas = {
            "🗓️ Revisão da semana": ("Você faz a revisão semanal do usuário em modo só leitura.", REVISAO,
                                    {"minute": "47", "hour": "19", "day": "*", "month": "*", "weekday": "0", "timezone": "America/Bahia"}),
            "✍️ Meu estilo de escrita": ("Você aprende o estilo de escrita do usuário em modo só leitura.", ESTILO,
                                         {"minute": "13", "hour": "10", "day": "1", "month": "*", "weekday": "*", "timezone": "America/Bahia"}),
        }
        for nome, (sis, prompt, sched) in novas.items():
            if nome in por_nome:
                print(nome, "update:", await a.evaluate(api, ["update", {"task_id": por_nome[nome], "prompt": prompt}]))
            else:
                por_nome[nome] = await a.evaluate(api, ["create", {"name": nome, "system_prompt": sis, "prompt": prompt, "schedule": sched}])
                print(nome, "criada:", por_nome[nome])
        for nome in rodar:
            print("rodar", nome, await a.evaluate(api, ["run", por_nome.get(nome, nome)]))
        print(json.dumps({n: u for n, u in por_nome.items() if n in novas}, ensure_ascii=False))
        await b.close()
asyncio.run(main())
