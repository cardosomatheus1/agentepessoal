"""Every scheduled routine keeps doing everything it did (Matheus, 20/10: "as rotinas podem ficar mais curtas, mas não
podem deixar de fazer nada do que faziam", above all the Raiz Connect ones).

1. The essential items of each routine's prompt (steps, limits, approvals, rules of communication, output sections,
   the "SEM NOVIDADE" condition) are still in it. Prompts live in infra/vm/rotinas/*.json (exported from the VM),
   infra/operador/rotinas_marketing.py and infra/vm/plugins/prospeccao/rodadas.py.
2. The tool list is now one line per tool (prompt_enxuto): every action a routine names for a tool is in that line,
   so the round sees it before the tool's manual arrives.
3. What every round gets around its prompt is still there: the scheduled-task block (LER → ENTENDER → AGIR, SEM
   NOVIDADE, PRECISA DE VOCÊ), the person's decisions, the rules that hold always, the prospecting playbook/manual.

Run: python3 infra/vm/tests/test_rotinas_essenciais.py"""

import ast
import importlib.util
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
PLUGINS = RAIZ / "infra" / "vm" / "plugins"


def _constantes(arquivo: Path, nomes: tuple) -> dict:
    """String constants of a module, read without running it (the operator scripts need AWS at import)."""
    saida = {}
    for no in ast.parse(arquivo.read_text(encoding="utf-8")).body:
        if isinstance(no, ast.Assign) and isinstance(no.targets[0], ast.Name) and no.targets[0].id in nomes:
            saida[no.targets[0].id] = ast.literal_eval(no.value)
    return saida


def fontes() -> dict:
    s = {}
    for arq in sorted((RAIZ / "infra" / "vm" / "rotinas").glob("*.json")):
        d = json.loads(arq.read_text(encoding="utf-8"))
        s[arq.stem] = (d.get("prompt") or "") + "\n" + (d.get("system_prompt") or "")
    m = _constantes(RAIZ / "infra" / "operador" / "rotinas_marketing.py", ("SISTEMA", "DIA", "SEMANA", "MES"))
    s.update({f"marketing:{k}": m[k] + "\n" + m["SISTEMA"] for k in ("DIA", "SEMANA", "MES")})
    r = _constantes(PLUGINS / "prospeccao" / "rodadas.py", ("SIS_BUSCA", "BUSCAR", "SIS_EXEC", "EXECUTAR", "HOJE"))
    s["prospeccao:buscar"] = r["SIS_BUSCA"] + "\n" + r["BUSCAR"]
    s["prospeccao:executar"] = r["SIS_EXEC"] + "\n" + r["EXECUTAR"]
    s["prospeccao:hoje"] = r["HOJE"]
    return s


SECOES_SEMANA = ["*Semana em uma linha:*", "*Instagram:*", "*Direct:*", "*Funcionou / não funcionou:*",
                 "*Mudança da semana (sim ou não?):*", "*Próximos 7 dias:*", "*Vídeo da semana:*"]
SECOES_MES = ["*Mês em uma linha:*", "*Números:*", "*Fase do plano:*", "*Repetir / evitar:*", "*Temas do próximo mês:*"]
SEMANA = ["que são TAXAS", "15 respostas (15%)", "5 leads (5%)", "NÃO é meta de volume", "garantia", "UMA mudança",
          "roteiro curto", "DONO do negócio", "nunca o consumidor", "número de exemplo dito como exemplo", "sem jargão",
          "calculadora grátis", '"sem dado"', '`prospeccao` acao "metricas" dias 7', '`conteudo` acao "desempenho" dias 7',
          "Só leitura"] + SECOES_SEMANA
MES = ["anúncio pago só depois de 10 clientes pagantes", "o site só é publicado com a ordem do Matheus", "dar, dar, dar, pedir",
       "As metas do Direct são taxas", "confirmar com o Matheus", '`prospeccao` acao "metricas" dias 30', "Só leitura"] + SECOES_MES

