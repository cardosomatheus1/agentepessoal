"""Tool `prospeccao`: find and score → propose (pre-approved types pass a reviewer, the rest go to the phone) → execute one approved action at a time →
report back; plus stages and numbers."""

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


def pr():
    return _carregar("prospeccao_helper", RAIZ / "helpers" / "prospeccao.py")


def ponte():
    if "whatsapp_ponte" in sys.modules:
        return sys.modules["whatsapp_ponte"]
    caminho = Path("/a0/usr/plugins/whatsapp/helpers/ponte.py")
    return _carregar("whatsapp_ponte", caminho) if caminho.exists() else None


def dono(context) -> str:
    sep = sys.modules.get("login_usuarios_separacao")
    return (sep.dono_contexto(context) if sep else (context.get_data("dono") or "matheus")) or "matheus"


COMO_EXECUTAR = {
    "aquecer": "Abra o perfil, siga (se ainda não segue), curta 1 ou 2 posts recentes e, se houver texto, comente EXATAMENTE "
               "esse texto no post mais recente (o primeiro NÃO fixado — posts com alfinete aparecem antes e podem ser antigos; confira a data). Para comentar, abra o post pelo link dele (https://www.instagram.com/p/<código>/ — "
               "pegue o link clicando no post do perfil): nessa página o campo \"Adicione um comentário…\" fica visível embaixo; "
               "clique nele, digite o texto e clique em \"Publicar\"; confira que o comentário aparece na lista. No resultado: ok=true se SEGUIU (o aquecimento valeu), mesmo que o comentário "
               "não tenha saído — diga no detalhe o que saiu e o que não saiu; ok=false só se nem seguir deu certo.",
    "dm_abertura": "Abra o perfil → Mensagem e envie EXATAMENTE este texto (sem mudar nada).",
    "dm_lembrete": "Abra a conversa com esse perfil no Direct e envie EXATAMENTE este texto.",
    "resposta": "Abra a conversa com esse perfil no Direct (se ainda não houver conversa — a pessoa respondeu num "
                "comentário —, abra o perfil → Mensagem) e envie EXATAMENTE este texto.",
    "parceiro": "Abra o perfil → Mensagem e envie EXATAMENTE este texto.",
}


