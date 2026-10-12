"""Tests of the decisions register (no model calls; data in a temporary folder, never the live one).
Run with implantar.py (staging copy) or inside the container."""

import importlib.util
import shutil
import sys
import tempfile
import threading
import time
import traceback
import types
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
LOGIN = "teste_dec"


class Falha(AssertionError):
    pass


def ok(cond, msg):
    if not cond:
        raise Falha(msg)


def eq(a, b, msg):
    if a != b:
        raise Falha(f"{msg}: esperado {b!r}, veio {a!r}")


def _carregar(nome: str, arquivo: Path, stubs: dict | None = None):
    """Load a plugin file; `stubs` stand in for Agent Zero modules (heavy to import) only while it loads."""
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


def _stubs() -> dict:
    agent = types.ModuleType("agent")
    agent.LoopData = type("LoopData", (), {})
    helpers = types.ModuleType("helpers")
    helpers.projects = types.ModuleType("helpers.projects")
    ext = types.ModuleType("helpers.extension")
    ext.Extension = type("Extension", (), {})
    tool = types.ModuleType("helpers.tool")
    tool.Tool = type("Tool", (), {})
    tool.Response = type("Response", (), {"__init__": lambda self, **kw: self.__dict__.update(kw)})
    return {"agent": agent, "helpers": helpers, "helpers.projects": helpers.projects, "helpers.extension": ext,
            "helpers.tool": tool}