ESSENCIAIS = {
    # --- Raiz Connect: prospecção
    "prospeccao:buscar": ["só NAVEGA E LÊ", "não siga, não curta, não comente, não mande mensagem",
                          "automática pelo revisor, dentro dos limites do dia", "@raiz.connect, nunca a pessoal",
                          '`prospeccao` acao "playbook" (leia inteiro: muda)', 'acao "contexto"', "«dm_abertura»",
                          "Sem link", '`prospeccao` acao "propor" em lotes de até 5', '"REESCREVA"', "até 3 versões",
                          "`fontes` (limite 20)", "`fontes_instagram`", "`conferir_estoque` (no máximo 3 vezes)",
                          "Script com a nossa conta só se o Matheus ligou", "Espere um tempo sorteado",
                          "skill `prospeccao-instagram`", "SEM NOVIDADE", "CONSULTA LIMITADA (429)", '"PRECISA DE VOCÊ:"'],
    "prospeccao:executar": ["nunca pela pessoal do Matheus", "APROVADAS, com o texto exatamente igual", "Nada além disso",
                            "@raiz.connect, nunca a pessoal", '"direct_script"', '"ler_direct"', "`proxima` com conta_ativa",
                            "faça exatamente a ação com o texto exato", "`resultado`", '"ESPERE"',
                            "antes do primeiro comentário da rodada, leia o playbook", "Espere um tempo sorteado",
                            '"PRECISA DE VOCÊ:" só para conta, bloqueio, verificação ou captcha',
                            '`prospeccao` acao "falha" e SEM NOVIDADE'],
    "prospeccao:hoje": ['`prospeccao` acao "hoje"', "NADA HOJE, responda exatamente SEM NOVIDADE",
                        "exatamente como veio", "Não acrescente nada"],
    # --- Raiz Connect: marketing (rotinas_marketing.py and the live copies exported to infra/vm/rotinas)
    "marketing:DIA": ['`conteudo` acao "agenda" dias 2', '"falhou" ou "incerta"', "amanhã não tiver post marcado",
                      '"PRECISA DE VOCÊ:"', 'responda exatamente "SEM NOVIDADE"', "não envia, publica, agenda, apaga"],
    "Iq73JPEP": ['`conteudo` acao "agenda" dias 2', '"PRECISA DE VOCÊ:"', '"SEM NOVIDADE"'],
    "marketing:SEMANA": SEMANA,
    "QDGSkPVk": SEMANA,
    "marketing:MES": MES,
    "KQxvZAHO": MES,
    # --- Raiz Connect: concorrentes
    "qt0dNXtu": ['`concorrentes` acao "coletar"', "sem jargão", 'número sempre como "valores de exemplo"', "sem emoji",
                 'nunca "aumente seu lucro"', "nunca com o consumidor", '"sem cobertura"', '"SEM NOVIDADE"',
                 "*Novidades:*", "*Instagram da semana:*", "*O que a Raiz pode testar:*", "*Sem cobertura:*"],
    # --- Radar e Iniciativa
    "HL76nfIg": ['`fios` acao "coletar"', "SEM NOVIDADE", '`rascunho`', '`contas`', '`reuniao`'],
    "2FIQTI0o": ['`iniciativa` com acao "contexto"', '"candidatos"', '"enviar"', '"NÃO mande", responda SEM NOVIDADE',
                 "sem jargão técnico", "Não repita fios soltos já avisados"],
    # --- the others
    "nW924Nkj": ["*Precisa de você:*", "*Hoje:*", "*Avançou:*", "*Posso adiantar:*", '`livro` acao "hoje"'],
    "bMU33E1T": ["*Semana em uma linha:*", "*Andou:*", "*Travado / esperando:*", "*Prospecção:*", "*Semana que vem:*",
                 "*Posso virar rotina:*", "*1 foco:*", "taxa de resposta", '`prospeccao` acao "metricas"'],
    "H8kWmYP1": ["SEM NOVIDADE", "Não repetir notificações de estado idêntico", "sem histórico"],
    "lu1v3ube": ["O PDF sai SEMPRE"],
}


