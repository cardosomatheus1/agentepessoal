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
        if antigo is not None and hasattr(antigo, "PENDENTES"):
            modulo.PENDENTES = antigo.PENDENTES
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
        print(f"aprovacoes: {tool_name} -> {analise['categoria']}/{decisao}: {analise['resumo']}", flush=True)
        if decisao == "permitir":
            return

        ctx = agent.context
        if decisao == "nunca":
            self._registrar(agent, f"⛔ Bloqueado pela sua regra ({analise['categoria']}): {analise['resumo']}")
            self._devolver(agent, f"[Regra do usuário] A ação «{analise['resumo']}» é da categoria "
                                  f"«{analise['categoria']}», que o usuário marcou como NUNCA. Ela não foi executada. "
                                  "Não tente de novo nem por outro caminho; siga sem ela ou explique ao usuário o que falta.")

        pendente = rv.abrir(ctx.id, analise, tool_name)
        texto = f"🔐 *Aprovação necessária* — {ctx.name or 'conversa'}\n\n{pendente['resumo']}\n_(categoria: {analise['categoria']})_"
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
