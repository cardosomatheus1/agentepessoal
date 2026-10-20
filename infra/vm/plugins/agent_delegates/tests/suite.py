"""Tests of the delegates' orchestration on the agent's side (who does what, what never leaves the agent, how a result
reads). No Agent Zero and no host service: the tool runs with stubs and a fake service. Run with implantar.py
(staging copy) or anywhere: python3 tests/suite.py"""

import asyncio
import importlib.util
import sys
import traceback
import types
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


class Falha(AssertionError):
    pass


def eq(a, b, msg):
    if a != b:
        raise Falha(f"{msg}: esperado {b!r}, veio {a!r}")


def ok(cond, msg):
    if not cond:
        raise Falha(msg)


def _carregar(nome: str, arquivo: Path, stubs: dict | None = None):
    antes = {k: sys.modules.get(k) for k in (stubs or {})}
    sys.modules.update(stubs or {})
    try:
        spec = importlib.util.spec_from_file_location(nome, arquivo)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        for k, v in antes.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def _ferramenta():
    stubs = {"helpers": types.ModuleType("helpers"), "helpers.tool": types.ModuleType("helpers.tool")}
    stubs["helpers.tool"].Tool = type("Tool", (), {"__init__": lambda s: None})
    stubs["helpers.tool"].Response = type("Response", (), {"__init__": lambda s, **kw: s.__dict__.update(kw)})
    return _carregar("agent_delegates_delegar_teste", RAIZ / "tools" / "delegar.py", stubs)


