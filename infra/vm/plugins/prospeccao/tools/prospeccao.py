"""Tool `prospeccao`: find and score → propose (pre-approved types pass a reviewer, the rest go to the phone) → execute one approved action at a time →
report back; plus stages and numbers."""

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

from helpers.tool import Response, Tool


def _carregar(nome: str, caminho: Path):
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        sys.modules[nome] = modulo
    return sys.modules[nome]


RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())


def _numero(valor, padrao: int) -> int:
    """A count from the model: a list counts its items (12/10: `termos` came as the list of searches and the call
    crashed), a numeric text is read, anything else is the default."""
    if isinstance(valor, (list, tuple)):
        return len(valor) or padrao
    try:
        return int(float(str(valor).strip())) if valor not in (None, "") else padrao
    except ValueError:
        return padrao


def pr():
    return _carregar("prospeccao_helper", RAIZ / "helpers" / "prospeccao.py")


def cartao():
    return _carregar("prospeccao_cartao", RAIZ / "helpers" / "cartao.py")


async def mandar_cartao(login: str, lid: str) -> str:
    """The hot lead's one-page card (12/10 review §7 item 3) to the phone; '' when it went, else why not."""
    import time

    p = pr()
    dados = await asyncio.to_thread(p.cartao_lead, login, lid)
    if not dados:
        return "lead não encontrado"
    c = cartao()
    destino = c.PASTA / f"{dados['handle']}-{time.strftime('%Y%m%d-%H%M%S')}.pdf"
    erro = await asyncio.to_thread(c.gerar_pdf, dados, destino)
    if erro:
        return erro
    c.limpar_antigos(time.time())
    return await asyncio.to_thread(p.enviar, login, "", None, "urgente", ponte(), str(destino),
                                   f"📇 Cartão de {dados['nome']} (@{dados['handle']})")


def fontes():
    return _carregar("prospeccao_fontes", RAIZ / "helpers" / "fontes.py")


def ponte():
    if "whatsapp_ponte" in sys.modules:
        return sys.modules["whatsapp_ponte"]
    caminho = Path("/a0/usr/plugins/whatsapp/helpers/ponte.py")
    return _carregar("whatsapp_ponte", caminho) if caminho.exists() else None


def dono(context) -> str:
    sep = sys.modules.get("login_usuarios_separacao")
    return (sep.dono_contexto(context) if sep else (context.get_data("dono") or "matheus")) or "matheus"


SEM_SCRIPTS = ("Busca e avaliação por script com a nossa conta estão desligadas (protegem a @raiz.connect; só o Matheus "
               "liga, com acao \"scripts_conta\"). ")

COMO_EXECUTAR = {
    "aquecer": "Abra o perfil e leia a bio e os posts; siga (se ainda não segue), veja os stories se houver anel colorido (sem "
               "reagir) e curta 1 post que você leu. Comentário: só se esta ação disser PODE COMENTAR, num post de até 7 dias com "
               "algo ESCRITO para comentar (a descrição automática do Instagram não conta): chame `prospeccao` acao \"comentar\" "
               "(acao_id, texto, base = o trecho copiado entre aspas e a data do post) ANTES do resultado e só publique se vier "
               "COMENTÁRIO APROVADO; depois, \"comentado\". Para comentar, abra o post pelo link dele "
               "(https://www.instagram.com/p/<código>/), clique em \"Adicione um comentário…\", digite com a ação `type`, clique em "
               "\"Publicar\" e confira que o comentário aparece. No resultado: ok=true se SEGUIU, mesmo que o comentário não tenha "
               "saído (diga no detalhe o que saiu e o que não saiu); ok=false só se nem seguir deu certo.",
    "dm_abertura": "Abra o perfil → Mensagem e envie EXATAMENTE este texto (sem mudar nada).",
    "dm_lembrete": "Abra o perfil → Mensagem (abre a conversa que já existe) e envie EXATAMENTE este texto.",
    "seguimento": "Abra o perfil → Mensagem (abre a conversa que já existe) e envie EXATAMENTE este texto.",
    "resposta": "Abra o perfil → Mensagem (abre a conversa; se a pessoa só falou num comentário, abre uma nova) e envie "
                "EXATAMENTE este texto.",
    "parceiro": "Abra o perfil → Mensagem e envie EXATAMENTE este texto.",
}


async def _ler_tokens_da_tela(context_id: str) -> list:
    """Every Meta access token on the open facebook.com tabs (Graph API Explorer / Access Token Tool), read straight
    from the page so the value never goes through the model. The helper asks Meta about each one and keeps the one
    that lasts longest (12/10: "the longest string" picked the short token, not the extended one)."""
    import re as _re
    from plugins._browser.helpers import runtime as modulo

    rt = await modulo.get_runtime(context_id, create=False)
    if rt is None:
        return ""
    abas = (await rt.call("list")).get("browsers") or []
    melhores = []
    js = ("() => { const t = []; document.querySelectorAll('input,textarea').forEach(e => t.push(e.value || '')); "
          "t.push(document.body ? document.body.innerText : ''); return t.join(' '); }")
    for aba in abas:
        if "facebook.com" not in str(aba.get("currentUrl", "")):
            continue
        try:
            res = await rt.call("evaluate", aba["id"], js)
        except Exception:
            continue
        texto = str(res.get("result") if isinstance(res, dict) else res)
        melhores += _re.findall(r"EAA[A-Za-z0-9]{80,}", texto)
    return list(dict.fromkeys(melhores))


