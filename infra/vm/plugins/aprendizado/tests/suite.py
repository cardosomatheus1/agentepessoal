"""Tests of aprendizado with the model mocked: no network, no Agent Zero. Run with implantar.py (staging copy) or from the
repository root: python3 infra/operador/rodar_suites_locais.py aprendizado"""

import asyncio
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import traceback
import types
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
REPO_SKILL = """---
name: prospeccao-instagram
description: "Prospecção pelo Instagram."
version: 1.0.0
---

# Prospecção
Regra antiga."""


class Falha(AssertionError):
    pass


def eq(a, b, msg):
    if a != b:
        raise Falha(f"{msg}: esperado {b!r}, veio {a!r}")


def ok(cond, msg):
    if not cond:
        raise Falha(msg)


def _modulo(nome, arquivo, stubs=None):
    stubs = stubs or {}
    antes = {k: sys.modules.get(k) for k in stubs}
    sys.modules.update(stubs)
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


def _sync(corrotina):
    """Run a coroutine that never really awaits (also from inside the suite runner's event loop)."""
    try:
        corrotina.send(None)
    except StopIteration as fim:
        return fim.value
    raise Falha("a extensão esperou algo (não devia)")


def _msg(content):
    return types.SimpleNamespace(content=content, output_text=lambda c=content: json.dumps(c, ensure_ascii=False)
                                 if not isinstance(c, str) else c)


