"""Tests of the loose-ends register's safe writes (temporary folder only; never the live register).
Run with implantar.py (staging copy) or inside the container."""

import importlib.util
import shutil
import sys
import tempfile
import threading
import traceback
import types
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
LOGIN = "teste_fios"


class Falha(AssertionError):
    pass


def ok(cond, msg):
    if not cond:
        raise Falha(msg)


def eq(a, b, msg):
    if a != b:
        raise Falha(f"{msg}: esperado {b!r}, veio {a!r}")


def _carregar(nome: str, arquivo: Path):
    spec = importlib.util.spec_from_file_location(nome, arquivo)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Suite:
    def __init__(self):
        self.f = _carregar("fios_teste", RAIZ / "helpers" / "fios.py")
        self.resultados = []

    def _pasta_nova(self):
        if getattr(self, "_tmp", None):
            shutil.rmtree(self._tmp, ignore_errors=True)
        self._tmp = Path(tempfile.mkdtemp(prefix="fios-teste-"))
        self.f.PASTA = self._tmp

    def t_salvar_ignorar_adiar(self):
        f = self.f
        eq(f.mesclar(LOGIN, [{"titulo": "Pagar a conta de luz", "prioridade": "alta"}]), (1, 0, 0), "criado")
        fid = f.carregar(LOGIN)["fios"][0]["id"]
        eq(f.adiar(LOGIN, fid, 2)["estado"], "adiado", "adiado")
        eq(f.ignorar(LOGIN, fid)["estado"], "ignorado", "ignorado")
        ok("Pagar a conta de luz" in f.carregar(LOGIN)["ruido"], "assunto ignorado vira ruído (não volta)")
        f.mesclar(LOGIN, [{"titulo": "Mandar o contrato"}])
        outro = next(x["id"] for x in f.carregar(LOGIN)["fios"] if x["titulo"] == "Mandar o contrato")
        eq(f.mesclar(LOGIN, [], [outro]), (0, 0, 1), "resolvido")
        eq(f.mesclar(LOGIN, [], [outro]), (0, 0, 0), "resolver de novo não conta")
        ok(not list(f.PASTA.glob(".*.tmp")), "nenhum temporário largado")

    def t_registro_ilegivel_nao_vira_vazio(self):
        f = self.f
        f.mesclar(LOGIN, [{"titulo": "Responder a Anna"}])
        arq = f.arquivo(LOGIN)
        arq.write_text('{"fios": [{"titulo": "Respon', encoding="utf-8")
        try:
            f.mesclar(LOGIN, [{"titulo": "Outro"}])
            raise Falha("gravar por cima de um registro ilegível devia dar erro")
        except f.EstadoIlegivel:
            pass
        eq(arq.read_text(encoding="utf-8"), '{"fios": [{"titulo": "Respon', "o registro não foi sobrescrito")

    def t_gravacoes_simultaneas_nao_se_apagam(self):
        f = self.f
        erros = []

        def gravar(prefixo):
            try:
                for i in range(15):
                    f.mesclar(LOGIN, [{"titulo": f"{prefixo} {i}"}])
            except Exception as exc:  # pragma: no cover
                erros.append(repr(exc))

        fios = [threading.Thread(target=gravar, args=(p,)) for p in ("a", "b", "c")]
        [x.start() for x in fios]
        [x.join() for x in fios]
        eq(erros, [], "sem erro")
        eq(len(f.carregar(LOGIN)["fios"]), 45, "os 45 fios ficaram (nenhuma gravação apagou a outra)")

    def t_listas_no_fim_do_prompt(self):
        # 20/10 (prompt enxuto): the lists changed every few minutes and broke the provider cache from the system prompt
        stubs = {"agent": types.ModuleType("agent"), "helpers.extension": types.ModuleType("helpers.extension")}
        stubs["agent"].LoopData = type("LoopData", (), {})
        stubs["helpers.extension"].Extension = type("Extension", (), {})
        antes = {k: sys.modules.get(k) for k in stubs}
        sys.modules.update(stubs)
        try:
            ext = _carregar("fios_prompt_teste", RAIZ / "extensions" / "python" / "system_prompt" / "_26_fios_soltos.py")
        finally:
            for k, v in antes.items():
                sys.modules.pop(k, None) if v is None else sys.modules.__setitem__(k, v)
        f = self.f
        f.mesclar(LOGIN, [{"titulo": "Mandar o contrato", "prioridade": "alta"}])
        conversas = [{"id": "outra", "nome": "Integração com Drive", "mudou_ha_h": 1.3, "ultima_resposta": "Pasta criada",
                      "pedidos": []}, {"id": "c1", "nome": "esta", "mudou_ha_h": 0, "ultima_resposta": "x", "pedidos": []}]
        f.conversas = lambda login, horas: conversas
        ext._fios = lambda: f
        ext._cache.clear()
        ctx = types.SimpleNamespace(id="c1", get_data=lambda k: {"dono": LOGIN}.get(k))
        obj = ext.FiosSoltosPrompt.__new__(ext.FiosSoltosPrompt)
        obj.agent = types.SimpleNamespace(number=0, context=ctx)
        ld = types.SimpleNamespace(params_persistent={}, extras_persistent={})
        saida = []
        corrotina = obj.execute(system_prompt=saida, loop_data=ld)
        try:
            corrotina.send(None)
        except StopIteration:
            pass
        sistema = "\n".join(saida)
        ok("`fios_soltos`" in sistema and "ferramenta `fios`" in sistema, "as instruções ficam no começo")
        ok("Mandar o contrato" not in sistema and "Integração com Drive" not in sistema, "as listas não ficam no começo")
        fim = ld.extras_persistent["fios_soltos"]
        ok("Mandar o contrato" in fim and "Integração com Drive" in fim and "Pasta criada" in fim, fim)
        ok(" h)" not in fim and "- esta (" not in fim, "sem há N h e sem a própria conversa")
        eq(ext.bloco(LOGIN, "c1", types.SimpleNamespace(abertos=lambda *a: 1 / 0)), "", "registro indisponível: nada")

    def _pasta_falsa(self):
        """A stand-in for plugins/cerebro/helpers/pasta.py: active only for the owner, Pendências kept in memory."""
        p = types.ModuleType("cerebro_pasta")
        p.__file__ = str(self._tmp / "outra-copia" / "pasta.py")  # another copy: fios.pasta() uses it as is
        p.RAIZ = self._tmp / "pasta"
        p.Ilegivel = type("Ilegivel", (RuntimeError,), {})
        p.guardadas = []
        p.ativa = lambda login: login == "matheus"
        p.ler = lambda colecao: [dict(x) for x in p.guardadas]
        p.gravar = lambda colecao, itens: p.guardadas.__setitem__(slice(None), [dict(x) for x in itens])
        p.escrever = lambda caminho, texto: (caminho.parent.mkdir(parents=True, exist_ok=True), caminho.write_text(texto))
        return p

    def _com_modulos(self, **mods):
        """Put fake cerebro modules in sys.modules for one test; returns a function that puts the old ones back."""
        antes = {k: sys.modules.get(k) for k in mods}
        for k, v in mods.items():
            sys.modules.pop(k, None) if v is None else sys.modules.__setitem__(k, v)

        def desfazer():
            for k, v in antes.items():
                sys.modules.pop(k, None) if v is None else sys.modules.__setitem__(k, v)
        return desfazer

    def t_toda_pendencia_do_dono_tem_area(self):
        # 20/10: the round created fios without `area`; the owner's Pendências must all carry one
        f = self.f
        desfazer = self._com_modulos(cerebro_pasta=None, cerebro_migracao=None)
        try:
            cerebro = Path(f.__file__).resolve().parents[2] / "cerebro" / "helpers"
            if (cerebro / "migracao.py").exists():  # repository / VM (a staging copy alone has no cerebro beside it)
                migracao = cerebro / "migracao.py"
                for k in ("cerebro_pasta", "cerebro_migracao"):
                    sys.modules.pop(k, None)
                real = f.pasta()  # the real Pasta, in a temporary folder, migrated
                real.RAIZ = self._tmp / "pasta-real"
                real.RAIZ.mkdir()
                (real.RAIZ / real.MARCA_MIGRADO).write_text("teste")
                palpite, validas = f.area_de("Revisar o cardápio do restaurante")
                eq(palpite, "raiz", "palpite pela tabela da migração do cérebro")
                m = sys.modules["cerebro_migracao"]
                eq(Path(m.__file__).resolve(), migracao.resolve(), "a tabela é a do plugin cerebro, carregada pelo caminho")
                eq(validas, {a for a, _ in m.AREAS} | {"geral"}, "áreas válidas vêm da mesma tabela")
                f.mesclar("matheus", [{"titulo": "Pagar o DAS do MEI"}, {"titulo": "Ligar para a tia"},
                                      {"titulo": "Token da Meta", "ligacoes": "app Nexos na Meta"},
                                      {"titulo": "Proposta da Orbyte", "area": "ORBYTE"},
                                      {"titulo": "Cardápio novo", "area": "financeiro"}])
                areas = {x["titulo"]: x.get("area") for x in f.carregar("matheus")["fios"]}
                eq(areas, {"Pagar o DAS do MEI": "pessoal", "Ligar para a tia": "geral", "Token da Meta": "nexos",
                           "Proposta da Orbyte": "orbyte", "Cardápio novo": "raiz"},
                   "sem área: palpite; área válida fica (minúscula); área desconhecida: palpite")
                ok("tags:" in next((real.RAIZ / "Pendencias").glob("*-pagar-o-das-do-mei.md")).read_text(encoding="utf-8")
                   and "pessoal" in next((real.RAIZ / "Pendencias").glob("*-pagar-o-das-do-mei.md")).read_text(encoding="utf-8"),
                   "a área vai para o arquivo da pendência na Pasta")
            sys.modules["cerebro_pasta"] = self._pasta_falsa()
            # a fake table loaded in place of the cerebro one (another copy wins) and, failing, the fallback "geral"
            falsa = types.ModuleType("cerebro_migracao")
            falsa.__file__ = str(self._tmp / "outra-copia" / "migracao.py")
            falsa.AREAS = (("raiz", ("cardapio",)), ("pessoal", ("mei",)))
            falsa.area_de = lambda *t: "pessoal" if "MEI" in " ".join(str(x or "") for x in t) else "geral"
            sys.modules["cerebro_migracao"] = falsa
            f.mesclar("matheus", [{"titulo": "Renovar o MEI"}])
            fio = next(x for x in f.carregar("matheus")["fios"] if x["titulo"] == "Renovar o MEI")
            eq(fio["area"], "pessoal", "usa a tabela já carregada")
            f.mesclar("matheus", [{"id": fio["id"], "estado": "adiado"}])
            eq(f.obter("matheus", fio["id"])["area"], "pessoal", "atualizar não troca a área que já tem")
            falsa.area_de = lambda *t: 1 / 0
            eq(f.area_de("qualquer"), ("geral", {"geral"}), "tabela quebrada: geral")
            f.mesclar("matheus", [{"titulo": "Outra coisa"}])
            eq(next(x for x in f.carregar("matheus")["fios"] if x["titulo"] == "Outra coisa")["area"], "geral",
               "sem tabela, a pendência ainda tem área (geral)")
            sem = [x["titulo"] for x in f.carregar("matheus")["fios"] if not x.get("area")]
            eq(sem, [], "nenhuma pendência do dono sem área")
            # guests: their register (JSON, outside the Pasta) is unchanged
            f.mesclar(LOGIN, [{"titulo": "Pagar o MEI da Fernanda"}])
            ok("area" not in f.carregar(LOGIN)["fios"][0], "convidado: nada muda")
        finally:
            desfazer()

    def t_rodada_e_ferramenta_pedem_area(self):
        texto = (RAIZ / "prompts" / "agent.system.tool.fios.md").read_text(encoding="utf-8")
        ok("area (raiz | nexos | orbyte | agente | pessoal | geral" in texto and '"area": "nexos"' in texto,
           "a ferramenta pede a área (e o exemplo tem)")
        rotinas = RAIZ.parents[1] / "rotinas"
        if rotinas.exists():  # in the repository (not in the staging copy on the VM)
            import json
            for uuid in ("HL76nfIg", "8COQyGTD"):
                prompt = json.loads((rotinas / f"{uuid}.json").read_text(encoding="utf-8"))["prompt"]
                ok("area raiz|nexos|orbyte|agente|pessoal|geral" in prompt, f"rodada {uuid} pede a área de cada fio")

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
