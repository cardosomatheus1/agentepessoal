"""Tool `prospeccao`: find → propose (the person approves on the phone) → execute one approved action at a time →
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
               "esse texto no post mais recente.",
    "dm_abertura": "Abra o perfil → Mensagem e envie EXATAMENTE este texto (sem mudar nada).",
    "dm_lembrete": "Abra a conversa com esse perfil no Direct e envie EXATAMENTE este texto.",
    "resposta": "Abra a conversa com esse perfil no Direct e envie EXATAMENTE este texto.",
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
            return r(json.dumps(out, ensure_ascii=False))
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
                       "Cada uma vem abaixo com ✅ / ✏️ / ❌. Nada sai sem o seu ✅.")
                p.enviar(login, cab, [{"id": f"pa:{p._login(login)}:{pid}:todas", "titulo": "✅ Aprovar todas"}], ponte=ponte())
                for a in out["propostas"]:
                    lead = p._lead(d, a["lead_id"])
                    p.enviar(login, p.mensagem_acao(a, lead), p.botoes_acao(login, a["id"]), ponte=ponte())
            resumo = {"enviadas_para_aprovacao": [f"{a['id']} {a['tipo']}" for a in out["propostas"]],
                      "recusadas": out["recusadas"]}
            return r(json.dumps(resumo, ensure_ascii=False) +
                     ("\nCorrija as recusadas (motivo ao lado) e proponha de novo, ou deixe de fora." if out["recusadas"] else ""))
        if acao == "proxima":
            a, motivo = p.proxima(login, conta_ativa)
            if not a:
                p.encerrar_liberacao(self.agent.context)
                return r(f"NADA AGORA: {motivo}. Termine a rodada.")
            p.liberar(self.agent.context, a)
            lead = a["lead"]
            return r(f"Conta conferida: @{p.conta(login)}. Ação {a['id']} ({a['tipo']}) APROVADA pelo Matheus para @{lead['handle']} — {lead['url']}\n"
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
            lead = p.mudar_etapa(login, lead_id, etapa, nota)
            if not lead:
                return r(f"Lead ou etapa inválidos (etapas: {', '.join(p.ETAPAS)}).")
            if etapa in ("respondeu", "lead", "demo"):
                emoji = {"respondeu": "💬", "lead": "🔥", "demo": "📅"}[etapa]
                p.enviar(login, f"{emoji} *{lead['nome']}* (@{lead['handle']}) — {etapa}\n\n{nota[:500]}\n{lead['url']}",
                         tipo="urgente" if etapa != "respondeu" else "resposta", ponte=ponte())
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
        if acao == "metricas":
            return r(json.dumps(p.metricas(login, int(dias or 7)), ensure_ascii=False))
        return r("acao: playbook | contexto | registrar | rejeitar | propor | proxima | resultado | etapa | editar | metricas")
