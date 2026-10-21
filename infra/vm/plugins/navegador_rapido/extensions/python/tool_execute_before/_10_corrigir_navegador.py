"""Apply the browser fixes once per server (idempotent)."""

import importlib.util
from pathlib import Path

from helpers.extension import Extension


class CorrigirNavegador(Extension):
    async def execute(self, tool_args=None, tool_name: str = "", **kwargs):
        root = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
        spec = importlib.util.spec_from_file_location("navegador_rapido_correcoes", root / "helpers" / "correcoes.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        try:
            args = tool_args  # already unwrapped by controle_agente (_05_desembrulhar)
            module.aplicar()
            if tool_name == "browser":
                module.argumentos_de_upload(args)
                module.argumentos_de_espera(args)
                module.argumentos_de_ref(args)
                module.argumentos_de_teclas(args)
                module.argumentos_de_rolagem(args)
                from plugins._browser.helpers import runtime

                ctx = str(self.agent.context.id)
                module.argumentos_de_dialogo(args, ctx, runtime._BrowserRuntimeCore)
                erros = module.argumentos_de_erros(args, ctx, runtime._BrowserRuntimeCore)
                if isinstance(args, dict) and args.get("selector") and str(args.get("action", "")).lower() in module.COM_SELETOR:
                    from plugins._browser.helpers.selector import get_tool_runtime

                    sessao = await get_tool_runtime(self.agent)
                    erros += await module.resolver_seletor(args, sessao.call)
                if erros:
                    self.agent.set_data("_navegador_erros", erros)
        except Exception as exc:  # never block the agent over this
            print(f"navegador_rapido: {exc}", flush=True)