class Prospeccao(Tool):
    async def execute(self, acao: str = "contexto", leads=None, acoes=None, acao_id: str = "", ok=None, detalhe: str = "",
                      bloqueio=False, lead_id: str = "", etapa: str = "", nota: str = "", texto: str = "", dias: int = 7,
                      conta_ativa: str = "",
                      **kwargs) -> Response:
        p = pr()
        login = dono(self.agent.context)
        acao = str(acao or "contexto").lower()
        r = lambda m: Response(message=m, break_loop=False)  # noqa: E731

        if acao == "playbook":
            return r((RAIZ / "playbook.md").read_text(encoding="utf-8"))
        if acao == "contexto":
            return r(p.resumo_contexto(login))
        if acao == "registrar":
            out = p.registrar(login, leads if isinstance(leads, list) else json.loads(leads or "[]"))
            return r(json.dumps(out, ensure_ascii=False) + "\nA nota é calculada pela rubrica do playbook a partir das evidências; "
                     "recusado por nota/regra não volta. Se faltou evidência (ex.: ultimo_post), confira no perfil e registre de novo.")
        if acao == "rejeitar":
            n = p.rejeitar(login, leads if isinstance(leads, list) else json.loads(leads or "[]"))
            return r(f"{n} perfis anotados como examinados e fora do perfil (não voltam por 60 dias).")
        if acao == "propor":
            itens = acoes if isinstance(acoes, list) else json.loads(acoes or "[]")
            out = p.propor(login, itens)
            if out["propostas"]:
                d = p.carregar(login)
                pid = p.guardar_pacote(login, [a["id"] for a in out["propostas"]])
                cab = (f"🎯 *Prospecção Raiz* — {len(out['propostas'])} para aprovar\n"
                       + ("O revisor não liberou estas sozinho (motivo em cada uma). " if out.get("automaticas") is not None else "")
                       + "Cada uma vem abaixo com ✅ / ✏️ / ❌. Nada sai sem o seu ✅.")
                p.enviar(login, cab, [{"id": f"pa:{p._login(login)}:{pid}:todas", "titulo": "✅ Aprovar todas"}], ponte=ponte())
                for a in out["propostas"]:
                    lead = p._lead(d, a["lead_id"])
                    msg = p.mensagem_acao(a, lead) + (f"\n🔍 Revisor: {a['revisao']}" if a.get("revisao") else "")
                    p.enviar(login, msg, p.botoes_acao(login, a["id"]), ponte=ponte())
            resumo = {"aprovadas_automaticamente": [f"{a['id']} {a['tipo']}" for a in out.get("automaticas", [])],
                      "enviadas_para_aprovacao": [f"{a['id']} {a['tipo']}: {a.get('revisao', '')}" for a in out["propostas"]],
                      "recusadas": out["recusadas"]}
            return r(json.dumps(resumo, ensure_ascii=False) +
                     ("\nCorrija as recusadas (motivo ao lado) e proponha de novo, ou deixe de fora." if out["recusadas"] else ""))
        if acao == "proxima":
            a, motivo = p.proxima(login, conta_ativa)
            if not a:
                p.encerrar_liberacao(self.agent.context)
                if "confira as respostas" in motivo:
                    return r(f"AINDA NÃO: {motivo}.")
                return r(f"NADA AGORA: {motivo}. Termine a rodada.")
            p.liberar(self.agent.context, a)
            lead = a["lead"]
            return r(f"Conta conferida: @{p.conta(login)}. Ação {a['id']} ({a['tipo']}) {'PRÉ-APROVADA (autorização do Matheus, dentro do limite do dia; texto revisado)' if a.get('auto') else 'APROVADA pelo Matheus'} para @{lead['handle']} — {lead['url']}\n"
                     f"{COMO_EXECUTAR[a['tipo']]}\nTexto aprovado:\n«{a['texto']}»\n\n"
                     "Depois chame `prospeccao` acao \"resultado\" com acao_id, ok (true/false) e detalhe (o que viu na tela). "
                     "Se o Instagram mostrar bloqueio/limite/'tente mais tarde'/verificação, PARE e mande bloqueio: true.")
        if acao == "resultado":
            ok_bool = str(ok).lower() in ("true", "1", "sim", "ok")
            bloq = str(bloqueio).lower() in ("true", "1", "sim")
            a = p.resultado(login, acao_id, ok_bool, detalhe, bloq)
            p.encerrar_liberacao(self.agent.context)
            if not a:
                return r("Ação não encontrada ou não estava aprovada.")
            if bloq:
                p.enviar(login, "⛔ *Prospecção pausada por 48 h*\n\nO Instagram mostrou um bloqueio/limite: " + detalhe[:300] +
                         "\nNada mais sai até lá.", tipo="urgente", ponte=ponte())
                return r("Registrado. Prospecção pausada por 48 h. Termine a rodada.")
            return r(f"Registrado: {a['estado']}. Chame `prospeccao` acao \"proxima\" de novo para a seguinte.")
        if acao == "etapa":
            onde = str(kwargs.get("onde") or "direct").lower()
            lead = p.mudar_etapa(login, lead_id, etapa, nota, onde)
            if not lead:
                return r(f"Lead ou etapa inválidos (etapas: {', '.join(p.ETAPAS)}).")
            if not lead["novidade"]:
                return r(f"Essa resposta de @{lead['handle']} já estava registrada (o Matheus já foi avisado). Siga.")
            if etapa in ("respondeu", "lead", "demo"):
                emoji, frase = {"respondeu": ("💬", "respondeu"), "lead": ("🔥", "virou lead (quer o cálculo / mandou receita)"),
                                "demo": ("📅", "topou conversar")}[etapa]
                lugar = "num comentário" if onde == "comentario" else "no Direct"
                p.enviar(login, f"{emoji} *{lead['nome']}* (@{lead['handle']}) {frase} {lugar}\n\n«{nota[:500]}»\n\n"
                         "A resposta que eu sugerir chega em seguida para o seu ✅.\n" + lead["url"],
                         tipo="urgente", ponte=ponte())  # someone answered: tell him now (Telegram), even in quiet hours
            return r(f"@{lead['handle']} agora está em {etapa}.")
        if acao == "editar":
            a, motivo = p.editar(login, acao_id, texto)
            if not a:
                return r(f"Não editado: {motivo}")
            d = p.carregar(login)
            p.enviar(login, "✏️ Versão nova para aprovar:\n\n" + p.mensagem_acao(a, p._lead(d, a["lead_id"])),
                     p.botoes_acao(login, a["id"]), ponte=ponte())
            return r("Nova versão enviada para aprovação.")
        if acao == "conta":
            erro = p.definir_conta(login, texto or conta_ativa)
            return r(erro or f"Prospecção configurada para @{p.conta(login)}.")
        if acao == "conferido":
            erro = p.conferido(login, str(kwargs.get("direct") or ""), str(kwargs.get("notificacoes") or ""))
            return r(erro or "Conferência registrada. Agora chame `prospeccao` acao \"proxima\".")
        if acao == "hoje":
            texto_dia = p.resumo_hoje(login)
            return r(texto_dia or "NADA HOJE")
        if acao == "auto":
            ligado = str(texto or "").lower() not in ("false", "0", "nao", "não", "off", "desligar")
            p.definir_auto(login, ligado)
            return r("Aprovação automática " + ("LIGADA" if ligado else "DESLIGADA") + " (aquecer, primeira mensagem e lembrete).")
        if acao == "metricas":
            return r(json.dumps(p.metricas(login, int(dias or 7)), ensure_ascii=False))
        return r("acao: playbook | contexto | registrar | rejeitar | propor | proxima | resultado | etapa | conferido | editar | hoje | auto | metricas")
