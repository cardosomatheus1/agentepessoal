"""Tests of the cleanup rules (no model calls). Run with implantar.py (staging copy) or inside the container."""
import datetime as dt
import importlib.util
import os
import sys
import time
import traceback
import types
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


class Falha(Exception):
    pass


def ok(cond, msg):
    if not cond:
        raise Falha(msg)


def _carregar(nome: str, arquivo: Path):
    try:
        import helpers.extension  # noqa: F401  (inside the container)
    except Exception:
        sys.modules.setdefault("helpers", types.ModuleType("helpers"))
        ext = types.ModuleType("helpers.extension")
        ext.Extension = type("Extension", (), {})
        sys.modules["helpers.extension"] = ext
    spec = importlib.util.spec_from_file_location(nome, arquivo)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def eq(a, b, msg):
    if a != b:
        raise Falha(f"{msg}: esperado {b!r}, veio {a!r}")


class Vivo:
    def __init__(self, vivo=True, erro=False):
        self.vivo, self.erro = vivo, erro

    def is_alive(self):
        if self.erro:
            raise RuntimeError("estado desconhecido")
        return self.vivo


class Suite:
    def __init__(self):
        self.dr = _carregar("limpeza_destravar_teste", RAIZ / "extensions" / "python" / "job_loop" / "_41_destravar_rotinas.py")
        self.resultados = []

    def _tarefa(self, uuid, estado, atualizada_min, ultima_min=None, agendada=True):
        agora = dt.datetime.now(dt.timezone.utc)
        return types.SimpleNamespace(
            uuid=uuid, name=uuid, state=estado, context_id=uuid, schedule={"minute": "23"} if agendada else None,
            updated_at=agora - dt.timedelta(minutes=atualizada_min),
            last_run=None if ultima_min is None else agora - dt.timedelta(minutes=ultima_min))

    def _soltas(self, tarefas, rodando=None, do_chat=None):
        return [s["tarefa"] for s in self.dr.destravar(tarefas, rodando or {}, lambda cid: (do_chat or {}).get(cid),
                                                        time.time(), "running", "error")]

    def t_temporarios_antigos_saem_e_os_em_uso_ficam(self):
        # 20/10: /tmp of the container reached 6.7 GB of build leftovers and the disk hit 89%
        import os
        import tempfile
        T = _carregar("limpeza_temporarios_teste", RAIZ / "helpers" / "temporarios.py")
        base = Path(tempfile.mkdtemp(prefix="limpeza-tmp-"))
        try:
            agora = 1_800_000_000
            velho, novo = agora - 5 * 86400, agora - 3600
            def criar(rel, quando, tam=10):
                p = base / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b"x" * tam)
                os.utime(p, (quando, quando))
                return p
            criar("build-velho/a/b.tar", velho, 1000); os.utime(base / "build-velho/a", (velho, velho)); os.utime(base / "build-velho", (velho, velho))
            criar("em-uso/velho.txt", velho); criar("em-uso/novo.txt", novo); os.utime(base / "em-uso", (velho, velho))
            criar("solto-velho.zip", velho, 500)
            criar("solto-novo.zip", novo)
            criar("models/whisper.bin", velho); os.utime(base / "models", (velho, velho))
            cache = base / "cache-uv"; criar("cache-uv/pkg.whl", novo, 300)
            nomes = sorted(p.name for p in T.escolher(base, agora))
            ok(nomes == ["build-velho", "solto-velho.zip"], f"só o que ninguém mexe há 3+ dias: {nomes}")
            r = T.limpar(agora, tmp=base, caches=[cache])
            ok(not (base / "build-velho").exists() and not (base / "solto-velho.zip").exists(), "velhos apagados")
            ok((base / "em-uso/velho.txt").exists() and (base / "solto-novo.zip").exists(), "pasta em uso e arquivo novo ficam")
            ok((base / "models/whisper.bin").exists(), "modelos de voz ficam")
            ok(not cache.exists() and r["liberado_mb"] >= 0 and len(r["apagados"]) == 3, f"cache esvaziado: {r}")
            ok(T.escolher(base / "nao-existe", agora) == [], "pasta que não existe não quebra")
        finally:
            import shutil
            shutil.rmtree(base, ignore_errors=True)
        ext = _carregar("limpeza_temp_ext_teste", RAIZ / "extensions" / "python" / "job_loop" / "_43_limpar_temporarios.py")
        marca = Path(tempfile.mkdtemp(prefix="limpeza-marca-")) / "m"
        ok(ext.na_hora(marca, 3600) and not ext.na_hora(marca, 3600), "no máximo uma vez por semana")
        ok("/a0/usr" not in str(T.TMP) and all("/a0/usr" not in str(c) for c in T.CACHES), "nunca os arquivos do usuário")

    def t_arquivar_so_conversas_paradas_e_soltas(self):
        a = _carregar("limpeza_arquivar_teste", RAIZ / "helpers" / "arquivar.py")
        agora = 1_800_000_000
        velho, novo = agora - 8 * 86400, agora - 2 * 86400
        itens = [{"id": "parada", "mtime": velho, "data": {}},
                 {"id": "recente", "mtime": novo, "data": {}},
                 {"id": "celular", "mtime": velho, "data": {"whatsapp_de": "matheus"}},
                 {"id": "gatilhos", "mtime": velho, "data": {"gatilhos_de": "matheus"}},
                 {"id": "rodada", "mtime": velho, "data": {}, "tem_tarefa": True},
                 {"id": "rodando", "mtime": velho, "data": {}, "rodando": True}]
        ok(a.escolher(itens, agora) == ["parada"], f"só a parada há 7+ dias e solta: {a.escolher(itens, agora)}")
        ext = (RAIZ / "extensions" / "python" / "job_loop" / "_42_arquivar_conversas.py").read_text(encoding="utf-8")
        ok(ext.index("copytree") < ext.index("AgentContext.remove"), "copia antes de tirar do agente")

    def t_rodada_rodando_nao_e_destravada(self):
        # 12/10: the search started at 9h23 (previous run the day before) and was put back to idle at 9h29, 9h32 and
        # 9h42; each time the scheduler started another copy in the same chat
        buscar = self._tarefa("buscar", "running", atualizada_min=8, ultima_min=1444)
        ok(self._soltas([buscar]) == [], "rodada que começou há 8 min não é destravada, mesmo com a anterior há 24 h")
        longa = self._tarefa("longa", "running", atualizada_min=180, ultima_min=1444)
        ok(self._soltas([longa], rodando={"longa": Vivo()}) == [],
           "rodada que o agendador ainda segura (DeferredTask vivo) nunca é destravada, por mais longa que seja")
        ok(self._soltas([longa], do_chat={"longa": Vivo()}) == [], "rodada viva no chat também não")
        ok(self._soltas([longa], rodando={"longa": Vivo(erro=True)}) == [], "na dúvida (is_alive falhou), deixa quieta")

    def t_rodada_presa_depois_de_reiniciar_volta(self):
        presa = self._tarefa("presa", "running", atualizada_min=120, ultima_min=900)
        ok(self._soltas([presa]) == ["presa"], "marcada como rodando há 2 h sem nada rodando (reinício) volta a ociosa")
        ok(self._soltas([presa], rodando={"presa": Vivo(vivo=False)}) == ["presa"], "DeferredTask morto não segura")
        sem_data = types.SimpleNamespace(uuid="x", name="x", state="running", context_id="", schedule=None,
                                         updated_at=None, last_run=None)
        ok(self._soltas([sem_data]) == ["x"], "sem data nenhuma conta como presa")

    def t_depois_de_reiniciar_volta_na_hora(self):
        # 12/10: copies of a round frozen in a paused chat were killed by restarting the agent; the round stays
        # "running" with nothing running it: it must not wait 90 min (it would miss its next time)
        agora = time.time()
        antes = self._tarefa("antes", "running", atualizada_min=20)
        depois = self._tarefa("depois", "running", atualizada_min=2)
        soltas = [s["tarefa"] for s in self.dr.destravar([antes, depois], {}, lambda cid: None, agora, "running", "error",
                                                         None, {}, agora - 5 * 60)]
        ok(soltas == ["antes"], f"marcada como rodando antes do reinício volta já; a que começou depois, não: {soltas}")

    def t_erro_volta_a_rodar_no_proximo_horario(self):
        erro = self._tarefa("erro", "error", atualizada_min=10, ultima_min=10)
        recente = self._tarefa("recente", "error", atualizada_min=2, ultima_min=2)
        avulsa = self._tarefa("avulsa", "error", atualizada_min=60, ultima_min=60, agendada=False)
        ociosa = self._tarefa("ociosa", "idle", atualizada_min=600, ultima_min=600)
        ok(self._soltas([erro, recente, avulsa, ociosa]) == ["erro"],
           "só a recorrente em erro há mais de 5 min volta; tarefa avulsa e ociosa ficam como estão")

    def t_erro_de_conexao_tenta_de_novo_em_5_15_e_30_min(self):
        # 12/10 review: a round lost because the proxy was not up yet waited for its next time (hours). 14/10: only a
        # run that got no model call back is run again (it did nothing, so nothing is repeated), after 5, 15, 30 min
        dr = self.dr
        base = dt.datetime.now(dt.timezone.utc)
        t0 = base.timestamp()
        tarefa = types.SimpleNamespace(uuid="busca", name="busca", context_id="busca", schedule={"minute": "7"},
                                       state="error", last_result="ERROR: litellm.APIConnectionError: Connection error.",
                                       last_run=base, updated_at=base)
        chamadas = {"busca": 0}
        repetidas = {}

        def checar(minutos):
            r = dr.destravar([tarefa], {}, lambda cid: None, t0 + minutos * 60, "running", "error", None, {}, 0.0,
                             repetidas, lambda cid: chamadas.get(cid))
            return [x.get("acao") for x in r]

        def falhou_de_novo(minutos):
            quando = base + dt.timedelta(minutes=minutos)
            tarefa.state, tarefa.last_run, tarefa.updated_at = "error", quando, quando

        eq(checar(1), [], "acabou de falhar: espera")
        eq(checar(4), [], "4 min: ainda espera")
        eq(checar(6), ["repetir"], "5 min depois: roda de novo")
        tarefa.state = "running"
        eq(checar(7), [], "rodando a nova tentativa: nada")
        falhou_de_novo(8)
        eq(checar(9), [], "falhou de novo sem chamar o modelo: espera 15 min")
        eq(checar(14), [None], "volta a ociosa (pode rodar no horário dela) mas ainda não repete")
        tarefa.state = "idle"
        eq(checar(20), [], "ociosa esperando o degrau")
        eq(checar(24), ["repetir"], "15 min depois da 2ª falha: roda de novo")
        eq(checar(25), [], "uma vez só por degrau")
        falhou_de_novo(26)
        eq(checar(50), [None], "3ª falha: 30 min ainda não passaram")
        tarefa.state = "idle"
        eq(checar(57), ["repetir"], "30 min depois: última tentativa")
        falhou_de_novo(58)
        eq(checar(70), [None], "depois da 3ª nova tentativa, espera o próximo horário dela")
        tarefa.state = "idle"
        eq(checar(200), [], "e não repete mais")

        agiu = types.SimpleNamespace(**{**vars(tarefa), "uuid": "exec", "context_id": "exec", "state": "error",
                                        "last_run": base, "updated_at": base})
        chamadas["exec"] = 3
        outro = types.SimpleNamespace(**{**vars(agiu), "uuid": "outro", "context_id": "outro",
                                         "last_result": "ERROR: KeyError: 'acao'"})
        chamadas["outro"] = 0
        sem_conta = types.SimpleNamespace(**{**vars(agiu), "uuid": "sumiu", "context_id": "sumiu"})
        velha = types.SimpleNamespace(**{**vars(agiu), "uuid": "velha", "context_id": "velha",
                                         "last_run": base - dt.timedelta(minutes=200)})
        chamadas["velha"] = 0
        r = {x["tarefa"]: x.get("acao") for x in dr.destravar(
            [agiu, outro, sem_conta, velha], {}, lambda cid: None, t0 + 6 * 60, "running", "error", None, {}, 0.0,
            repetidas, lambda cid: chamadas.get(cid))}
        eq(r, {"exec": None, "outro": None, "sumiu": None, "velha": None},
           "chamou o modelo (pode ter agido), outro erro, contagem desconhecida ou falha antiga: só volta a ociosa")

    def t_sucesso_reinicia_a_escada(self):
        dr = self.dr
        base = dt.datetime.now(dt.timezone.utc)
        t0 = base.timestamp()
        tarefa = types.SimpleNamespace(uuid="r", name="r", context_id="r", schedule={"minute": "7"}, state="error",
                                       last_result="ERROR: Connection refused", last_run=base, updated_at=base)
        repetidas = {"r": "2026-10-12T10:00:00+00:00"}  # the old file format: a plain marker
        checar = lambda m: [x.get("acao") for x in dr.destravar(  # noqa: E731
            [tarefa], {}, lambda cid: None, t0 + m * 60, "running", "error", None, {}, 0.0, repetidas, lambda cid: 0)]
        eq(checar(6), ["repetir"], "formato antigo do arquivo não atrapalha")
        tarefa.state, tarefa.last_run, tarefa.last_result = "idle", base + dt.timedelta(minutes=8), "feito"
        eq(checar(9), [], "rodou bem")
        ok("r" not in repetidas, "a escada recomeça do zero")
        dr.destravar([], {}, lambda cid: None, t0, "running", "error", None, {}, 0.0, repetidas, lambda cid: 0)
        ok(repetidas == {}, "tarefa que sumiu sai do registro")

    def t_rodada_viva_sem_novidade_ha_20_min_e_encerrada(self):
        # a run the scheduler still holds was never touched: stuck mid-run (a call that never came back), it stayed
        # "running" forever and the round never ran again
        dr = self.dr
        t0 = time.time()
        rodada = self._tarefa("exec", "running", atualizada_min=5)
        viva = {"exec": Vivo()}
        estado = {"sig": "a", "longa": False}
        paradas = {}

        def checar(minutos):
            r = dr.destravar([rodada], viva, lambda cid: None, t0 + minutos * 60, "running", "error", lambda cid: False,
                             {}, 0.0, {}, lambda cid: 1, lambda cid: estado["sig"], lambda cid: estado["longa"], paradas)
            return [(x["acao"], x.get("parada_min")) for x in r]

        eq(checar(0), [], "primeira vez que vê")
        eq(checar(15), [], "15 min sem novidade: espera")
        estado["sig"] = "b"
        eq(checar(16), [], "um item novo no log (ou chamada ao modelo) zera a conta")
        eq(checar(35), [], "19 min depois do último item: espera")
        eq(checar(37), [("encerrar", 21)], "20 min sem nada: encerra a rodada (roda de novo no horário dela)")
        ok("exec" not in paradas, "o registro recomeça")
        estado["longa"] = True
        for m in (40, 70, 100):
            eq(checar(m), [], f"comando de terminal (ou aprovação) em andamento: isenta ({m} min)")
        estado["longa"] = False
        eq(checar(115), [], "terminou o comando: conta a partir da última vez que o viu rodando")
        eq(checar(121), [("encerrar", 21)], "e encerra 20 min depois dela")
        sem = dr.destravar([rodada], viva, lambda cid: None, t0 + 999 * 60, "running", "error", lambda cid: False, {},
                           0.0, {}, lambda cid: 1, lambda cid: None, lambda cid: False, paradas)
        eq(sem, [], "chat não encontrado (atividade desconhecida): deixa quieta")
        ociosa = self._tarefa("exec", "idle", atualizada_min=1)
        paradas["exec"] = {"marca": "a", "desde": t0}
        dr.destravar([ociosa], {}, lambda cid: None, t0, "running", "error", None, {}, 0.0, {}, None, None, None, paradas)
        ok(paradas == {}, "terminou: o registro é da execução")

    def t_atividade_conta_os_chats_dos_ajudantes(self):
        dr = self.dr

        class Ctx:
            def __init__(self, cid, pai="", paralelo=False):
                self.id, self.log = cid, types.SimpleNamespace(guid="g", updates=[])
                self.dados, self.saida = {}, {}
                (self.dados if paralelo else self.saida)["_parallel_parent_context_id" if paralelo else "parent_context_id"] = pai
                self.agent0 = types.SimpleNamespace(data={}, loop_data=types.SimpleNamespace(current_tool=None))

            def get_data(self, k):
                return self.dados.get(k)

            def get_output_data(self, k):
                return self.saida.get(k)

        rodada, ajudante, neto, paralelo, outra = (Ctx("rodada"), Ctx("aj", "rodada"), Ctx("neto", "aj"),
                                                    Ctx("par", "rodada", paralelo=True), Ctx("outra"))
        todos = [rodada, ajudante, neto, paralelo, outra]
        fam = dr.familia("rodada", todos)
        eq(sorted(c.id for c in fam), ["aj", "neto", "par", "rodada"], "a rodada e os chats que ela abriu, em qualquer nível")
        antes = dr.assinatura(fam)
        neto.log.updates.append(1)  # the helper of the helper is working: the round's own log stands still
        ok(dr.assinatura(fam) != antes, "item novo no chat de um ajudante conta como atividade")
        antes = dr.assinatura(fam)
        ajudante.dados["_limpeza_chamadas"] = {"n": 4}
        ok(dr.assinatura(fam) != antes, "chamada ao modelo que voltou conta como atividade")
        ok(not dr.ferramenta_longa(fam), "nada demorado rodando")
        neto.agent0.loop_data.current_tool = types.SimpleNamespace(name="code_execution_tool")
        ok(dr.ferramenta_longa(fam), "comando de terminal num ajudante isenta a rodada")
        neto.agent0.loop_data.current_tool = types.SimpleNamespace(name="browser")
        ok(not dr.ferramenta_longa(fam), "navegador parado não isenta")
        ok(dr.ferramenta_longa(fam, {"aj": {}}), "aprovação esperando o Matheus isenta")

    def t_conta_chamadas_ao_modelo_por_conversa(self):
        contar = _carregar("limpeza_contar_teste", RAIZ / "extensions" / "python" / "chat_model_call_after"
                           / "_10_contar_chamadas.py")
        zerar = _carregar("limpeza_zerar_teste", RAIZ / "extensions" / "python" / "_functions" / "agent" / "Agent"
                          / "hist_add_user_message" / "start" / "_10_zerar_chamadas.py")
        ctx = types.SimpleNamespace(dados={})
        ctx.get_data, ctx.set_data = ctx.dados.get, ctx.dados.__setitem__
        agente = types.SimpleNamespace(number=0, context=ctx)

        def chamada():
            ext = contar.ContarChamadas.__new__(contar.ContarChamadas)
            ext.agent = agente
            coro = ext.execute(call_data={}, response="ok")
            try:
                coro.send(None)
            except StopIteration:
                pass

        def mensagem(no_meio=False):
            ext = zerar.ZerarChamadas.__new__(zerar.ZerarChamadas)
            ext.agent = agente
            ext.execute(data={"args": (agente, "msg"), "kwargs": {"intervention": no_meio} if no_meio else {}})

        mensagem()
        eq(ctx.dados["_limpeza_chamadas"]["n"], 0, "tarefa nova começa do zero")
        chamada()
        chamada()
        eq(ctx.dados["_limpeza_chamadas"]["n"], 2, "cada chamada que voltou conta")
        ok(ctx.dados["_limpeza_chamadas"]["ultima"] > 0, "e guarda a hora")
        mensagem(no_meio=True)
        eq(ctx.dados["_limpeza_chamadas"]["n"], 2, "mensagem lida no meio da tarefa não zera")
        mensagem()
        eq(ctx.dados["_limpeza_chamadas"]["n"], 0, "a próxima rodada zera")
        dr = (RAIZ / "extensions" / "python" / "job_loop" / "_41_destravar_rotinas.py").read_text(encoding="utf-8")
        ok(f'CHAMADAS = "{contar.CHAVE}"' in dr and contar.CHAVE == zerar.CHAVE, "as três partes usam a mesma chave")

    def t_rodada_pausada_e_retomada_ou_cancelada(self):
        # 12/10: the loop detector paused the search round's chat; nobody resumes a scheduled round, so it stayed stuck
        dr, agora = self.dr, time.time()
        buscar = self._tarefa("buscar", "running", atualizada_min=30)
        viva = {"buscar": Vivo()}
        pausas = {}
        def rodar(minutos):
            return self.dr.destravar([buscar], viva, lambda cid: None, agora + minutos * 60, "running", "error",
                                     lambda cid: True, pausas)
        eq = lambda a, b, m: ok(a == b, f"{m}: {a!r}")  # noqa: E731
        eq(rodar(0), [], "acabou de pausar: espera")
        eq(rodar(5), [], "5 min pausada: ainda espera (alguém pode estar olhando)")
        r = rodar(11)
        eq([x["acao"] for x in r], ["retomar"], "pausada há mais de 10 min: retoma uma vez (a execução viva não impede)")
        eq(rodar(12), [], "depois de retomar, conta de novo")
        r = rodar(23)
        eq([x["acao"] for x in r], ["cancelar"], "pausou de novo em menos de 2 h: cancela a execução (volta no próximo horário)")
        ok(dr.destravar([buscar], viva, lambda cid: None, agora + 30 * 60, "running", "error", lambda cid: False, pausas) == [],
           "sem pausa, execução viva: nada a fazer")
        ociosa = self._tarefa("buscar", "idle", atualizada_min=1)
        pausas2 = {"buscar": {"desde": agora - 3600}}
        dr.destravar([ociosa], {}, lambda cid: None, agora, "running", "error", lambda cid: True, pausas2)
        ok("desde" not in pausas2.get("buscar", {}), "a pausa é da execução: a próxima começa a contar do zero")
        pausas3 = {"velha": {"retomada": agora - 3 * 3600}}
        dr.destravar([], {}, lambda cid: None, agora, "running", "error", lambda cid: True, pausas3)
        ok(pausas3 == {}, "registro velho some")

    def t_aba_em_uso_pela_tela_nao_fecha(self):
        # 16/10: the cleanup closed the tab of a chat that looked idle while the operator was creating an app through
        # the live view (navegador_visual marks navegador_em_uso_ate)
        m = _carregar("limpeza_aba_em_uso", RAIZ / "extensions" / "python" / "job_loop" / "_40_limpar_navegador.py")

        class Ctx:
            def __init__(self, dados):
                self.dados, self.task = dados, None
                self.last_message = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)

            def get_data(self, k):
                return self.dados.get(k)

        ctxs = {"usada": Ctx({"navegador_em_uso_ate": time.time() + 600}), "parada": Ctx({}),
                "vencida": Ctx({"navegador_em_uso_ate": time.time() - 1})}
        ok([c for c, _ in m.escolher(ctxs, 99999)] == ["parada", "vencida"], "a aba em uso pela tela fica aberta")

    def t_time_travel_sem_pastas_pesadas_e_sem_trava_velha(self):
        import importlib.util as iu
        import types as tp
        stubs = {"helpers": tp.ModuleType("helpers"), "helpers.extension": tp.ModuleType("helpers.extension")}
        stubs["helpers.extension"].Extension = object
        antes = {k: sys.modules.get(k) for k in stubs}
        sys.modules.update(stubs)
        try:
            spec = iu.spec_from_file_location("limpeza_tt_teste", RAIZ / "extensions" / "python" / "job_loop" /
                                              "_44_time_travel_leve.py")
            m = iu.module_from_spec(spec)
            spec.loader.exec_module(m)
        finally:
            for k, v in antes.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v
        tt = tp.SimpleNamespace(EXCLUDED_DIR_NAMES={".git", "node_modules"}, EXCLUDED_DIR_PATTERNS={"*.egg-info"})
        ok(m.aplicar(tt) > 0 and "agentes" in tt.EXCLUDED_DIR_NAMES, "a pasta das instalações do Hermes/OpenClaw sai")
        import fnmatch
        for nome in ("aibusiness", "agentepessoal-wt-correcoes", "erp-saas-video-ifood"):
            ok(any(fnmatch.fnmatch(nome, p) for p in tt.EXCLUDED_DIR_PATTERNS), f"{nome}: cópia de repositório sai")
        ok(not any(fnmatch.fnmatch("pesquisas", p) for p in tt.EXCLUDED_DIR_PATTERNS) and
           "pesquisas" not in tt.EXCLUDED_DIR_NAMES, "o resto da pasta de trabalho continua com histórico")
        ok(m.aplicar(tt) == 0, "aplicar de novo não muda nada")
        import tempfile
        raiz = Path(tempfile.mkdtemp(prefix="limpeza-tt-"))
        velho, novo = raiz / "a" / "repo.git" / "index.lock", raiz / "b" / "repo.git" / "index.lock"
        for f in (velho, novo):
            f.parent.mkdir(parents=True)
            f.write_text("")
        agora = time.time()
        os.utime(velho, (agora - 3600, agora - 3600))
        ok(m.destravar(raiz, agora, git_rodando=lambda: True) == [], "git escrevendo agora: nenhuma trava sai")
        ok(m.destravar(raiz, agora, git_rodando=lambda: False) == [str(velho)], "só a trava velha sai")
        ok(novo.exists(), "a recente fica (pode ser de um git em andamento)")

    def t_intervalo_vale_mesmo_recarregando_o_modulo(self):
        # 12/10 review: job-loop extensions are loaded again on every pass, so the "every 10 minutes" kept in a module
        # variable ran every minute; the time now lives in a marker file
        import shutil
        import tempfile

        tmp = Path(tempfile.mkdtemp(prefix="limpeza-marca-"))
        try:
            for arquivo in ("_40_limpar_navegador.py", "_41_destravar_rotinas.py"):
                caminho = RAIZ / "extensions" / "python" / "job_loop" / arquivo
                m1 = _carregar("limpeza_marca_1", caminho)
                marca = tmp / arquivo
                ok(m1._na_hora(marca, m1.INTERVALO), f"{arquivo}: a primeira volta roda")
                m2 = _carregar("limpeza_marca_2", caminho)  # the next pass: a fresh module
                ok(not m2._na_hora(marca, m2.INTERVALO), f"{arquivo}: a volta seguinte, com o módulo recarregado, não roda")
                antes = time.time() - m2.INTERVALO - 1
                os.utime(marca, (antes, antes))
                ok(m2._na_hora(marca, m2.INTERVALO), f"{arquivo}: passado o intervalo, roda de novo")
                ok(not hasattr(m2, "_ultima"), f"{arquivo}: nada de relógio em variável do módulo")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    async def rodar(self, so=""):
        for nome in sorted(n for n in dir(self) if n.startswith("t_") and (not so or so in n)):
            try:
                getattr(self, nome)()
                self.resultados.append({"teste": nome, "ok": True})
            except Exception as exc:
                self.resultados.append({"teste": nome, "ok": False, "erro": f"{type(exc).__name__}: {exc}",
                                        "onde": traceback.format_exc().splitlines()[-3:]})
        return {"passou": sum(r["ok"] for r in self.resultados), "total": len(self.resultados), "resultados": self.resultados}
