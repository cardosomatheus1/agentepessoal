"""The failure report of the nightly fix session (falhas_do_dia.py), over the real results of 21/10. No AWS.
Run from the repository root: python3 infra/operador/tests/test_falhas_do_dia.py"""

import importlib.util
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]


def main() -> int:
    spec = importlib.util.spec_from_file_location("falhas_do_dia_teste", RAIZ / "infra" / "operador" / "falhas_do_dia.py")
    f = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(f)
    falhas = []

    def ok(cond, msg):
        if not cond:
            falhas.append(msg)

    reais = {
        "seletor sem ref": "Browser click failed: click could not resolve selector \"button[aria-label='Next']\" to a browser ref",
        "lista feita pelo site": 'Browser select_option failed: Page.evaluate: BrowserPageContentActionError: Browser page content cannot select helper-backed reference "1".',
        "navegador caiu": "Browser open failed: BrowserContext.new_page: Connection closed while reading from the driver",
        "argumento recusado": "A chamada a 'browser' NÃO foi executada: argumento desconhecido 'timeout'.",
        "terminal ainda rodando": "bash>sleep 75\n[SYSTEM: Returning control to agent after 30 seconds with no output. Process might be still running.]",
        "terminal falhou": "bash>python x.py\nbash: python: command not found\n⟦código de saída 127⟧",
        "tecla desconhecida": 'Browser key_chord failed: Keyboard.down: Unknown key: "ARROWDOWN"',
    }
    for esperado, texto in reais.items():
        ok(f.classificar(texto) == esperado, f"{esperado}: veio {f.classificar(texto)!r}")
    ok(f.classificar('{"id": 46, "currentUrl": "https://outlook.live.com/mail/0/"}') == "", "resultado normal não é falha")
    ok(f.classificar("Python 3.13.14\n(venv) root@x:/a0#") == "", "saída normal do terminal não é falha")

    clique = "Browser click failed: click could not resolve selector \"button[aria-label='Next']\" to a browser ref"
    itens = [{"chat": c, "tipo": "tool", "ferramenta": "browser", "args": {"action": "click", "selector": "x"},
              "conteudo": clique} for c in ("A", "A", "B")]
    itens += [{"chat": "C", "tipo": "tool", "ferramenta": "browser", "args": {"action": "content"}, "conteudo": "ok"},
              {"chat": "C", "tipo": "warning", "ferramenta": "", "args": {}, "conteudo": "A0 repetiu a mesma ação (`browser`)"},
              {"chat": "D", "tipo": "code_exe", "ferramenta": "code_execution_tool", "args": {"runtime": "terminal"},
               "conteudo": reais["terminal falhou"]}]
    g = f.agrupar(itens)
    ok(g[0]["tipo"] == "seletor sem ref" and g[0]["vezes"] == 3 and g[0]["conversas"] == ["A", "B"]
       and g[0]["acao"] == "click", f"o maior grupo primeiro, com as conversas: {g[0]}")
    ok(len(g[0]["exemplos"]) == 3 and '"selector": "x"' in g[0]["exemplos"][0]["args"], "exemplos com a chamada real")
    ok({x["tipo"] for x in g} == {"seletor sem ref", "laço", "terminal falhou"}, f"grupos: {[x['tipo'] for x in g]}")
    texto = f.relatorio(g, 24)
    ok(texto.startswith("# Falhas do agente nas últimas 24 h") and "3× seletor sem ref — browser click (2 conversa(s))" in texto,
       f"relatório: {texto[:300]}")
    ok("Nenhuma falha" in f.relatorio([], 24), "dia sem falha")
    ok(f._args({"tool_args": {"tool_args": {"action": "click", "ref": 6}}}) == {"action": "click", "ref": 6},
       "argumentos embrulhados lidos")
    ok(f._args({"action": "wait", "browser_snapshot": {}, "_tool_name": "browser"}) == {"action": "wait"},
       "argumentos direto nos kvps, sem o print")

    spec = importlib.util.spec_from_file_location("avisar_teste", RAIZ / "infra" / "operador" / "avisar_matheus.py")
    a = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(a)
    import base64
    cmd = a.comando('Corrigi 2 falhas "de hoje"; $(rm -rf /) não roda')
    ok("rm -rf" not in cmd and '"de hoje"' not in cmd, "o texto vai em base64: nada dele vira comando")
    b64 = cmd.split("b64decode('")[1].split("'")[0]
    ok(base64.b64decode(b64).decode() == 'Corrigi 2 falhas "de hoje"; $(rm -rf /) não roda', "e chega igual")
    ok("tipo='progresso'" in cmd, "aviso de progresso: segura no horário de silêncio")

    spec = importlib.util.spec_from_file_location("revisar_teste", RAIZ / "infra" / "operador" / "revisar_opencode.py")
    r = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(r)
    ok(r.veredito("...\nVEREDITO: APROVADO") == "aprovado", "aprovado")
    ok(r.veredito("VEREDITO: APROVADO no rascunho\n...\nVEREDITO: REPROVADO — quebra o upload") == "reprovado",
       "vale o último veredito")
    ok(r.veredito("o modelo parou no meio") == "", "sem veredito: a revisão não terminou (não implanta)")
    c = r.comando_vm("revisao_1.patch", "/a0/usr/workdir/revisao_opencode/revisao_1", "x'; rm -rf /; echo '")
    ok("rm -rf" not in c and "opencode2 run --model amazon-bedrock/global.anthropic.claude-opus-5-5" in c,
       "o motivo vai em base64 e o modelo é o Opus 5.5")

    for m in falhas:
        print("FALHA", m)
    print("TESTES", "ok" if not falhas else f"{len(falhas)} falha(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