def _indice():
    spec = importlib.util.spec_from_file_location("indice_rotinas_teste", PLUGINS / "prompt_enxuto" / "helpers" / "indice.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.CURTAS


def _acoes(ferramenta: str) -> set:
    """Actions a plugin tool declares in its own prompt (its manual)."""
    md = next(PLUGINS.glob(f"*/prompts/agent.system.tool.{ferramenta}.md"), None)
    if md is None:
        return set()
    t = md.read_text(encoding="utf-8")
    nomes = set(re.findall(r'^- (?:`acao`:? )?"([a-z_]+)"', t, re.M)) | set(re.findall(r'acao[`:]* "([a-z_]+)"', t))
    nomes |= {a for grupo in re.findall(r"`acao`: ([^\n]+)", t) for a in re.findall(r'"([a-z_]+)"', grupo)}
    return nomes


def testes():
    falhas = []
    s, curtas = fontes(), _indice()
    for rotina, itens in ESSENCIAIS.items():
        if rotina not in s:
            falhas.append(f"{rotina}: prompt não encontrado")
            continue
        for item in itens:
            if item not in s[rotina]:
                falhas.append(f"{rotina}: falta «{item}»")
    # 2. every action a routine names is in the tool's short line
    for rotina, texto in s.items():
        for ferramenta, curta in curtas.items():
            if f"`{ferramenta}`" not in texto:
                continue
            for acao in _acoes(ferramenta):
                if re.search(rf'[`"]{re.escape(acao)}[`"]', texto) and acao not in curta:
                    falhas.append(f"{rotina}: a linha curta de `{ferramenta}` não cita a ação «{acao}»")
    # 3. what wraps every round
    wa = (PLUGINS / "whatsapp" / "extensions" / "python" / "system_prompt" / "_60_conversa_whatsapp.py").read_text(encoding="utf-8")
    tarefa = wa.split('TAREFA = """', 1)[1].split('"""', 1)[0]
    for item in ("LER → ENTENDER → AGIR", "comece a resposta final com `SEM NOVIDADE`", "`PRECISA DE VOCÊ:`",
                 "`whatsapp_enviar`", "checkpoint/contexto.md", "`consultar_sol`"):
        if item not in tarefa:
            falhas.append(f"bloco das tarefas agendadas: falta «{item}»")
    mem = (PLUGINS / "memoria_pessoal" / "extensions" / "python" / "system_prompt" / "_17_memoria_pessoal.py").read_text(encoding="utf-8")
    if "{bloco_decisoes(quem, nome)}" not in mem:
        falhas.append("as decisões do Matheus (pagamento, @raiz.connect, garantia, oferta) saíram do prompt")
    regras = (PLUGINS / "prompt_enxuto" / "extensions" / "python" / "system_prompt" / "_12_regras_base.py").read_text(encoding="utf-8")
    for item in ("pagar", "terceiros", "apagar", "Captcha", "§§secret(NOME)"):
        if item not in regras:
            falhas.append(f"regras de sempre: falta «{item}»")
    # every scheduled round is assessed at its end and runs with the corrections Matheus approved (20/10)
    mono = PLUGINS / "rotinas" / "extensions" / "python" / "_functions" / "agent" / "Agent" / "monologue"
    fim, inicio = mono / "end" / "_20_autoavaliar.py", mono / "start" / "_30_correcoes_agendada.py"
    if not fim.exists() or "autoavaliar(" not in fim.read_text(encoding="utf-8"):
        falhas.append("o fim da rodada não chama mais a autoavaliação")
    if not inicio.exists() or "correcoes_agendada(" not in inicio.read_text(encoding="utf-8"):
        falhas.append("a rodada não recebe mais as correções aprovadas pelo Matheus")
    pro = curtas["prospeccao"]
    for item in ("@raiz.connect", "nunca o perfil pessoal", "pré-aprovado", "limites do dia", "revisor", '"REESCREVA"',
                 "APROVADAS, com o texto exato", '"playbook"', "`prospeccao-instagram`"):
        if item not in pro:
            falhas.append(f"linha curta da prospecção: falta «{item}»")
    manual = (PLUGINS / "prospeccao" / "prompts" / "agent.system.tool.prospeccao.md").read_text(encoding="utf-8")
    if "pré-aprovado pelo Matheus dentro dos limites do dia" not in manual or "COMENTÁRIO APROVADO" not in manual:
        falhas.append("o manual da prospecção (texto inteiro da ferramenta) perdeu limites ou aprovação")
    playbook = (PLUGINS / "prospeccao" / "playbook.md").read_text(encoding="utf-8")
    if "próxima mensalidade" not in playbook or "@raiz.connect" not in playbook:
        falhas.append("playbook sem a garantia ou sem a conta @raiz.connect")
    return falhas


if __name__ == "__main__":
    f = testes()
    for x in f:
        print("✗", x)
    total = sum(len(v) for v in ESSENCIAIS.values())
    print(f"{'✓' if not f else '✗'} rotinas essenciais: {len(ESSENCIAIS)} rotinas, {total} itens, {len(f)} falha(s)")
    sys.exit(1 if f else 0)