class Suite:
    def __init__(self):
        self.e = _carregar("agent_delegates_escolha_teste", RAIZ / "helpers" / "escolha.py")
        self.resultados = []

    def t_contas_mensagens_e_dinheiro_ficam_no_agente(self):
        for tarefa in ("Entre no meu Gmail e resuma os e-mails de hoje", "Faça login no portal do iFood com a senha do cofre",
                       "Mande mensagem no WhatsApp para o lead João", "Envie um e-mail ao cliente com a proposta",
                       "Pague o boleto e compre o domínio", "Rode a prospecção da Raiz de hoje",
                       "Veja minha agenda de amanhã", "Responda ao cliente no Instagram da Raiz"):
            ok(self.e.so_no_a0(tarefa), f"fica no A0: {tarefa}")

    def t_trabalho_comum_pode_ser_delegado(self):
        for tarefa in ("Gere uma planilha com o total por mês do CSV anexo", "Crie uma página HTML de login de exemplo",
                       "Escreva um script que valida o token JWT do arquivo", "Apague as linhas duplicadas da planilha",
                       "Pesquise na web os preços dos concorrentes e compare", "Converta o PDF em DOCX"):
            eq(self.e.so_no_a0(tarefa), "", f"pode delegar: {tarefa}")

    def t_codigo_e_dados_vao_ao_hermes(self):
        for tarefa in ("Gere uma planilha xlsx com os dados do CSV e um gráfico de barras",
                       "Escreva um script python que converte os PDFs em texto", "Calcule a média da tabela e faça o gráfico"):
            eq(self.e.escolher_motor(tarefa)[0], "hermes", tarefa)

    def t_pesquisa_e_segunda_opiniao_vao_ao_openclaw(self):
        for tarefa in ("Pesquise na web os preços de 5 concorrentes de ERP para restaurantes e compare",
                       "Faça uma revisão crítica independente deste plano de lançamento",
                       "Levante notícias e artigos sobre o mercado de food service com as fontes"):
            eq(self.e.escolher_motor(tarefa)[0], "openclaw", tarefa)

    def t_empate_vai_ao_hermes_com_motivo(self):
        motor, motivo = self.e.escolher_motor("Organize isto para mim")
        eq(motor, "hermes", "sem sinal claro, o padrão é o Hermes")
        ok(motivo, "sempre com motivo")

    def t_resultado_mostra_ferramentas_arquivos_e_aviso(self):
        f = _ferramenta()
        txt = f.formatar({"id": "d20261020-180000-abc234", "motor": "hermes", "status": "pronto", "segundos": 42,
                          "ferramentas": ["terminal", "write_file", "terminal"], "resposta": "Feito: total 123.",
                          "arquivos": [{"arquivo": "/a0/usr/workdir/delegados/d1/resumo.xlsx", "bytes": 5000}]},
                         "código, dados ou arquivos")
        ok("hermes (código, dados ou arquivos): pronto em 42 s" in txt, txt)
        ok("terminal, write_file" in txt and txt.count("terminal") == 1, "ferramentas sem repetição")
        ok("/a0/usr/workdir/delegados/d1/resumo.xlsx (5000 bytes)" in txt, "arquivo entregue")
        ok("não verificada" in txt and txt.rstrip().endswith("Feito: total 123."), "resposta marcada como não verificada")
        ok("ainda está trabalhando" in f.formatar({"id": "x", "motor": "openclaw", "status": "rodando", "segundos": 9}),
           "rodando avisa e ensina a conferir")
        eq(f.formatar({"erro": "motor deve ser hermes ou openclaw"}), "NÃO DELEGADO: motor deve ser hermes ou openclaw",
           "recusa do serviço")

    def t_lista_de_arquivos_aceita_texto(self):
        f = _ferramenta()
        eq(f.lista_arquivos("/a0/usr/a.csv, /a0/usr/b.pdf\n/a0/usr/c.png"), ["/a0/usr/a.csv", "/a0/usr/b.pdf", "/a0/usr/c.png"],
           "vírgula ou linha")
        eq(f.lista_arquivos(None), [], "sem arquivos")

    async def t_ferramenta_recusa_sem_chamar_o_servico(self):
        f = _ferramenta()
        chamadas = []
        f.pedir = lambda *a, **k: chamadas.append(a) or {"erro": "não devia"}
        f.RAIZ = RAIZ
        ferr = f.Delegar()
        r = await (ferr.execute(tarefa="Entre no meu Gmail e copie os anexos"))
        ok(r.message.startswith("NÃO DELEGADO") and "fica com você" in r.message, r.message)
        r = await (ferr.execute(tarefa="   "))
        ok("Escreva a `tarefa`" in r.message, "tarefa vazia")
        eq(chamadas, [], "nada foi pedido ao serviço")

    async def t_ferramenta_escolhe_motor_e_espera(self):
        f = _ferramenta()
        f.INTERVALO = 0
        pedidos = []
        respostas = iter([{"id": "d1", "status": "rodando", "motor": "openclaw", "segundos": 5},
                          {"id": "d1", "status": "pronto", "motor": "openclaw", "segundos": 30, "ferramentas": ["exec"],
                           "resposta": "ok", "arquivos": []}])

        def pedir(acao, dados, tempo=120):
            pedidos.append((acao, dados))
            return {"id": "d1", "motor": dados["motor"]} if acao == "iniciar" else next(respostas)
        f.pedir = pedir
        r = await (f.Delegar().execute(tarefa="Pesquise na web e compare os preços de 3 concorrentes",
                                            arquivos="/a0/usr/workdir/x.csv", minutos=99))
        eq(pedidos[0][0], "iniciar", "primeiro inicia")
        eq(pedidos[0][1]["motor"], "openclaw", "auto escolheu o OpenClaw")
        eq(pedidos[0][1]["minutos"], 30, "minutos limitados a 30")
        eq(pedidos[0][1]["arquivos"], ["/a0/usr/workdir/x.csv"], "arquivos em lista")
        ok("pronto em 30 s" in r.message and "exec" in r.message, r.message)

    def t_manual_e_indice_falam_da_divisao(self):
        manual = (RAIZ / "prompts" / "agent.system.tool.delegar.md").read_text(encoding="utf-8")
        for termo in ("orquestrador", "Hermes", "OpenClaw", "Você mesmo", "/trabalho/saida/", "não verificada"):
            ok(termo in manual, f"manual cita {termo!r}")
        indice = RAIZ.parent / "prompt_enxuto" / "helpers" / "indice.py"
        if indice.exists():
            txt = indice.read_text(encoding="utf-8")
            ok('"delegar":' in txt and "orquestra" in txt, "o índice curto apresenta delegar como orquestração")

    async def rodar(self, so=""):
        for nome in sorted(n for n in dir(self) if n.startswith("t_") and (not so or so in n)):
            try:
                feito = getattr(self, nome)()
                if asyncio.iscoroutine(feito):
                    await feito
                self.resultados.append({"teste": nome, "ok": True})
            except Exception as exc:
                self.resultados.append({"teste": nome, "ok": False, "erro": f"{type(exc).__name__}: {exc}",
                                        "onde": traceback.format_exc().splitlines()[-3:]})
        return {"passou": sum(r["ok"] for r in self.resultados), "total": len(self.resultados),
                "resultados": self.resultados}


if __name__ == "__main__":
    r = asyncio.run(Suite().rodar(sys.argv[1] if len(sys.argv) > 1 else ""))
    for x in r["resultados"]:
        print("ok   " if x["ok"] else "FALHA", x["teste"], x.get("erro", ""), *(x.get("onde") or []) if not x["ok"] else "")
    print("TESTES", r["passou"], r["total"])
