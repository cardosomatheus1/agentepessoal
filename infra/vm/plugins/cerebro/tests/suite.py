"""Tests of the Segundo Cérebro's Pasta (20/10): files and frontmatter, nothing deleted, the one-time migration, the
old writers (decisões, fios, ficha) writing into the Pasta, Assuntos, the anotação automática (with a fake model), the
nota do dia, the audit and the tool. Everything in a temporary folder. Run with implantar.py (staging) or anywhere:
python3 tests/suite.py"""

import asyncio
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import time
import traceback
import types
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PLUGINS = RAIZ.parent if (RAIZ.parent / "memoria_pessoal").exists() else Path("/a0/usr/plugins")  # staging copy


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


class Suite:
    def __init__(self):
        self.resultados = []

    # ------------------------------------------------------------ fixture
    def preparar(self, migrar: bool = True):
        self.tmp = Path(tempfile.mkdtemp(prefix="cerebro_teste_"))
        sys.modules.pop("cerebro_modulos", None)
        for k in [k for k in sys.modules if k.startswith(("cerebro_", "memoria_pessoal_", "fios_soltos_helper"))]:
            sys.modules.pop(k, None)
        self.mods = _carregar("cerebro_modulos", RAIZ / "helpers" / "modulos.py")
        sys.modules["cerebro_modulos"] = self.mods
        self.p = self.mods.m("pasta")
        self.p.RAIZ = self.tmp / "pasta"
        self.d, self.f = self.mods.m("decisoes"), self.mods.m("fios")
        self.d.PASTA = self.tmp / "decisoes"
        self.f.PASTA = self.tmp / "fios"
        self.ficha = _carregar("memoria_pessoal_ficha", PLUGINS / "memoria_pessoal" / "helpers" / "ficha.py")
        sys.modules["memoria_pessoal_ficha"] = self.ficha
        self.ficha.PASTA = self.tmp / "usuarios"
        self.a = self.mods.m("assuntos")
        self.antigos = {"decisoes": self.tmp / "antigo" / "decisoes.json", "fios": self.tmp / "antigo" / "fios.json",
                        "ficha": self.tmp / "antigo" / "matheus.md"}
        (self.tmp / "antigo").mkdir()
        agora = time.time()
        self.antigos["decisoes"].write_text(json.dumps({"decisoes": [
            {"id": 1, "tema": "prospeccao.cotas", "tipo": "decisao", "valor": "Prospecção da Raiz com 20 DMs por dia",
             "citacao": "pode mandar 20 por dia", "origem": "conversa x", "por": "agente", "em": agora - 86400 * 3, "estado": "ativa"},
            {"id": 2, "tema": "codigo.modelo", "tipo": "preferencia", "valor": "Usar OpenCode para mexer em código",
             "citacao": "", "origem": "", "por": "agente", "em": agora - 86400, "estado": "ativa"}]}))
        self.antigos["fios"].write_text(json.dumps({"fios": [
            {"id": "aa11bb", "titulo": "Autorizar o Drive para os vídeos", "estado": "aberto", "dono": "você",
             "criado": agora - 86400 * 10, "atualizado": agora - 86400 * 10},
            {"id": "cc22dd", "titulo": "Mandar o cardápio da Raiz ao cliente", "estado": "aberto", "dono": "você",
             "criado": agora - 3600, "atualizado": agora - 3600}], "ruido": ["promo da AWS"]}))
        self.antigos["ficha"].write_text("# Sobre matheus\n\n> Mantida pela ferramenta `ficha` (add, patch, remove)\n\n"
                                         "- Mora em Salvador\n- Fundador da Raiz Connect\n")
        if migrar:
            self.res_migracao = self.mods.m("migracao").migrar("operador: teste", antigos=self.antigos)

    def limpar(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ------------------------------------------------------------ tests
    def t_frontmatter_ida_e_volta_e_ilegivel(self):
        self.preparar(migrar=False)
        try:
            p = self.p
            campos = {"id": 7, "valor": "Texto com \"aspas\" e: dois pontos", "liga": ["a:1"], "status": "x", "tags": ["a"]}
            txt = p.frontmatter(campos)
            eq(p.ler_frontmatter(txt + "# corpo\n"), {"id": 7, "valor": campos["valor"], "liga": ["a:1"]},
               "lê o que escreveu (status/tags são derivados, não voltam)")
            for ruim in ("sem cabeçalho", "---\nid: 7\n", "---\nid 7\n---\n", "---\nid: {quebrado\n---\n"):
                try:
                    p.ler_frontmatter(ruim, "x.md")
                    raise Falha(f"aceitou cabeçalho ruim: {ruim!r}")
                except p.Ilegivel:
                    pass
        finally:
            self.limpar()

    def t_estrutura_do_guia_sem_sobrescrever(self):
        self.preparar(migrar=False)
        try:
            p = self.p
            criados = p.estrutura()
            for pasta_ in p.PASTAS:
                ok((p.RAIZ / pasta_).is_dir(), f"pasta {pasta_}")
            ok((p.RAIZ / "CLAUDE.md").exists() and len((p.RAIZ / "CLAUDE.md").read_text().splitlines()) <= 200,
               "CLAUDE.md curto na raiz")
            eq(sorted(p.contexto_pendente()), sorted(p.CONTEXTO), "os 6 de Contexto começam pendentes")
            (p.RAIZ / "Contexto" / "marca.md").write_text("conteúdo dele")
            p.estrutura()
            eq((p.RAIZ / "Contexto" / "marca.md").read_text(), "conteúdo dele", "estrutura nunca sobrescreve")
            ok("Contexto/organizacao.md" in criados, "lista o que criou")
            try:
                p.gravar_contexto("marca.md", "A marca fala simples, sem jargão, com exemplos de cozinha.", "")
                raise Falha("gravou contexto sem o ok dele")
            except ValueError:
                pass
            onde = p.gravar_contexto("marca.md", "A marca fala simples, sem jargão, com exemplos de cozinha.", "ok, pode gravar")
            eq(onde, "Contexto/marca.md", "grava a seção")
            ok("marca.md" not in p.contexto_pendente(), "seção feita sai das pendentes")
            try:
                p.gravar_contexto("perfil.md", "qualquer coisa longa o bastante aqui", "ok")
                raise Falha("perfil é da ficha")
            except ValueError:
                pass
        finally:
            self.limpar()

    def t_migracao_unica_com_area_e_arquivo_morto(self):
        self.preparar()
        try:
            p, r = self.p, self.res_migracao
            eq((r["decisoes"], r["pendencias"], r["ficha"]), (2, 2, 2), "migrou tudo")
            ok(p.ativa("matheus") and not p.ativa("ilia"), "a Pasta vale só para o dono")
            nomes = sorted(x.name for x in (p.RAIZ / "Decisoes").glob("0*.md"))
            eq(nomes, ["0001-prospeccao-da-raiz-com-20-dms-por-dia.md", "0002-usar-opencode-para-mexer-em-codigo.md"],
               "um arquivo por decisão, nome com número e título")
            dec = {x["id"]: x for x in p.ler("decisoes")}
            eq(dec[1]["area"], "raiz", "área deduzida (prospecção → raiz)")
            eq(dec[2]["area"], "agente", "área deduzida (código → agente)")
            ok((p.RAIZ / "Arquivo-morto" / "registros-antigos" / "decisoes-decisoes.json").exists(), "cópia dos antigos")
            ok(not (self.antigos["decisoes"].stat().st_mode & 0o222), "o antigo fica só para leitura")
            try:
                self.mods.m("migracao").migrar("operador: de novo", antigos=self.antigos)
                raise Falha("migrou duas vezes")
            except RuntimeError:
                pass
            ok("Fundador da Raiz Connect" in (p.RAIZ / "Contexto" / "perfil.md").read_text(), "ficha virou o perfil")
        finally:
            self.limpar()

    def t_escritores_antigos_gravam_na_pasta(self):
        self.preparar()
        try:
            p, d, f, fi = self.p, self.d, self.f, self.ficha
            r = d.registrar("matheus", "raiz.preco-setup", "Cobrar R$ 497 de setup a partir de novembro",
                            citacao="cobra 497 de setup", area="raiz")
            eq(r["id"], 3, "numeração continua")
            ok(any(x.name.startswith("0003-") for x in (p.RAIZ / "Decisoes").glob("*.md")), "decisão nova virou arquivo")
            d.registrar("matheus", "raiz.preco-setup", "Cobrar R$ 597 de setup a partir de dezembro")
            ok((p.RAIZ / "Decisoes" / "0003-cobrar-r-497-de-setup-a-partir-de-novembro.md").exists(),
               "a substituída continua (estado substituida), nada some")
            ok("substituida" in (p.RAIZ / "Decisoes" / "0003-cobrar-r-497-de-setup-a-partir-de-novembro.md").read_text(),
               "estado na nota")
            ok(not (self.tmp / "decisoes" / "matheus.json").exists(), "nada gravado no JSON antigo")
            # a guest keeps the old store
            d.registrar("teste_conv", "x.y", "Algo decidido por um convidado")
            ok((self.tmp / "decisoes" / "teste_conv.json").exists(), "convidado segue no registro antigo")
            f.mesclar("matheus", [{"titulo": "Terminar a tarefa do MEI", "area": "pessoal"}], ["aa11bb"])
            abertas = {x["titulo"] for x in f.abertos("matheus", 50)}
            eq(abertas, {"Terminar a tarefa do MEI", "Mandar o cardápio da Raiz ao cliente"}, "pendências pela Pasta")
            eq(f.carregar("matheus").get("ruido"), ["promo da AWS"], "ruído preservado no .meta")
            fi.adicionar("matheus", "Prefere respostas curtas e em português")
            ok("Prefere respostas curtas" in (p.RAIZ / "Contexto" / "perfil.md").read_text(), "ficha grava no perfil")
            ok((p.RAIZ / "Contexto" / "perfil.md").read_text().startswith("---\n"), "perfil com cabeçalho")
            eq(len(fi.entradas("matheus")), 3, "ficha lê do perfil")
        finally:
            self.limpar()

    def t_nada_se_apaga_e_ilegivel_nao_vira_vazio(self):
        self.preparar()
        try:
            p, f = self.p, self.f
            ruim = p.RAIZ / "Pendencias" / "zz-quebrada.md"
            ruim.write_text("---\nid: {quebrado\n---\n")
            try:
                f.mesclar("matheus", [{"titulo": "qualquer"}])
                raise Falha("gravou com uma pendência ilegível")
            except f.EstadoIlegivel:
                pass
            ruim.unlink()
            dados = f.carregar("matheus")
            dados["fios"] = [x for x in dados["fios"] if x["id"] != "cc22dd"]
            f.salvar("matheus", dados)
            ok(list((p.RAIZ / "Arquivo-morto" / "Pendencias").glob("cc22dd-*.md")), "o que saiu foi para o arquivo morto")
        finally:
            self.limpar()

    def t_id_estranho_vira_nome_seguro(self):
        self.preparar()
        try:
            p, f = self.p, self.f
            ruim = "[novo id] não devolvido"
            f.mesclar("matheus", [{"id": ruim, "titulo": "Restaurar o token da Meta"}])
            nomes = [x.name for x in (p.RAIZ / "Pendencias").glob("*.md")]
            ok(any(n.startswith("novo-id-nao-devolvido-") for n in nomes) and not any("[" in n for n in nomes),
               f"nome seguro: {nomes}")
            ok(p.link(f"pendencia:{ruim}").startswith("[[Pendencias/novo-id-nao-devolvido-"), "link acha a nota")
            r = self.mods.m("auditoria").rodar(p)
            ok(not any(a["checagem"] in ("indices", "orfas") for a in r["achados"]), "índice e órfãs ok")
            # a file saved with the old unsafe name is renamed on the next save
            velho = next((p.RAIZ / "Pendencias").glob("novo-id-*.md"))
            os.replace(velho, p.RAIZ / "Pendencias" / "[novo id] não devolvido-x.md")
            f.mesclar("matheus", [{"id": ruim, "detalhe": "de novo"}])
            ok(not any("[" in x.name for x in (p.RAIZ / "Pendencias").glob("*.md")), "renomeado para o nome seguro")
        finally:
            self.limpar()

    def t_assuntos_onde_parou_e_historico(self):
        self.preparar()
        try:
            a = self.a
            x = a.registrar("Preço do plano da Raiz", onde_parou="três faixas; falta o desconto anual", area="raiz")
            eq(x["efeito"], "nova", "abre")
            y = a.registrar("preço do plano da raiz", onde_parou="decidiu 12% no anual")
            eq((y["efeito"], y["id"]), ("atualizou", x["id"]), "mesmo título atualiza o mesmo assunto")
            z = a.atualizar("plano raiz", estado="encerrado")
            eq(z["estado"], "encerrado", "acha pelo título e encerra")
            eq(len(z["historico"]), 3, "histórico guarda cada passo")
            texto = next((self.p.RAIZ / "Assuntos").glob(f"{x['id']}-*.md")).read_text()
            ok("**Onde parou:** decidiu 12% no anual" in texto and "## Histórico" in texto, "nota legível")
            eq(a.abertos(), [], "encerrado sai dos abertos")
        finally:
            self.limpar()

    def t_captura_anota_liga_e_avisa(self):
        self.preparar()
        try:
            cap = self.mods.m("captura")
            dele = ["decidi abrir o MEI esse mês, mas ainda falta emitir o CNPJ e ver o contador"]
            propostas = cap.interpretar(json.dumps({
                "decisoes": [{"tema": "pessoal.mei", "decisao": "Abrir o MEI este mês", "tipo": "decisao", "area": "pessoal",
                              "citacao": "decidi abrir o MEI esse mês"}],
                "pendencias": [{"titulo": "Emitir o CNPJ do MEI", "area": "pessoal",
                                "citacao": "ainda falta emitir o CNPJ e ver o contador"},
                               {"titulo": "Inventada", "citacao": "isso ele nunca disse em lugar nenhum"}],
                "pendencias_feitas": [{"id": "cc22dd", "citacao": "decidi abrir o MEI esse mês"}],
                "assuntos": [{"titulo": "Abertura do MEI", "onde_parou": "falta CNPJ e contador", "area": "pessoal",
                              "citacao": "falta emitir o CNPJ e ver o contador"}]}))
            r = cap.aplicar(propostas, dele, "conversa t", self.d, self.f, self.a)
            tipos = sorted(t for t, _r, _x in r["feito"])
            eq(tipos, ["assunto", "decisao", "pendencia", "pendencia-feita"], "anotou cada tipo")
            ok(any("sem citação" in x for x in r["descartados"]), "o que ele não disse é descartado")
            dec = next(x for x in self.p.ler("decisoes") if x["tema"] == "pessoal.mei")
            ok(any(l.startswith("pendencia:") for l in dec.get("liga", [])) and any(l.startswith("assunto:") for l in dec["liga"]),
               "decisão ligada à pendência e ao assunto da mesma frase")
            texto = next((self.p.RAIZ / "Decisoes").glob(f"{str(dec['id']).zfill(4)}-*.md")).read_text()
            ok("[[Pendencias/" in texto and "[[Assuntos/" in texto, "ligações viram links na nota")
            linha = cap.aviso(r["feito"])
            ok(linha.startswith("📌 Anotei — ") and "Se não era isso" in linha and linha.count("\n") == 0, linha)
            eq(cap.aviso([]), "", "nada novo, nada enviado")
            ok(cap.interpretar("sem json") is None, "saída ilegível não aplica nada")
        finally:
            self.limpar()

    def t_desfazer_a_ultima_anotacao(self):
        self.preparar()
        try:
            ferr = _carregar("cerebro_tool_teste", RAIZ / "tools" / "cerebro.py", {
                "helpers": types.ModuleType("helpers"), "helpers.tool": types.SimpleNamespace(
                    Tool=type("Tool", (), {}), Response=type("Response", (), {}))})
            d = self.d.registrar("matheus", "raiz.x", "Uma decisão que era só ideia", citacao="era só uma ideia minha")
            cap = self.mods.m("captura")
            self.p.escrever(cap.estado_arquivo(self.p.RAIZ), json.dumps({"chats": {}, "ultimo": [f"decisao:{d['id']}"]}))
            feito = ferr.desfazer(self.mods, "ultimo", "era só ideia")
            eq(feito, [f"decisao:{d['id']}"], "desfez a última")
            ok(all(x["tema"] != "raiz.x" for x in self.d.ativas("matheus")), "não vale mais")
            ok(any(x["tema"] == "raiz.x" for x in self.d.carregar("matheus")["decisoes"]), "mas continua no histórico")
            msg = ferr.executar("consultar", "matheus", texto="cardápio raiz")
            ok("Mandar o cardápio da Raiz" in msg, f"consulta acha na Pasta: {msg}")
            ok("Nada na Pasta" in ferr.executar("consultar", "matheus", texto="zebra voadora"), "o que não tem, diz")
            ok("só do Matheus" in ferr.executar("consultar", "ilia", texto="x"), "convidado não usa a Pasta")
        finally:
            self.limpar()

    def t_nota_do_dia_as_20h_uma_vez(self):
        self.preparar()
        try:
            dia, p = self.mods.m("dia"), self.p
            hoje20 = time.mktime(time.strptime(time.strftime("%Y-%m-%d", p.agora_local()) + " 20:30", "%Y-%m-%d %H:%M"))
            ok(not dia.hora_de_escrever(p, hoje20 - 3 * 3600), "antes das 20h não")
            ok(dia.hora_de_escrever(p, hoje20), "às 20h sim")
            self.d.registrar("matheus", "raiz.y", "Uma decisão de hoje para a nota", agora=hoje20 - 600)
            nota = dia.compor(p, hoje20)
            ok("## Decidido" in nota["texto"] and "## Abertas há mais de 7 dias" in nota["texto"], "seções da nota")
            ok("Autorizar o Drive" not in nota["texto"] or "Abertas há mais de 7 dias" in nota["texto"], "velha listada")
            ok(len(nota["resumo"].splitlines()) <= 3 and nota["resumo"].startswith("🧠 Hoje: 1 decisão"), nota["resumo"])
            enviados = []
            job = _carregar("cerebro_job_teste", RAIZ / "extensions" / "python" / "job_loop" / "_58_cerebro.py",
                            {"helpers": types.ModuleType("helpers"), "helpers.extension": types.SimpleNamespace(
                                Extension=type("Extension", (), {}))})
            sys.modules["cerebro_modulos"] = self.mods
            feito = job.tique(hoje20, enviar=enviados.append)
            ok(any(x.startswith("nota do dia") for x in feito) and len(enviados) == 1, f"escreveu e mandou uma vez {feito}")
            ok("Responda “bora”" in enviados[0], "convida para a entrevista enquanto faltar contexto")
            job.tique(hoje20 + 120, enviar=enviados.append)
            eq(len(enviados), 1, "não repete no mesmo dia")
        finally:
            self.limpar()

    def t_auditoria_da_nota_e_acha_problemas(self):
        self.preparar()
        try:
            aud, p = self.mods.m("auditoria"), self.p
            r1 = aud.rodar(p)
            ok(0 <= r1["nota"] <= 100 and r1["descontos"]["contexto"] > 0, "contexto pendente desconta")
            (p.RAIZ / "Documentos" / "solta.md").write_text("# solta\n\n[[Decisoes/nao-existe]]\n")
            r2 = aud.rodar(p)
            ok(any(a["checagem"] == "links-mortos" for a in r2["achados"]), "acha link morto")
            ok(any(a["checagem"] == "cabecalho" and "solta" in a["arquivo"] for a in r2["achados"]), "acha nota sem cabeçalho")
            ok(r2["nota"] < r1["nota"], "piora a nota")
            g = aud.gravar(p)
            ok(Path(g["arquivo"]).exists() and "**Nota:" in Path(g["arquivo"]).read_text(), "relatório gravado")
        finally:
            self.limpar()

    def t_pedido_ensina_pendencia_com_o_exemplo_dele(self):
        # 20/10: o modelo deixava passar "ainda nao terminei a tarefa do MEI" (o exemplo do próprio Matheus)
        cap = _carregar("cerebro_captura_pedido", RAIZ / "helpers" / "captura.py")
        for termo in ("ainda nao terminei a tarefa do MEI", "Uma frase pode ter decisão E pendência E assunto",
                      "Tarefa que ele pediu ao assistente NÃO é pendência"):
            ok(termo in cap.PEDIDO, f"pedido cita {termo!r}")
        pedido = cap.montar_pedido(["x"], "y", [{"id": "a1", "titulo": "T"}], [], [])
        ok("[a1] T" in pedido and "{" in pedido, "lista as pendências abertas e o formato JSON")

    def t_prompt_e_indice(self):
        ext = (RAIZ / "extensions" / "python" / "system_prompt" / "_27_cerebro.py").read_text(encoding="utf-8")
        for termo in ("anotação automática", "Pendência = o que ELE precisa fazer", "acao=desfazer", "UMA seção"):
            ok(termo in ext, f"regras citam {termo!r}")
        indice = PLUGINS / "prompt_enxuto" / "helpers" / "indice.py"
        if indice.exists():
            ok('"cerebro":' in indice.read_text(encoding="utf-8"), "ferramenta no índice curto")

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