class Suite:
    def __init__(self):
        self.resultados = []
        self.a = _modulo("aprendizado_aprender_teste", RAIZ / "helpers" / "aprender.py")

    def _pastas(self):
        tmp = Path(tempfile.mkdtemp(prefix="aprendizado-teste-"))
        skills, dados = tmp / "skills", tmp / "dados"
        (skills / "prospeccao-instagram").mkdir(parents=True)
        (skills / "prospeccao-instagram" / "SKILL.md").write_text(REPO_SKILL, encoding="utf-8")
        return tmp, skills, dados

    def t_quando_revisar(self):
        a = self.a
        ok(a.deve_revisar(8, "faz a planilha", None, 1000), "tarefa longa: revisa")
        ok(not a.deve_revisar(3, "faz a planilha", None, 1000), "tarefa curta sem correção: não")
        ok(a.deve_revisar(2, "não era isso, já falei que é pelo Drive", None, 1000), "correção dele: revisa mesmo curta")
        ok(a.deve_revisar(3, "Mandou duplicado de novo", None, 1000), "'de novo' é correção")
        ok(not a.deve_revisar(20, "x", 1000 - 60, 1000), "revisou há 1 minuto nesta conversa: espera")
        ok(a.deve_revisar(20, "x", 1000 - a.INTERVALO - 1, 1000), "passado o intervalo: revisa")
        # 21/10: tarefa curta em que um passo falhou e outro caminho funcionou: o caminho que funcionou vira lição
        reais = ["Browser upload_file failed: upload_file could not resolve selector 'input[type=file]'",
                 '{"action": {"files": ["KE.xlsx"], "via": "janela de arquivos aberta por \'Anexar arquivo\'"}}',
                 "Itens Enviados: Tem anexos"]
        ok(a.contornou(reais), "falhou e depois funcionou")
        ok(not a.contornou(reais[1:]), "nada falhou: não é contorno")
        ok(not a.contornou(reais[:1]), "falhou e terminou falhando: não é contorno")
        ok(a.contornou(["ok", "bash> x\n⟦código de saída 127⟧\n↳ Próximo passo: use python3", "Python 3.13"]),
           "terminal: o código de saída e a dica contam como falha")
        ok(a.deve_revisar(3, "manda o e-mail", None, 1000, contorno=True), "contorno: revisa mesmo curta")
        ok(not a.deve_revisar(3, "manda o e-mail", None, 1000, contorno=False), "sem contorno, curta: não")
        ok("Um passo FALHOU e outro caminho FUNCIONOU" in a.PROMPT and "Nunca como \"X não funciona\"" in a.PROMPT,
           "o revisor sabe guardar o caminho que funcionou")

    def t_cria_skill_nova_com_marca_e_diario(self):
        a = self.a
        tmp, skills, dados = self._pastas()
        try:
            pedidos = []

            def modelo(sistema, texto):
                pedidos.append((sistema, texto))
                return 'Pronto:\n{"acao": "criar", "nome": "formularios-web", "descricao": "Preencher formulário de ' \
                       'cadastro em site", "gatilhos": ["formulário", "cadastro"], "conteudo": "# Formulários\\n1. Leia ' \
                       'o formulário inteiro antes de digitar.", "motivo": "o envio falhou por campo escondido"}'
            r = a.revisar("user: preenche o formulário da 99", ["prospeccao-instagram"], "ctx1", modelo, skills, dados, 5000)
            eq(r["feito"], "criada", "skill criada")
            texto = (skills / "formularios-web" / "SKILL.md").read_text(encoding="utf-8")
            ok(texto.startswith("---\nname: formularios-web\n") and "origem: aprendizado" in texto,
               f"cabeçalho com nome e origem: {texto[:200]}")
            ok("version: 1.0.1" in texto and '  - "formulário"' in texto, "versão e gatilhos")
            ok("Leia o formulário inteiro" in texto, "corpo")
            ok(pedidos[0][0] == a.PROMPT and "DADO" in pedidos[0][1], "prompt de revisão; a conversa vai como dado")
            ok(pedidos[0][1].index("## Skill prospeccao-instagram (carregada") < pedidos[0][1].index("# A tarefa"),
               "a skill carregada vai inteira, antes da tarefa")
            linha = json.loads((dados / "diario.jsonl").read_text(encoding="utf-8").splitlines()[-1])
            eq((linha["feito"], linha["nome"], linha["conversa"]), ("criada", "formularios-web", "ctx1"), "diário")
            ok(a.aviso(r).startswith("📚 Aprendi uma skill nova: `formularios-web`"), f"aviso: {a.aviso(r)}")
            eq(a.ultimo("ctx1", dados), 5000, "hora da revisão guardada por conversa")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def t_atualiza_so_a_propria_e_guarda_a_anterior(self):
        a = self.a
        tmp, skills, dados = self._pastas()
        try:
            criar = {"acao": "criar", "nome": "formularios-web", "descricao": "d", "conteudo": "v1", "motivo": "m"}
            a.aplicar(criar, "c", skills, dados, 1000)
            r = a.aplicar({**criar, "acao": "atualizar", "conteudo": "v2 com a correção"}, "c", skills, dados, 2000)
            eq(r["feito"], "atualizada", "a skill do aprendizado é reescrita")
            texto = (skills / "formularios-web" / "SKILL.md").read_text(encoding="utf-8")
            ok("v2 com a correção" in texto and "version: 1.0.2" in texto, "conteúdo novo, versão sobe")
            antiga = list((dados / "historico").glob("formularios-web-*.md"))
            ok(len(antiga) == 1 and "\nv1\n" in antiga[0].read_text(encoding="utf-8"), "a anterior fica guardada")
            r = a.aplicar({"acao": "atualizar", "nome": "prospeccao-instagram", "conteudo": "Regra nova", "motivo": "x"},
                          "c", skills, dados, 3000)
            eq(r["feito"], "sugestao", "skill do repositório: só sugestão")
            eq((skills / "prospeccao-instagram" / "SKILL.md").read_text(encoding="utf-8"), REPO_SKILL, "e ela fica intacta")
            ok("Regra nova" in (dados / "sugestoes.md").read_text(encoding="utf-8"), "a sugestão fica anotada")
            eq(a.aviso(r), "", "sugestão não vira aviso no celular")
            r = a.aplicar({"acao": "criar", "nome": "prospeccao-instagram", "conteudo": "x", "motivo": "x"},
                          "c", skills, dados, 3000)
            eq(r["feito"], "sugestao", "'criar' com nome de uma skill do repositório também não a sobrescreve")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def t_recusa_o_que_nao_deve_gravar(self):
        a = self.a
        tmp, skills, dados = self._pastas()
        try:
            for proposta, por in [
                ({"acao": "criar", "nome": "../etc", "conteudo": "x"}, "nome com caminho"),
                ({"acao": "criar", "nome": "Corrigir Pedido", "conteudo": "x"}, "nome fora do padrão"),
                ({"acao": "criar", "nome": "tokens-api", "conteudo": "use a chave sk-abcdefghijklmnopqrstuvwx"}, "segredo"),
                ({"acao": "criar", "nome": "grande-demais", "conteudo": "x" * (a.SKILL_MAX + 1)}, "tamanho"),
                ({"acao": "criar", "nome": "vazia", "conteudo": "  "}, "vazia"),
            ]:
                eq(a.aplicar(proposta, "c", skills, dados, 1)["feito"], "recusada", por)
            eq(sorted(p.name for p in skills.iterdir()), ["prospeccao-instagram"], "nada gravado")
            eq(a.revisar("t", [], "c2", lambda s, t: "não sei", skills, dados, 1)["feito"], "recusada", "sem JSON")
            eq(a.revisar("t", [], "c3", lambda s, t: '{"acao": "nada"}', skills, dados, 1)["feito"], "nada", "nada a salvar")
            eq(a.interpretar('{"acao": "apagar", "nome": "x"}'), None, "ação desconhecida (apagar) não existe")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def t_pedido_corta_conversa_longa_e_limita_skills(self):
        a = self.a
        skills = {f"s{i}": {"descricao": f"d{i}", "texto": "y" * 15_000, "nossa": False} for i in range(5)}
        pedido = a.montar_pedido("início " + "z" * (a.CONVERSA_MAX * 2) + " fim", skills, ["s3"])
        ok("início" in pedido and pedido.rstrip().endswith("fim") and "cortado" in pedido, "começo e fim da tarefa")
        ok(pedido.count("## Skill s") <= a.SKILLS_MAX // 15_000, "teto das skills inteiras")
        ok("## Skill s3 (carregada nesta tarefa)" in pedido, "a carregada entra primeiro")
        ok(all(f"- s{i}: d{i}" in pedido for i in range(5)), "todas listadas por nome")

    def _extensao(self):
        stubs = {"agent": types.ModuleType("agent"), "helpers": types.ModuleType("helpers"),
                 "helpers.extension": types.ModuleType("helpers.extension")}
        stubs["agent"].LoopData = type("LoopData", (), {})
        stubs["helpers.extension"].Extension = type(
            "Extension", (), {"__init__": lambda self, agent=None, **k: setattr(self, "agent", agent)})
        m = _modulo("aprendizado_ext_teste", RAIZ / "extensions" / "python" / "monologue_end" / "_64_aprender.py", stubs)
        m.aprender = lambda: self.a
        return m

    def t_tarefa_conta_passos_fala_e_skills(self):
        m = self._extensao()
        hist = types.SimpleNamespace(current=types.SimpleNamespace(messages=[
            _msg({"user_message": "manda pro Drive, não por e-mail"}),
            _msg('{"tool_name": "skills_tool", "tool_args": {"action": "load", "skill_name": "planilhas-drive"}}'),
            _msg({"tool_name": "skills_tool", "tool_result": "ok"}),
            _msg({"tool_name": "browser", "tool_result": "página"}),
        ]))
        texto, passos, fala, carregadas = m.tarefa(hist)
        eq((passos, fala, carregadas), (2, "manda pro Drive, não por e-mail", ["planilhas-drive"]), "leitura da tarefa")
        eq(m.resultados(hist), ["ok", "página"], "os resultados das ferramentas, em ordem")
        longo = types.SimpleNamespace(current=types.SimpleNamespace(messages=[
            _msg({"tool_name": "code_execution_tool", "tool_result": "linha\n" * 2000 + "⟦código de saída 1⟧"})]))
        ok("⟦código de saída 1⟧" in m.resultados(longo)[0], "saída longa: a marca de falha no fim não se perde")
        ok("página" in texto, "texto da tarefa")

    def t_so_nas_conversas_do_matheus(self):
        m = self._extensao()
        iniciadas = []
        m.threading = types.SimpleNamespace(Thread=lambda **k: types.SimpleNamespace(start=lambda: iniciadas.append(k)),
                                            Lock=lambda: None)
        m.carregar = lambda nome, caminho: types.SimpleNamespace(e_rotina=lambda cid: cid == "rotina")
        tmp = Path(tempfile.mkdtemp(prefix="aprendizado-teste-"))
        self.a.DADOS, self.a.DESLIGADO = tmp, tmp / "desligado"
        msgs = [_msg({"user_message": "faz"})] + [_msg({"tool_name": "browser", "tool_result": "x"})] * 9

        def agente(ctx_id="c1", numero=0, **dados):
            ctx = types.SimpleNamespace(id=ctx_id, get_data=lambda k: dados.get(k))
            return types.SimpleNamespace(number=numero, context=ctx,
                                         history=types.SimpleNamespace(current=types.SimpleNamespace(messages=msgs)))
        try:
            casos = [(agente(dono="matheus", whatsapp_de="matheus"), 1, "conversa dele pelo celular"),
                     (agente(ctx_id="c2", dono="matheus"), 1, "conversa dele no app"),
                     (agente(dono="convidado"), 0, "conversa de outra pessoa (as skills valem para todos)"),
                     (agente(numero=1, dono="matheus"), 0, "ajudante"),
                     (agente(ctx_id="rotina", dono="matheus"), 0, "rodada agendada"),
                     (agente(ctx_id="c3", dono="matheus", gatilhos_de="matheus"), 0, "conversa de gatilhos")]
            for ag, esperado, por in casos:
                antes = len(iniciadas)
                _sync(m.Aprender(agent=ag).execute())
                eq(len(iniciadas) - antes, esperado, por)
            self.a.DESLIGADO.write_text("")
            _sync(m.Aprender(agent=agente(ctx_id="c9", dono="matheus")).execute())
            eq(len(iniciadas), 2, "interruptor desligado: nenhuma revisão")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def t_skill_parada_vai_para_o_arquivo(self):
        # 22/10 (Duet videos: skills pile up): ours unused for 30 days are archived; the repository's never
        a = _modulo("aprender_arquivo_teste", RAIZ / "helpers" / "aprender.py")
        tmp = Path(tempfile.mkdtemp(prefix="aprender-arquivo-"))
        raiz, dados = tmp / "skills", tmp / "dados"
        agora = 1_800_000_000.0
        for nome, origem in (("planilha-vendas", "aprendizado"), ("formularios-web", "aprendizado"), ("prospeccao-instagram", "")):
            (raiz / nome).mkdir(parents=True)
            (raiz / nome / "SKILL.md").write_text(f"---\nname: {nome}\ndescription: x\n"
                                                  + (f"origem: {origem}\n" if origem else "") + "---\nregras", encoding="utf-8")
            os.utime(raiz / nome / "SKILL.md", (agora - 60 * 86400, agora - 60 * 86400))
        eq(a.paradas(raiz, dados, agora), [], "sem contagem de uso ainda: nada é parado")
        a.registrar_uso("", dados, agora - 40 * 86400)
        a.registrar_uso("formularios-web", dados, agora - 5 * 86400)
        a.registrar_uso("../etc", dados, agora)
        eq(a.paradas(raiz, dados, agora), ["planilha-vendas"], "só a nossa sem uso; a usada e a do repositório ficam")
        eq(a.arquivar_paradas(raiz, dados, agora), ["planilha-vendas"], "arquivada")
        ok(not (raiz / "planilha-vendas").exists() and list((dados / "arquivo").glob("planilha-vendas-*/SKILL.md")),
           "sai das skills e fica no arquivo, inteira")
        ok((raiz / "prospeccao-instagram" / "SKILL.md").exists(), "a do repositório nunca é tocada")
        ok("arquivada" in (dados / "diario.jsonl").read_text(encoding="utf-8"), "registrado no diário")
        shutil.rmtree(tmp, ignore_errors=True)

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
        print(("✓ " if x["ok"] else "✗ ") + x["teste"] + ("" if x["ok"] else f": {x['erro']} {x['onde']}"))
    print(f"{r['passou']}/{r['total']}")
    sys.exit(0 if r["passou"] == r["total"] else 1)
