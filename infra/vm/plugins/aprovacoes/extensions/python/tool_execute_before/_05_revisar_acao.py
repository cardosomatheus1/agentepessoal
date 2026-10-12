"""Gate before risky actions: classify, then permit / ask the user / block per their rules.

Asking shows a card with buttons in the chat and, when the person has WhatsApp, a message with
buttons there; typing "aprovar" / "sempre" / "recusar" in the chat also works. Any other message
cancels the action and goes to the agent as usual. While waiting the VM may hibernate; the wait
resumes when it wakes (an answer on WhatsApp wakes it).
"""

import asyncio
import importlib.util
import sys
import time
from pathlib import Path

from helpers.extension import Extension
from helpers.errors import InterventionException

RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())


def _carregar(nome: str, caminho: Path):
    """Load a helper by path, again when the file changed (a deploy), keeping pending state."""
    antigo = sys.modules.get(nome)
    mtime = caminho.stat().st_mtime
    if antigo is None or getattr(antigo, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        modulo._mtime = mtime
        for estado in ("PENDENTES", "PEDIDOS"):  # waiting approvals / code requests survive
            if antigo is not None and hasattr(antigo, estado):
                setattr(modulo, estado, getattr(antigo, estado))
        sys.modules[nome] = modulo
    return sys.modules[nome]


def revisor():
    return _carregar("aprovacoes_revisor", RAIZ / "helpers" / "revisor.py")


def whatsapp():
    caminho = RAIZ.parent / "whatsapp" / "helpers" / "ponte.py"
    return _carregar("whatsapp_ponte", caminho) if caminho.exists() else None


def _config(agent) -> dict:
    try:
        from helpers import plugins

        return plugins.get_plugin_config("aprovacoes", agent=agent) or {}
    except Exception:
        return {}


CATEGORIA_LEGIVEL = {
    "mensagem_terceiros": "mensagem para outra pessoa", "publicar": "publicação", "apagar": "apagar algo",
    "termos": "aceitar termos", "enviar_analise": "enviar para análise", "contas_reais": "mudar conta real",
    "chaves_acesso": "chave de acesso", "producao": "sistema em produção", "pagamento": "pagamento", "compra": "compra",
    "senha_seguranca": "senha / segurança",
}


class RevisarAcao(Extension):
    async def execute(self, tool_args: dict | None = None, tool_name: str = "", **kwargs):
        agent = self.agent
        if not agent:
            return
        args = dict(tool_args or {})
        tool = getattr(agent.loop_data, "current_tool", None)
        intencao = str(getattr(tool, "message", "") or "")[-2500:]
        rv = revisor()
        if not rv.precisa_revisao(tool_name, args, intencao):
            return

        cfg = _config(agent)
        try:
            analise = await asyncio.to_thread(rv.classificar, tool_name, args, intencao, str(cfg.get("sempre_permitir") or ""))
            decisao = rv.veredito(cfg.get("regras") or {}, analise)
        except Exception as exc:  # reviewer down: the user decides
            analise = {"categoria": "contas_reais", "sempre_permitida": False,
                       "resumo": f"{tool_name} (o revisor falhou: {str(exc)[:80]})"}
            decisao = "perguntar"
        liberadas = agent.context.get_data("_aprovacoes_liberadas") or {}
        if decisao == "perguntar" and rv.liberacao_vale(analise, tool_name, liberadas,
                                                        agent.context.get_data("_navegador_url") or "", time.time()):
            # the person already approved this exact action (e.g. a prospecting message): asking again would only make
            # them approve twice. Never overrides a "nunca" rule; minutes long; only in the browser on the Instagram.
            decisao = "permitir"
            analise["resumo"] = f"{analise['resumo']} — pré-aprovado: {liberadas.get('motivo', '')}"[:300]
        if decisao == "perguntar" and rv.livre_instagram(analise, tool_name, args, intencao, cfg):
            decisao = "permitir"  # the person said Instagram messages need no approval; he gets told what was done
            analise["resumo"] = f"{analise['resumo']} — Instagram: liberado pelo Matheus"[:300]
            try:  # "pode me avisar que foi feito": every message let through this way is announced on the phone
                wa = whatsapp()
                if wa:
                    await asyncio.to_thread(wa.enviar, wa.dono(agent.context),
                                            f"📣 *Instagram (sem pedir ok)* — {agent.context.name or 'tarefa'}\n\n{analise['resumo']}",
                                            "", "", None, "progresso")
            except Exception as exc:
                print(f"aprovacoes: Instagram notice failed: {exc}", flush=True)
        if decisao == "perguntar" and rv.livre_meta_raiz(analise, tool_name, args, intencao, cfg):
            decisao = "permitir"  # "aprovo tudo lá do Instagram" (12/10): the Meta steps to read the Raiz's Instagram
            analise["resumo"] = f"{analise['resumo']} — Meta/Instagram da Raiz: liberado pelo Matheus"[:300]
            try:
                wa = whatsapp()
                if wa:
                    await asyncio.to_thread(wa.enviar, wa.dono(agent.context),
                                            f"📣 *Meta, Instagram da Raiz (sem pedir ok)* — {agent.context.name or 'tarefa'}\n\n{analise['resumo']}",
                                            "", "", None, "progresso")
            except Exception as exc:
                print(f"aprovacoes: Meta notice failed: {exc}", flush=True)
        if analise["categoria"] != "nenhuma" and agent.context.id in rv.somente_leitura():
            decisao = "nunca"  # read-only chats (daily brief, proactive research) never change anything
        print(f"aprovacoes: {tool_name} -> {analise['categoria']}/{decisao}: {analise['resumo']}", flush=True)
        rv.registrar_atividade(agent.context, tool_name, analise, decisao)
        if decisao == "permitir":
            return

        ctx = agent.context
        if decisao == "nunca":
            self._registrar(agent, f"⛔ Bloqueado pela sua regra ({analise['categoria']}): {analise['resumo']}")
            self._devolver(agent, f"[Regra do usuário] A ação «{analise['resumo']}» é da categoria "
                                  f"«{analise['categoria']}», que o usuário marcou como NUNCA. Ela não foi executada. "
                                  "Não tente de novo nem por outro caminho; siga sem ela ou explique ao usuário o que falta.")

        # Loop guard: the same kind of approval asked over and over (e.g. "send the verification
        # code" retried, each one texting the user) is refused on the 3rd time within 10 minutes.
        import difflib

        agora = time.time()
        historico = [h for h in (ctx.get_data("_aprovacoes_hist") or []) if agora - h[1] < 600]
        parecidos = sum(1 for c, _, r in historico if c == analise["categoria"]
                        and difflib.SequenceMatcher(None, r, analise["resumo"].lower()).ratio() > 0.6)
        historico.append((analise["categoria"], agora, analise["resumo"].lower()))
        ctx.set_data("_aprovacoes_hist", historico)
        if parecidos >= 2:  # 3rd similar request of the same kind (different steps of one task pass)
            self._registrar(agent, f"🔁 Recusado por repetição ({analise['categoria']}, 3ª vez em 10 min): {analise['resumo']}")
            rv.registrar_atividade(ctx, tool_name, analise, "recusado por repetição")
            self._devolver(agent, f"[Proteção contra loop] Você pediu aprovação para «{analise['categoria']}» pela 3ª vez "
                                  "em 10 minutos. A ação NÃO foi executada. Pare agora, não tente de novo e explique ao "
                                  "usuário o que está travando.")

        pendente = rv.abrir(ctx.id, analise, tool_name)
        onde = ctx.name if ctx.name and ctx.name.lower() not in ("conversa", "chat", "nova conversa") else "uma tarefa"
        texto = (f"🔐 *Preciso do seu ok* ({onde})\n\n{pendente['resumo']}\n\n"
                 f"_Tipo: {CATEGORIA_LEGIVEL.get(analise['categoria'], analise['categoria'])}_")
        self._registrar(agent, texto.replace("*", "**", 2) + "\n\nResponda **aprovar**, **sempre** ou **recusar** (ou use os botões).")
        try:  # a failed notice never lets the action through: it still waits for the chat card
            wa = whatsapp()
            if wa:
                botoes = [{"id": f"aprov:{ctx.id}:{pendente['id']}:{d}", "titulo": t}
                          for d, t in (("aprovar", "Aprovar"), ("sempre", "Sempre permitir"), ("recusar", "Recusar"))]
                await asyncio.to_thread(wa.enviar, wa.dono(ctx), texto, "", "", botoes)
        except Exception as exc:
            print(f"aprovacoes: WhatsApp notice failed: {exc}", flush=True)

        limite = time.time() + 60 * float(cfg.get("espera_minutos") or 360)
        escolha = ""
        try:
            while time.time() < limite:
                escolha = pendente["decisao"] or ""
                if escolha:
                    break
                msg = agent.intervention
                if msg is not None:
                    digitada = rv.resposta_digitada(getattr(msg, "message", ""))
                    if not digitada:  # another message: drop the action, the agent reads the message
                        escolha = "outra"
                        break
                    agent.intervention = None
                    escolha = digitada
                    break
                await asyncio.sleep(1)
        finally:
            rv.PENDENTES.pop(ctx.id, None)
        rv.registrar_atividade(ctx, tool_name, analise, f"resposta: {escolha or 'sem resposta'}")

        if escolha in ("aprovar", "sempre"):
            if escolha == "sempre":
                self._lembrar_sempre(agent, cfg, pendente["resumo"])
            self._registrar(agent, f"✅ Aprovado: {pendente['resumo']}")
            return
        if escolha == "outra":
            self._registrar(agent, f"↩️ Ação cancelada (você mandou outra mensagem): {pendente['resumo']}")
            await agent.handle_intervention()  # raises with the person's message
            return
        motivo = "recusou" if escolha == "recusar" else f"não respondeu em {int(float(cfg.get('espera_minutos') or 360))} min"
        self._registrar(agent, f"❌ Não executado (usuário {motivo}): {pendente['resumo']}")
        self._devolver(agent, f"[Usuário] {motivo.capitalize()} a ação «{pendente['resumo']}». Ela NÃO foi executada. "
                              "Não tente de novo nem por outro caminho; siga sem ela ou pergunte o que fazer.")

    @staticmethod
    def _registrar(agent, texto: str) -> None:
        try:
            agent.context.log.log(type="warning", heading="Aprovações", content=texto)
        except Exception:
            pass

    @staticmethod
    def _devolver(agent, texto: str) -> None:
        """Skip the tool: the agent gets the outcome as a message and its loop continues."""
        from agent import UserMessage

        msg = UserMessage(message=texto, attachments=[])
        agent.hist_add_user_message(msg, intervention=True)
        raise InterventionException(msg)

    @staticmethod
    def _lembrar_sempre(agent, cfg: dict, resumo: str) -> None:
        try:
            from helpers import plugins

            novo = dict(cfg)
            linhas = [l for l in str(novo.get("sempre_permitir") or "").splitlines() if l.strip()]
            linhas.append(resumo)
            novo["sempre_permitir"] = "\n".join(linhas[-50:])
            plugins.save_plugin_config("aprovacoes", "", "", novo)
        except Exception as exc:
            print(f"aprovacoes: 'sempre' not saved: {exc}", flush=True)