class Prospeccao(Tool):
    async def execute(self, **kwargs) -> Response:
        """A state change the rules forbid comes back as a plain refusal (the journal keeps the state honest)."""
        try:
            return await self._executar(**kwargs)
        except pr().TransicaoInvalida as exc:
            return Response(message=f"RECUSADO pela regra de estados: {exc}. Não force: confira com `contexto` ou "
                                    "`eventos` o estado real e siga o fluxo.", break_loop=False)

    async def _executar(self, acao: str = "contexto", leads=None, acoes=None, acao_id: str = "", ok=None, detalhe: str = "",
                        bloqueio=False, lead_id: str = "", etapa: str = "", nota: str = "", texto: str = "", dias: int = 7,
                        conta_ativa: str = "",
                        **kwargs) -> Response:
        p = pr()
        login = dono(self.agent.context)
        acao = str(acao or "contexto").lower()
        acao = {"conferido": "caixa_lida", "conferidos": "estoque_conferido"}.get(acao, acao)  # old names (one letter apart)
        r = lambda m: Response(message=m, break_loop=False)  # noqa: E731

        if acao == "playbook":
            return r((RAIZ / "playbook.md").read_text(encoding="utf-8"))
        if acao == "contexto":
            return r(p.resumo_contexto(login))
        if acao == "registrar":
            out = p.registrar(login, leads if isinstance(leads, list) else json.loads(leads or "[]"))
            return r(json.dumps(out, ensure_ascii=False) + "\nA nota é calculada pela rubrica do playbook a partir das evidências; "
                     "recusado por nota/regra não volta. Se faltou evidência (ex.: ultimo_post), confira no perfil e registre de novo.")
        if acao == "buscar_script":
            if not p.scripts_conta(login):
                return r(SEM_SCRIPTS + "Encha o estoque com `fontes_instagram` (Apify) e `fontes`; se não der, siga com o que há.")
            termos = kwargs.get("termos") or texto
            termos = termos if isinstance(termos, list) else [t.strip() for t in str(termos or "").split(",") if t.strip()]
            if not termos:
                return r("Passe `termos` = lista de buscas (ex.: [\"marmita salvador\", \"marmitaria salvador\", \"marmita fit salvador\"]).")
            pausa = p.api_pausada(login)
            if pausa:
                return r(f"Buscas pelo Instagram paradas até {pausa} (o Instagram limitou as consultas da nossa conta). "
                         "Complete o estoque com `fontes`; não abra perfis um a um.")
            cabem = await asyncio.to_thread(p.reservar_consultas, login, min(len(termos), 3))
            if not cabem:
                return r("Teto de consultas pelo Instagram de hoje atingido. Complete o estoque com `fontes` e pare a busca no Instagram.")
            termos = termos[:cabem]
            return r("Rode este script com `browser` action \"evaluate\" numa aba do instagram.com (logada como @raiz.connect). "
                     "Ele devolve um JSON com os @ achados; passe-o INTEIRO para `prospeccao` acao \"perfis_script\" com "
                     "`achados` = o texto (a ferramenta tira os já conhecidos e rejeitados).\n\n" + p.montar_busca(termos))
        if acao == "avaliar_api":
            aviso_429 = ""
            if "__429__" in str(kwargs.get("achados") or ""):  # the search hit the limit: no more Instagram scripts today
                ate = await asyncio.to_thread(p.limite_consulta, login, "a busca devolveu http 429")
                aviso_429 = (f"\nA busca pelo Instagram devolveu 429: nenhum script pelo Instagram até {ate} (a API oficial "
                             "continua valendo). Responda no fim CONSULTA LIMITADA (429).")
            if kwargs.get("achados"):
                handles = p.novos_handles(login, kwargs["achados"])
            else:
                handles = leads if isinstance(leads, list) else [h.strip() for h in str(leads or texto or "").replace(",", " ").split() if h.strip()]
                handles = p.novos_handles(login, handles)
            if not handles:
                return r("Nenhum @ novo (todos já conhecidos ou rejeitados)." + aviso_429)
            perfis = await asyncio.to_thread(p.descobrir_perfis, login, handles)
            if perfis and perfis[0].get("handle") == "-":
                return r(perfis[0]["erro"] + (". Use perfis_script (navegador) por enquanto." if not aviso_429 else ".") + aviso_429)
            out = p.avaliar_perfis(login, perfis)
            return r(json.dumps(out, ensure_ascii=False) + "\nAvaliados pela API oficial. Criados já estão registrados com nota; "
                     "recusados anotados; \"conta pessoal ou inexistente\" = perfil sem conta comercial (fora do perfil ideal)."
                     + aviso_429)
        if acao == "token_meta":
            tokens = await _ler_tokens_da_tela(self.agent.context.id)
            token = await asyncio.to_thread(p.escolher_token_meta, tokens) if tokens else ""
            if not token:
                return r("Não achei um token (EAA…) em nenhuma aba aberta. Deixe aberta a aba do Explorador da Graph API ou da "
                         "ferramenta de token (depois de \"Estender\") e chame de novo.")
            out = await asyncio.to_thread(p.guardar_token_meta, login, token)
            return r(json.dumps(out, ensure_ascii=False))
        if acao == "perfis_script":
            if "__429__" in str(kwargs.get("achados") or ""):
                ate = await asyncio.to_thread(p.limite_consulta, login, "a busca devolveu http 429")
                return r(f"O Instagram limitou as consultas da nossa conta (429): nenhuma busca ou avaliação pelo Instagram até {ate}. "
                         "Complete o estoque com `fontes`; não abra perfis um a um.")
            if not p.scripts_conta(login):
                return r(SEM_SCRIPTS + "Avalie com `avaliar_api` (API oficial); o que ela não avaliar fica de fora.")
            pausa = p.api_pausada(login)
            if pausa:
                return r(f"Scripts de perfil parados até {pausa} (o Instagram limitou as consultas). Complete o estoque com "
                         "`fontes`; não abra perfis um a um.")
            if kwargs.get("achados"):
                handles = p.novos_handles(login, kwargs["achados"])
                if not handles:
                    return r("Nenhum @ novo nessa busca (todos já conhecidos ou rejeitados). Tente outros termos.")
            else:
                handles = leads if isinstance(leads, list) else [h.strip() for h in str(leads or texto or "").replace(",", " ").split() if h.strip()]
                handles = p.novos_handles(login, handles)
            if not handles:
                return r("Passe `leads` = lista de @ (até 15).")
            cabem = await asyncio.to_thread(p.reservar_consultas, login, min(len(handles), 5))
            if not cabem:
                return r("Teto de consultas pelo Instagram de hoje atingido: pare a avaliação por script. Complete o estoque com `fontes`.")
            lote, fila = handles[:cabem], handles[cabem:]
            return r((f"Novos achados: {len(handles)}. Este script avalia {len(lote)}; depois chame de novo `perfis_script` com `leads` = {fila[:25]} (de 5 em 5). " if fila else "")
                     + "Rode este script com a ferramenta `browser`, action \"evaluate\", numa aba já aberta em https://www.instagram.com/ "
                     "(logada como @raiz.connect). Ele devolve um texto JSON; passe esse texto INTEIRO, sem mudar nada, para "
                     "`prospeccao` acao \"avaliar_perfis\" com `dados` = o texto.\n\n" + p.montar_script(lote))
        if acao == "conferir_estoque":
            # leads found outside Instagram: activity, size and privacy checked before their turn (12/10: 73% of the
            # sheet's visits ended in a discard)
            if p.api_meta_pronta(login) and p.a_conferir(login, 1, "api"):
                perfis = await asyncio.to_thread(p.descobrir_perfis, login, p.a_conferir(login, 25, "api"))
                out = p.conferir_perfis(login, perfis, "api")
                return r(json.dumps(out, ensure_ascii=False) + "\nConferidos pela API oficial (os de conta não comercial ficam para o "
                         "script). Chame `conferir_estoque` de novo se ainda houver.")
            handles = p.a_conferir(login, 5)
            if not handles:
                return r("Nada a conferir no estoque agora.")
            f = fontes()
            if f.apify_pronto(login):  # Apify reads any public profile, without our account
                out = await asyncio.to_thread(f.conferir_apify, login, p, p.a_conferir(login, 25))
                if not out.get("erro"):
                    return r(json.dumps(out, ensure_ascii=False) + "\nConferidos pelo Apify. Chame `conferir_estoque` de novo se ainda houver.")
            if not p.scripts_conta(login):
                return r("Sem Apify ou API para esses perfis agora: a conferência fica para a visita (ANTES DE SEGUIR). Pare esta parte.")
            pausa = p.api_pausada(login)
            if pausa:
                return r(f"Scripts de perfil parados até {pausa} (o Instagram limitou as consultas): pule a conferência.")
            cabem = await asyncio.to_thread(p.reservar_consultas, login, len(handles))
            if not cabem:
                return r("Teto de consultas pelo Instagram de hoje atingido: a visita do aquecimento confere esses perfis.")
            handles = handles[:cabem]
            return r("Rode este script com a ferramenta `browser`, action \"evaluate\", numa aba já aberta em https://www.instagram.com/ "
                     "(logada como @raiz.connect). Ele devolve um texto JSON; passe esse texto INTEIRO, sem mudar nada, para "
                     "`prospeccao` acao \"estoque_conferido\" com `dados` = o texto.\n\n" + p.montar_script(handles))
        if acao == "estoque_conferido":
            out = p.conferir_perfis(login, kwargs.get("dados") or texto)
            if any("429" in e.get("erro", "") for e in out["erros"]):
                return r(json.dumps(out, ensure_ascii=False) + "\nO Instagram limitou as consultas da nossa conta (429): nenhuma "
                         "consulta pelo Instagram até amanhã. Não abra perfis um a um.")
            return r(json.dumps(out, ensure_ascii=False) + "\nDescartados já saíram do estoque; conferidos ficam prontos para a vez deles. "
                     "Chame `conferir_estoque` de novo (no máximo 3 vezes por rodada).")
        if acao == "avaliar_perfis":
            out = p.avaliar_perfis(login, kwargs.get("dados") or texto)
            if any("429" in e.get("erro", "") for e in out["erros"]):
                return r(json.dumps(out, ensure_ascii=False) + "\nO Instagram limitou as consultas da nossa conta (429): nenhuma "
                         "busca ou avaliação pelo Instagram até amanhã. Não abra perfis um a um; complete o estoque com `fontes`.")
            return r(json.dumps(out, ensure_ascii=False) + "\nCriados já estão registrados com nota; recusados já anotados. "
                     "Só os de \"conferir\" precisam de você: abra o perfil, descubra o que falta (cidade/segmento) e use "
                     "`registrar` (copie os dados do item e complete o que faltava) ou `rejeitar`.")
        if acao == "fontes":
            # the stock is split among the sources (12/10): this action refills only the share of the sheet and of the
            # CNPJ catalog that is missing; the Instagram share is the search round's own search on Instagram
            f = fontes()
            limite = max(1, min(40, _numero(kwargs.get("limite"), 20)))
            pf = p.estoque(login)["por_fonte"]
            origens = [o for o in ("planilha", "catalogo") if pf[o]["faltam"]]
            if not origens:
                ig = pf["instagram"]["faltam"]
                return r("A parte da planilha e a do catálogo no estoque estão cheias: não chame `fontes` de novo agora."
                         + (f" Falta a parte do Instagram ({ig}): `fontes_instagram`." if ig else " Estoque cheio."))
            coleta = None
            d = f.carregar(login)
            if "catalogo" in origens and sum(1 for e in d["empresas"].values()
                                             if e["estado"] == "fila" and f.origem_empresa(e) == "catalogo") < limite:
                coleta = await asyncio.to_thread(f.coletar, login, _numero(kwargs.get("paginas"), 4))
            out = await asyncio.to_thread(f.enriquecer, login, p, limite, origens)
            e = p.estoque(login)
            pf = e["por_fonte"]
            falta_fontes = pf["planilha"]["faltam"] or pf["catalogo"]["faltam"]
            return r(json.dumps({"coleta": coleta, **out, "estoque": e}, ensure_ascii=False) +
                     "\nCriados já estão registrados com nota (achados fora do Instagram: a data do último post é conferida na "
                     "visita do aquecimento, quando o comentário também é escrito). Não precisa propor «aquecer»: a execução "
                     "consome o estoque sozinha. "
                     + ("Chame `fontes` de novo para repor a planilha/catálogo." if falta_fontes and not out.get("erro_busca")
                        else "Planilha/catálogo: pare (parte cheia ou buscas do dia esgotadas).")
                     + (f" Instagram: faltam {pf['instagram']['faltam']} — `fontes_instagram`." if pf["instagram"]["faltam"] else ""))
        if acao == "fontes_instagram":
            # the Instagram share of the stock through Apify (12/10 pilot: 20 of 38 profiles fit, ~US$ 0.10)
            f = fontes()
            pf = p.estoque(login)["por_fonte"]["instagram"]
            if not pf["faltam"]:
                return r("A parte do Instagram no estoque está cheia: não chame de novo agora.")
            if not f.apify_pronto(login):
                return r("Sem Apify configurado: " + ("encha a parte do Instagram com a busca no Instagram (skill, seção 5)."
                                                      if p.scripts_conta(login) else "siga com `fontes` e o estoque que há."))
            out = await asyncio.to_thread(f.buscar_instagram, login, p, _numero(kwargs.get("buscas") or kwargs.get("termos"), 3),
                                          _numero(kwargs.get("por_termo"), 20))
            pf = p.estoque(login)["por_fonte"]["instagram"]
            if out.get("erro"):
                return r(f"{out['erro']}. " + (f"Se precisar, use a busca no Instagram (skill, seção 5) para a parte que falta ({pf['faltam']})."
                                                if p.scripts_conta(login) else "Siga com o estoque que há."))
            return r(json.dumps({**out, "parte_instagram": pf}, ensure_ascii=False) + "\nCriados já estão registrados e conferidos "
                     "(último post, seguidores, privado). " + (f"Faltam {pf['faltam']}: chame `fontes_instagram` de novo." if pf["faltam"]
                                                               else "Parte do Instagram cheia: pare."))
        if acao == "importar_lista":
            caminho = Path(str(kwargs.get("arquivo") or texto or ""))
            if not caminho.is_file() or caminho.suffix != ".json":
                return r("Passe `arquivo` = caminho de um .json com a lista de empresas (nome, cidade, uf, segmento, telefone, instagram, site, evidencia, fonte).")
            out = fontes().importar(login, json.loads(caminho.read_text(encoding="utf-8")))
            return r(json.dumps(out, ensure_ascii=False))
        if acao == "eventos":
            evs = p.eventos(login, _numero(kwargs.get("ultimos"), 30))
            if lead_id:
                lead = p._lead(p.carregar(login), lead_id)
                evs = [e for e in evs if lead and e["lead"] == lead["id"]]
            return r("\n".join(f"{e['em']:.0f} {e['acao']} {e['tipo']}: {e['de']} → {e['para']} ({e['por']}) {e['motivo']}" for e in evs)
                     or "Sem eventos.")
        if acao == "apagada":
            a = await asyncio.to_thread(p.marcar_apagada, login, acao_id, detalhe or texto)
            if not a:
                return r("Só uma mensagem EXECUTADA pode ser marcada como apagada (passe acao_id e detalhe).")
            return r(f"Mensagem {acao_id} registrada como apagada: não conta mais como resposta enviada. "
                     "Se for para mandar outra, proponha uma única mensagem nova pelo fluxo normal.")
        if acao == "rejeitar":
            n = await asyncio.to_thread(p.rejeitar, login, leads if isinstance(leads, list) else json.loads(leads or "[]"))
            return r(f"{n} perfis anotados como examinados e fora do perfil (não voltam por 60 dias).")
        if acao == "propor":
            itens = acoes if isinstance(acoes, list) else json.loads(acoes or "[]")
            out = await asyncio.to_thread(p.propor, login, itens)
            if out["propostas"]:
                d = p.carregar(login)
                pid = p.guardar_pacote(login, [a["id"] for a in out["propostas"]])
                cab = (f"🎯 *Prospecção Raiz* — {len(out['propostas'])} para aprovar\n"
                       + ("O revisor não liberou estas sozinho (motivo em cada uma). " if out.get("automaticas") is not None else "")
                       + "Cada uma vem abaixo com ✅ / ✏️ / ❌. Nada sai sem o seu ✅.")
                await asyncio.to_thread(p.enviar, login, cab, [{"id": f"pa:{p._login(login)}:{pid}:todas", "titulo": "✅ Aprovar todas"}], ponte=ponte())
                for a in out["propostas"]:
                    lead = p._lead(d, a["lead_id"])
                    msg = p.mensagem_acao(a, lead) + (f"\n🔍 Revisor: {a['revisao']}" if a.get("revisao") else "")
                    await asyncio.to_thread(p.enviar, login, msg, p.botoes_acao(login, a["id"]), ponte=ponte())
            resumo = {"aprovadas_automaticamente": [f"{a['id']} {a['tipo']}" for a in out.get("automaticas", [])],
                      "enviadas_para_aprovacao": [f"{a['id']} {a['tipo']}: {a.get('revisao', '')}" for a in out["propostas"]],
                      "recusadas": out["recusadas"]}
            return r(json.dumps(resumo, ensure_ascii=False) +
                     ("\nCorrija as recusadas (motivo ao lado) e proponha de novo, ou deixe de fora." if out["recusadas"] else ""))
        if acao == "proxima":
            a, motivo = await asyncio.to_thread(p.proxima, login, conta_ativa, quem=self.agent.context.id)
            if not a:
                p.encerrar_liberacao(self.agent.context)
                return r(p.aviso_sem_acao(motivo))
            if a.get("conferir"):  # handed out before and never reported: it may have gone out
                p.encerrar_liberacao(self.agent.context)
                lead = a["lead"]
                no_direct = a["tipo"] in p.TIPOS_DIRECT
                return r(f"CONFIRA ANTES DE QUALQUER ENVIO: a ação {a['id']} ({a['tipo']}) para @{lead.get('handle', '')} foi "
                         "entregue a uma rodada e ficou sem resultado — pode ter saído. Abra " + lead.get("url", "o perfil")
                         + (f" e a conversa no Direct: a mensagem «{a['texto'][:90]}» está lá?" if no_direct
                            else " e veja se já seguimos (botão «Seguindo») e curtimos.")
                         + " Depois chame `prospeccao` acao \"resultado\" com acao_id, ok=true se saiu (uma vez) ou ok=false se "
                         "não saiu, e detalhe com o que viu. NÃO envie nem refaça nada agora.")
            p.liberar(self.agent.context, a)
            lead = a["lead"]
            conferir = ""
            if a["tipo"] == "aquecer" and lead.get("conferir_atividade"):
                conferir = (f"ANTES DE SEGUIR: este perfil foi achado fora do Instagram (catálogo de CNPJ/buscador). Confira que é "
                            f"mesmo «{lead['nome']}» ({lead['cidade']}), a data do último post (o mais recente entre os 4 primeiros da grade) e o "
                            "número de seguidores. Se for outro negócio, o último post tiver mais de 30 dias, ou tiver menos de 300 ou mais de 50 mil "
                            "seguidores, NÃO siga nem curta: chame `prospeccao` acao \"etapa\" com "
                            f"lead_id \"{lead['id']}\", etapa \"descartado\" e nota (\"parado há N dias\", \"perfil de outro negócio\" ou \"N seguidores\") — isso já encerra "
                            "esta visita (não precisa de \"resultado\"; parado ou fora da faixa volta ao estoque em 60 dias) — e chame \"proxima\" "
                            "de novo: vem o próximo da fila. Se estiver ativo, siga normalmente e diga no detalhe a data do último post.\n")
            elif a["tipo"] == "aquecer" and lead.get("conferir_negocio"):
                conferir = (f"ANTES DE SEGUIR: este perfil veio de fora do Instagram e já foi conferido (ativo, tamanho certo). Só confira "
                            f"que é mesmo «{lead['nome']}» ({lead['cidade']}). Se for outro negócio, NÃO siga: chame `prospeccao` acao "
                            f"\"etapa\" com lead_id \"{lead['id']}\", etapa \"descartado\" e nota \"perfil de outro negócio\" — isso já "
                            "encerra esta visita — e chame \"proxima\" de novo.\n")
            if a["tipo"] == "aquecer":
                conferir += ("COMENTÁRIO JÁ APROVADO: publique EXATAMENTE o texto abaixo no post mais recente.\n" if a.get("texto")
                             else "PODE COMENTAR (lead quente), se houver o que dizer.\n" if p.pode_comentar(lead)
                             else "SEM COMENTÁRIO nesta visita (só lead quente): siga, veja os stories e curta 1 post.\n")
            return r(f"Conta conferida: @{p.conta(login)}. Ação {a['id']} ({a['tipo']}) {'PRÉ-APROVADA (autorização do Matheus, dentro do limite do dia; texto revisado)' if a.get('auto') else 'APROVADA pelo Matheus'} para @{lead['handle']} — {lead['url']}\n"
                     f"{conferir}{COMO_EXECUTAR[a['tipo']]}\nTexto aprovado:\n«{a['texto']}»\n\n"
                     + (("PARA ABRIR A CONVERSA: no perfil, rode com `browser` action \"evaluate\" o script abaixo; ele acha o botão "
                         "Mensagem/Message pelo texto (não clique por referência: a página se redesenha). \"ABRIU\": siga; \"SEM BOTÃO "
                         "MENSAGEM\": recarregue o perfil UMA vez e rode de novo; se repetir, `resultado` ok=false.\n"
                         + p.SCRIPT_ABRIR_CONVERSA + "\n\n") if a["tipo"] in p.TIPOS_DIRECT else "")
                     + (("PARA DIGITAR NO DIRECT (obrigatório, NÃO digite à mão): com a conversa aberta, 1) clique no campo de mensagem, "
                         "2) aperte Control+A e depois Backspace (ações press do browser) para apagar rascunho de tentativa anterior, "
                         "3) rode este script com `browser` action \"evaluate\" — ele confere que o campo está vazio, coloca o texto uma vez "
                         "e espera aparecer. Só aperte Enter/Enviar se ele devolver OK. \"CAMPO NÃO ESTÁ VAZIO\": repita 1–3. "
                         "Depois de enviar, leia a conversa e confira que a mensagem aparece UMA vez.\n" + p.script_digitar(a["texto"]) + "\n\n")
                        if a["tipo"] in p.TIPOS_DIRECT else "")
                     + "Depois chame `prospeccao` acao \"resultado\" com acao_id, ok (true/false) e detalhe (o que viu na tela). "
                     "Se o Instagram mostrar bloqueio/limite/'tente mais tarde'/verificação, PARE e mande bloqueio: true.")
        if acao == "comentar":
            aprovado, motivo = await asyncio.to_thread(p.comentar, login, acao_id, texto, kwargs.get("base") or detalhe)
            if not aprovado:
                if motivo.startswith("REESCREVA"):
                    return r(f"{motivo} Não publique nada até vir COMENTÁRIO APROVADO.")
                return r(f"NÃO COMENTE: {motivo}. Siga sem comentário (se estiver na visita, mande o `resultado` normalmente).")
            a = next(x for x in p.carregar(login)["acoes"] if x["id"] == acao_id)
            p.liberar(self.agent.context, {**a, "auto": True})
            return r(f"COMENTÁRIO APROVADO pelo revisor: publique EXATAMENTE «{texto.strip()}» no post que você leu (o da `base`) de "
                     "@" + (p._lead(p.carregar(login), a["lead_id"]) or {}).get("handle", "") + " (abra o post pelo link, "
                     "campo \"Adicione um comentário…\", Publicar, confira que aparece na lista). Depois chame `prospeccao` acao "
                     "\"comentado\" com acao_id, ok e detalhe.")
        if acao == "comentado":
            ok_bool = str(ok).lower() in ("true", "1", "sim", "ok")
            a = await asyncio.to_thread(p.comentado, login, acao_id, ok_bool, detalhe)
            if not a or a["estado"] != "aprovada":  # catch-up comment: close the window; on a visit it stays until resultado
                p.encerrar_liberacao(self.agent.context)
            return r("Registrado." if a else "Não havia comentário aprovado para essa ação.")
        if acao == "sem_comentario":
            itens = p.sem_comentario(login)
            return r(json.dumps(itens, ensure_ascii=False) if itens else "Nenhum aquecimento recente sem comentário.")
        if acao == "resultado":
            ok_bool = str(ok).lower() in ("true", "1", "sim", "ok")
            bloq = str(bloqueio).lower() in ("true", "1", "sim")
            if bloq and not acao_id:  # a block or verification seen while reading (no action in hand)
                segundo = await asyncio.to_thread(p.pausar_por_bloqueio, login, detalhe)
                await asyncio.to_thread(p.enviar, login, ("⛔ *Prospecção parada até você liberar* (segundo bloqueio em 30 dias)"
                                        if segundo else "⛔ *Prospecção pausada por 48 h*") + "\n\nO Instagram mostrou um bloqueio ou "
                                        "pediu verificação: " + str(detalhe or "")[:300] + "\nNada mais sai até lá.",
                                        tipo="urgente", ponte=ponte())
                return r("Registrado. Prospecção pausada. Termine a rodada.")
            a = await asyncio.to_thread(p.resultado, login, acao_id, ok_bool, detalhe, bloq, quem=self.agent.context.id)
            p.encerrar_liberacao(self.agent.context)
            if not a:
                x = next((y for y in p.carregar(login)["acoes"] if y["id"] == acao_id), None)
                if x and x["estado"] in ("aprovada", "incerta"):
                    return r("Essa ação está com outra rodada: não registre nada por ela. Chame `prospeccao` acao \"proxima\".")
                if x and x["estado"] in ("cancelada", "falhou", "executada"):
                    return r(f"Essa ação já estava encerrada ({x['estado']}; lead descartado, fechado ou já registrado). "
                             "Nada a fazer: chame `prospeccao` acao \"proxima\" para a seguinte.")
                return r("Ação não encontrada ou não estava aprovada.")
            if bloq:
                segundo = bool(p.carregar(login)["config"].get("bloqueio_matheus"))
                await asyncio.to_thread(p.enviar, login, ("⛔ *Prospecção parada até você liberar* (segundo bloqueio em 30 dias)"
                         if segundo else "⛔ *Prospecção pausada por 48 h*") + "\n\nO Instagram mostrou um bloqueio/limite: "
                         + detalhe[:300] + "\nNada mais sai até lá.", tipo="urgente", ponte=ponte())
                return r("Registrado. Prospecção pausada. Termine a rodada.")
            if a["tipo"] == "resposta" and a.get("auto") and a["estado"] == "executada":
                lead = p._lead(p.carregar(login), a["lead_id"]) or {}
                await asyncio.to_thread(p.enviar, login, f"↩️ Respondi *{lead.get('nome', '')}* (@{lead.get('handle', '')}) pela @raiz.connect\n\n«{a['texto'][:600]}»",
                         ponte=ponte())  # replies leave without his ✅ (11/10): he hears what went out
            return r(f"Registrado: {a['estado']}. Chame `prospeccao` acao \"proxima\" de novo para a seguinte.")
        if acao == "etapa":
            onde = str(kwargs.get("onde") or "direct").lower()
            negocio = str(kwargs.get("negocio") or "").lower() in ("true", "1", "sim")
            if etapa == "interagiu" or (etapa == "respondeu" and onde == "comentario" and not negocio):
                lead = await asyncio.to_thread(p.interacao_comentario, login, lead_id, nota)
                if not lead:
                    return r("Lead não encontrado (use o @, a URL ou o id).")
                return r(f"@{lead['handle']}: registrado como INTERAÇÃO (respondeu ao nosso comentário sem falar de preço, custo "
                         "ou do sistema). Não proponha resposta no Direct: a pessoa vai primeiro na fila da 1ª mensagem, que "
                         "pode citar essa troca. Se ela falou de preço/custo/lucro ou pediu para conversar, chame de novo com "
                         "negocio: true.")
            lead = await asyncio.to_thread(p.mudar_etapa, login, lead_id, etapa, nota, onde)
            if not lead:
                return r(f"Lead ou etapa inválidos (etapas: {', '.join(p.ETAPAS)}).")
            if not lead["novidade"]:
                return r(f"Essa resposta de @{lead['handle']} já estava registrada (o Matheus já foi avisado). Siga.")
            if etapa in ("respondeu", "lead", "demo") and p.avisar_agora(etapa, nota):  # the rest goes to the 20h17 summary
                emoji, frase = {"respondeu": ("💬", "respondeu"), "lead": ("🔥", "virou lead (quer a calculadora / quer conversar)"),
                                "demo": ("📅", "topou conversar")}[etapa]
                lugar = "num comentário" if onde == "comentario" else "no Direct"
                await asyncio.to_thread(p.enviar, login, f"{emoji} *{lead['nome']}* (@{lead['handle']}) {frase} {lugar}\n\n«{nota[:500]}»\n\n"
                         "Vou responder pela @raiz.connect (o revisor confere o texto antes) e te aviso do que saiu. Se preferir "
                         "conversar você mesmo, toque em 🙋 Deixa comigo.\n" + lead["url"], p.botao_assumir(login, lead["id"]),
                         tipo="urgente", ponte=ponte())  # someone answered: tell him now (Telegram), even in quiet hours
            if etapa in ("lead", "demo"):  # hot: the one-page card follows the notice
                erro = await mandar_cartao(login, lead["id"])
                if erro:
                    print(f"prospeccao: cartão de @{lead['handle']} não saiu: {erro}", flush=True)
            return r(f"@{lead['handle']} agora está em {etapa}.")
        if acao == "entrou":  # someone outside the registry wrote to @raiz.connect (blind review 4, item 3)
            handle, fala = str(kwargs.get("handle") or lead_id or ""), str(nota or texto or "")
            negocio = str(kwargs.get("negocio") or "").lower() in ("true", "1", "sim")
            if not handle or not fala:
                return r("Passe `handle` (o @) e `nota` (o que a pessoa escreveu).")
            if not negocio:
                novo = await asyncio.to_thread(p.entrou_aviso, login, handle, fala)
                if novo:
                    await asyncio.to_thread(p.enviar, login, f"📩 @{p.normalizar(handle)} (fora da lista da prospecção) escreveu para a "
                                            f"@raiz.connect:\n\n«{fala[:500]}»\n\nNão respondi: é com você.", tipo="urgente", ponte=ponte())
                return r("Matheus avisado. Não responda." if novo else "Já avisado antes. Não responda.")
            out = await asyncio.to_thread(p.registrar_entrada, login, handle, fala)
            if out.get("erro"):
                return r(out["erro"])
            if out.get("existia"):
                return r("Esse @ já está no registro: use `etapa` com o lead_id " + out["lead_id"] + ".")
            lead = await asyncio.to_thread(p.mudar_etapa, login, out["lead_id"], "respondeu", fala, "direct")
            if lead and lead.get("novidade"):
                await asyncio.to_thread(p.enviar, login, f"💬 @{lead['handle']} escreveu para a @raiz.connect (chegou sozinho)\n\n"
                                        f"«{fala[:500]}»\n\nVou responder pela @raiz.connect (o revisor confere o texto antes) e te "
                                        "aviso do que saiu. Se preferir conversar você mesmo, toque em 🙋 Deixa comigo.\n" + lead["url"],
                                        p.botao_assumir(login, lead["id"]), tipo="urgente", ponte=ponte())
            return r(f"Registrado como lead de entrada ({out['lead_id']}), etapa respondeu. Proponha a `resposta` pelo playbook "
                     "(Respostas; pode dizer quem fala). Se a fala pede outra etapa (lead, demo), chame `etapa` em seguida.")
        if acao == "cartao":  # "me manda o cartão do @x"
            erro = await mandar_cartao(login, lead_id)
            return r(f"Não consegui mandar o cartão: {erro}" if erro else "Cartão enviado ao celular do Matheus.")
        if acao == "limite_consulta":  # the round saw "http 429" (or "try again later") on a query
            ate = await asyncio.to_thread(p.limite_consulta, login, detalhe or texto)
            return r(f"Registrado: nenhuma busca, avaliação ou conferência pelo Instagram até {ate}. Não abra perfis um a um "
                     "para compensar; termine a rodada com o que não usa o Instagram e escreva no fim "
                     "\"CONSULTA LIMITADA (429)\".")
        if acao == "liberar_bloqueio":  # only on the person's order, after a second block in 30 days
            await asyncio.to_thread(p.liberar_bloqueio, login)
            return r("Prospecção liberada: volta pela metade do ritmo por 7 dias.")
        if acao == "liberar_consultas":  # the person decides to allow the profile scripts again
            await asyncio.to_thread(p.liberar_consultas, login)
            return r("Consultas pelo Instagram liberadas de novo.")
        if acao == "variante":  # A/B decided with the numbers, after the person agrees ("" = alternate again)
            v = await asyncio.to_thread(p.definir_variante, login, texto)
            return r(f"Primeira mensagem: só a variante {v} daqui em diante." if v else "Primeira mensagem: alternando A e B de novo.")
        if acao in ("assumir", "devolver"):  # he talks to this @ himself / hands it back to the rounds
            lead = await asyncio.to_thread(p.assumir_lead if acao == "assumir" else p.devolver_lead, login, lead_id)
            if not lead:
                return r("Lead não encontrado (use o @, a URL ou o id).")
            return r(f"@{lead['handle']}: " + ("a automação parou; é o Matheus quem conversa." if acao == "assumir"
                                               else "devolvido; as rodadas podem voltar a propor para esse perfil."))
        if acao == "editar":
            a, motivo = await asyncio.to_thread(p.editar, login, acao_id, texto)
            if not a:
                return r(f"Não editado: {motivo}")
            d = p.carregar(login)
            await asyncio.to_thread(p.enviar, login, "✏️ Versão nova para aprovar:\n\n" + p.mensagem_acao(a, p._lead(d, a["lead_id"])),
                     p.botoes_acao(login, a["id"]), ponte=ponte())
            return r("Nova versão enviada para aprovação.")
        if acao == "scripts_conta":  # only on the person's order
            ligado = str(texto or "").lower() in ("ligar", "ligado", "true", "1", "sim", "on")
            await asyncio.to_thread(p.definir_scripts_conta, login, ligado)
            return r("Busca e avaliação por script com a @raiz.connect " + ("LIGADAS (teto diário e 429 continuam valendo)." if ligado
                     else "DESLIGADAS: o estoque vem do Apify, da API oficial e das fontes."))
        if acao == "conta":
            erro = p.definir_conta(login, texto or conta_ativa)
            return r(erro or f"Prospecção configurada para @{p.conta(login)}.")
        if acao == "direct_script":
            return r("Abra https://www.instagram.com/direct/inbox/ (`browser` navigate), rode este script com `browser` action "
                     "\"evaluate\" nessa aba e passe o JSON INTEIRO para `prospeccao` acao \"ler_direct\" com `dados` = o texto. A lista "
                     "de conversas não aparece no texto da página (`content`): não conclua \"caixa vazia\" por ele.\n\n" + p.SCRIPT_DIRECT)
        if acao == "ler_direct":
            out = await asyncio.to_thread(p.processar_direct, login, kwargs.get("dados") or texto)
            for n in out["novas"]:
                await asyncio.to_thread(p.enviar, login, f"💬 *{n['nome']}* (@{n['handle']}) respondeu no Direct\n\n«{n['texto'][:500]}»\n\n"
                         "Vou responder pela @raiz.connect (o revisor confere o texto antes) e te aviso do que saiu. Se preferir "
                         "conversar você mesmo, toque em 🙋 Deixa comigo.\n" + n["url"], p.botao_assumir(login, n["lead_id"]), tipo="urgente", ponte=ponte())
            if out["erros"] and not out["conversas"]:
                await asyncio.to_thread(p.registrar_falha, login, "ler_direct: " + "; ".join(out["erros"]))
                return r(f"Não consegui ler o Direct ({'; '.join(out['erros'])}). Abra a caixa pelo print (skill, seção 2) e siga a "
                         "rodada; se nem assim, `caixa_lida` com o que conseguiu ver. Não é motivo para PRECISA DE VOCÊ.")
            resumo = (f"{out['conversas']} conversas lidas na lista; respostas novas de leads: "
                      + (", ".join("@" + n["handle"] for n in out["novas"]) or "nenhuma"))
            if "abrir" not in out:  # the old API shape
                return r(json.dumps(out, ensure_ascii=False) + f"\nUse em `caixa_lida` → direct: \"{resumo}\". Para cada resposta nova, "
                         "proponha a `resposta` pelo playbook (o revisor confere). O Matheus JÁ foi avisado; chame `etapa` só se a "
                         "fala pede outra etapa (lead, demo, descartado).")
            linhas = [resumo + (" (VARREDURA COMPLETA registrada: a lista mostra a última mensagem de cada conversa)" if out["varredura"] else "")]
            for n in out["novas"]:
                linhas.append(f"- RESPOSTA de @{n['handle']} («{n['texto'][:120]}»): o Matheus JÁ foi avisado. Abra a conversa clicando em "
                              f"«{n['nome_na_caixa'][:50]}» na lista, leia tudo e proponha a `resposta` pelo playbook; `etapa` só se a fala "
                              "pede outra (lead, demo, descartado).")
            for a in out["abrir"]:
                linhas.append(f"- ABRA «{a['nome_na_caixa'][:50]}» ({a['pasta']}, {a['quando']}: «{a['previa'][:100]}»): {a['por_que']}.")
            if out["nao_achadas"]:
                linhas.append("- Não estão na lista (abra pelo perfil → Mensagem; se não abrir, `falha` e siga): "
                              + ", ".join("@" + x["handle"] for x in out["nao_achadas"]))
            if out["robos"]:
                linhas.append("- Resposta automática (não é resposta; nada a fazer): " + ", ".join(x[:40] for x in out["robos"]))
            linhas.append(f"Depois, `caixa_lida` com direct: \"{resumo}\"" + (", varredura: true" if out["varredura"] else "")
                          + " e as notificações.")
            return r("\n".join(linhas))
        if acao == "falha":
            await asyncio.to_thread(p.registrar_falha, login, str(texto or kwargs.get("nota") or ""))
            return r("Registrado para o operador (não vai ao Matheus). Siga a rodada; se não há mais nada a fazer, a resposta "
                     "final é SEM NOVIDADE.")
        if acao == "caixa_lida":
            inter = kwargs.get("interagiram") or []
            inter = inter if isinstance(inter, list) else [h.strip() for h in str(inter).split(",") if h.strip()]
            varredura = str(kwargs.get("varredura") or "").lower() in ("true", "1", "sim")
            erro = await asyncio.to_thread(p.conferido, login, str(kwargs.get("direct") or ""), str(kwargs.get("notificacoes") or ""),
                                           inter, varredura)
            return r(erro or "Leitura registrada. Agora chame `prospeccao` acao \"proxima\".")
        if acao == "hoje":
            texto_dia = p.resumo_hoje(login)
            return r(texto_dia or "NADA HOJE")
        if acao == "auto":
            ligado = str(texto or "").lower() not in ("false", "0", "nao", "não", "off", "desligar")
            p.definir_auto(login, ligado)
            return r("Aprovação automática " + ("LIGADA" if ligado else "DESLIGADA") + " (aquecer, primeira mensagem e lembrete).")
        if acao == "metricas":
            return r(json.dumps(p.metricas(login, _numero(dias, 7)), ensure_ascii=False))
        return r("acao: playbook | contexto | registrar | rejeitar | propor | comentar | comentado | proxima | resultado | etapa | "
                 "caixa_lida | direct_script | ler_direct | falha | fontes | fontes_instagram | conferir_estoque | estoque_conferido | buscar_script | avaliar_api | "
                 "perfis_script | avaliar_perfis | limite_consulta | liberar_consultas | cartao | assumir | devolver | editar | "
                 "apagada | importar_lista | variante | token_meta | hoje | metricas")