class Suite:
    def __init__(self):
        self.d = _carregar("memoria_decisoes_teste", RAIZ / "helpers" / "decisoes.py")
        self.resultados = []

    def _pasta_nova(self):
        if getattr(self, "_tmp", None):
            shutil.rmtree(self._tmp, ignore_errors=True)
        self._tmp = Path(tempfile.mkdtemp(prefix="decisoes-teste-"))
        self.d.PASTA = self._tmp

    def t_um_por_tema_e_a_nova_substitui(self):
        d = self.d
        r = d.registrar(LOGIN, "Aprovações do Instagram", "Ações no Instagram da Raiz não precisam de ok",
                        tipo="permissao", citacao="aprovo tudo lá do Instagram", por="matheus")
        eq((r["efeito"], r["tema"], r["id"]), ("nova", "aprovacoes-do-instagram", 1), "primeira decisão")
        r2 = d.registrar(LOGIN, "aprovacoes do instagram", "  Ações no Instagram  da Raiz não precisam de ok ",
                         tipo="permissao")
        eq((r2["efeito"], r2["id"]), ("igual", 1), "mesmo texto de novo (espaços e acento no tema não importam): nada muda")
        r3 = d.registrar(LOGIN, "aprovacoes-do-instagram", "Instagram sem ok, menos publicar e impulsionar",
                         tipo="permissao", por="matheus")
        eq((r3["efeito"], r3["id"], r3["anterior"]["id"]), ("substituiu", 2, 1), "texto novo no mesmo tema substitui")
        vivas = d.ativas(LOGIN)
        eq([x["id"] for x in vivas], [2], "só uma em vigor por tema")
        hist = d.historico(LOGIN, "Aprovações do Instagram")
        eq([(x["id"], x["estado"]) for x in hist], [(1, "substituida"), (2, "ativa")], "a antiga fica no histórico")
        eq(hist[0].get("substituida_por"), 2, "a antiga aponta para a nova")
        eq(hist[1].get("citacao", ""), "", "a nova não herda a citação da antiga")
        d.registrar(LOGIN, "avisos", "Menos avisos e mais claros; não perguntar de novo o que já foi decidido")
        eq(len(d.ativas(LOGIN)), 2, "temas diferentes convivem")

    def t_tema_e_campos_obrigatorios(self):
        d = self.d
        eq(d.tema_canonico("  Prospecção / Fontes  "), "prospeccao-fontes", "tema sem acento, minúsculo, com hífen")
        eq(d.tema_canonico("prospeccao..fontes."), "prospeccao.fontes", "ponto separa níveis")
        for args, o in (({"tema": "", "decisao": "uma decisão qualquer"}, "sem tema"),
                        ({"tema": "x", "decisao": "curta"}, "decisão curta demais"),
                        ({"tema": "x", "decisao": "uma decisão qualquer", "tipo": "talvez"}, "tipo desconhecido")):
            try:
                d.registrar(LOGIN, **args)
            except d.DecisaoInvalida:
                continue
            raise Falha(f"{o}: devia recusar")
        eq(d.ativas(LOGIN), [], "nada recusado foi gravado")

    def t_revogar(self):
        d = self.d
        a = d.registrar(LOGIN, "tela-celular", "A tela do celular virtual fica como está")
        b = d.registrar(LOGIN, "aws", "Acesso total da AWS mantido; não propor restringir a chave")
        eq(d.revogar(LOGIN, f"#{a['id']}", motivo="mudou de ideia", por="matheus")["estado"], "revogada", "pelo número")
        eq(d.revogar(LOGIN, "AWS")["id"], b["id"], "pelo tema")
        eq(d.ativas(LOGIN), [], "revogada não vale mais")
        eq(d.revogar(LOGIN, "aws"), None, "revogar o que não está em vigor não faz nada")
        c = d.registrar(LOGIN, "aws", "Acesso total da AWS mantido; não propor restringir a chave")
        eq((c["efeito"], c.get("substitui")), ("nova", None), "decidir de novo depois de revogar cria uma nova")

    def t_prompt_proibicoes_primeiro_vencidas_fora_e_limite(self):
        d = self.d
        eq(d.texto_para_prompt(LOGIN), "", "sem decisões: bloco vazio")
        agora = time.time()
        d.registrar(LOGIN, "preferencia.tom", "Português, curto e sem jargão", tipo="preferencia")
        d.registrar(LOGIN, "pagamentos", "Nada de pagamento, campanha com gasto ou meio de pagamento", tipo="proibicao")
        d.registrar(LOGIN, "temporaria", "Pausar as rodadas de prospecção hoje", valido_ate=agora - 60)
        texto = d.texto_para_prompt(LOGIN)
        linhas = texto.splitlines()
        ok(linhas[0].startswith("- #2 **pagamentos** (não pode"), f"proibição vem primeiro: {linhas}")
        ok("temporaria" not in texto, "decisão vencida (valido_ate) não aparece")
        for i in range(30):
            d.registrar(LOGIN, f"tema{i:02d}", f"Uma decisão comprida o bastante para ocupar espaço número {i}")
        curto = d.texto_para_prompt(LOGIN, limite=600)
        ok(len(curto) < 800 and "(mais " in curto and "acao \"listar\"" in curto, f"limite com aviso de que há mais: {curto}")
        ok(curto.splitlines()[0].startswith("- #2 **pagamentos**"), "o corte nunca tira as proibições do topo")

    def t_arquivo_ilegivel_nao_vira_vazio(self):
        d = self.d
        d.registrar(LOGIN, "senhas", "Não trocar senhas nem apagar backups; só evitar que algo fique público")
        arq = d.arquivo(LOGIN)
        arq.write_text("{quebrado", encoding="utf-8")
        try:
            d.registrar(LOGIN, "outra", "Qualquer coisa decidida depois do arquivo quebrar")
            raise Falha("gravar sobre um arquivo ilegível devia dar erro")
        except d.EstadoIlegivel:
            pass
        eq(arq.read_text(encoding="utf-8"), "{quebrado", "o arquivo ilegível não foi sobrescrito")
        ok("não consegui ler" in d.texto_para_prompt(LOGIN), "o bloco do prompt avisa em vez de quebrar o turno")
        ok(not list(d.PASTA.glob(".*.tmp")), "nenhum arquivo temporário largado")

    def t_duas_gravacoes_ao_mesmo_tempo_nao_se_apagam(self):
        d = self.d
        erros = []

        def gravar(prefixo):
            try:
                for i in range(15):
                    d.registrar(LOGIN, f"{prefixo}{i}", f"Decisão {prefixo} número {i} gravada em paralelo")
            except Exception as exc:  # pragma: no cover
                erros.append(repr(exc))

        fios = [threading.Thread(target=gravar, args=(p,)) for p in ("a", "b", "c")]
        [f.start() for f in fios]
        [f.join() for f in fios]
        eq(erros, [], "sem erro nas gravações paralelas")
        vivas = d.ativas(LOGIN)
        eq(len(vivas), 45, "as 45 decisões ficaram (nenhuma gravação apagou a outra)")
        eq(sorted(x["id"] for x in vivas), list(range(1, 46)), "números únicos e seguidos")

    def t_ferramenta_e_bloco_do_turno(self):
        d = self.d
        ferramenta = _carregar("memoria_decisao_tool_teste", RAIZ / "tools" / "decisao.py", _stubs())
        r = ferramenta.executar(d, LOGIN, "registrar", tema="aprovacoes.instagram", tipo="permissao",
                                decisao="Ações no Instagram da Raiz não precisam de ok; só avisar",
                                citacao="aprovo tudo lá do Instagram")
        ok(r.startswith("Registrado #1 aprovacoes.instagram") and "Anotado:" in r, r)
        r = ferramenta.executar(d, LOGIN, "registrar", tema="aprovacoes.instagram", tipo="permissao",
                                decisao="Ações no Instagram da Raiz não precisam de ok; só avisar")
        ok(r.startswith("Já estava registrado"), r)
        r = ferramenta.executar(d, LOGIN, "registrar", tema="x", decisao="")
        ok(r.startswith("Não registrei"), r)
        r = ferramenta.executar(d, LOGIN, "listar", busca="instagram")
        ok("aprovacoes.instagram" in r and "aprovo tudo" in r, r)
        ok(ferramenta.executar(d, LOGIN, "listar", busca="whatsapp").startswith("Nenhuma decisão"), "busca sem achado")
        r = ferramenta.executar(d, LOGIN, "revogar", id="1", motivo="teste")
        ok(r.startswith("Revogada #1"), r)
        ok("ativa" not in ferramenta.executar(d, LOGIN, "historico", tema="aprovacoes.instagram").split("[")[-1], "histórico")
        ctx = types.SimpleNamespace(get_data=lambda k: {"usuario": "", "dono": "Ana"}.get(k))
        eq(ferramenta.quem(ctx), "ana", "sem quem fala, vale o dono da conversa")
        ctx = types.SimpleNamespace(get_data=lambda k: {"usuario": "Matheus", "dono": "ana"}.get(k))
        eq(ferramenta.quem(ctx), "matheus", "quem fala tem prioridade (mesma regra do bloco de memória)")

        ext = _carregar("memoria_ext_teste", RAIZ / "extensions" / "python" / "system_prompt" / "_17_memoria_pessoal.py",
                        _stubs())
        d.registrar(LOGIN, "avisos", "Menos avisos e mais claros; não perguntar o que já foi decidido")
        bloco = ext.bloco_decisoes(LOGIN, "Matheus", d)
        ok("Decisões de Matheus em vigor" in bloco and "**avisos**" in bloco and "ferramenta `decisao`" in bloco, bloco)
        quebrado = types.SimpleNamespace(texto_para_prompt=lambda q: 1 / 0)
        ok("indisponível" in ext.bloco_decisoes(LOGIN, "Matheus", quebrado), "erro no registro não derruba o turno")

    async def rodar(self, so=""):
        try:
            for nome in sorted(n for n in dir(self) if n.startswith("t_") and (not so or so in n)):
                self._pasta_nova()
                try:
                    getattr(self, nome)()
                    self.resultados.append({"teste": nome, "ok": True})
                except Exception as exc:
                    self.resultados.append({"teste": nome, "ok": False, "erro": f"{type(exc).__name__}: {exc}",
                                            "onde": traceback.format_exc().splitlines()[-3:]})
        finally:
            shutil.rmtree(getattr(self, "_tmp", ""), ignore_errors=True)
        return {"passou": sum(r["ok"] for r in self.resultados), "total": len(self.resultados),
                "resultados": self.resultados}


if __name__ == "__main__":
    import asyncio

    r = asyncio.run(Suite().rodar(sys.argv[1] if len(sys.argv) > 1 else ""))
    for x in r["resultados"]:
        print("ok   " if x["ok"] else "FALHA", x["teste"], x.get("erro", ""), *(x.get("onde") or []) if not x["ok"] else "")
    print("TESTES", r["passou"], r["total"])
