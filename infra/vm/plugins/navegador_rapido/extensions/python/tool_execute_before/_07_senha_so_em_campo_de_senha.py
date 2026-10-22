"""A vault secret is typed only into a password field (21/10, 99 portal: §§secret(NOVENTAENOVE) went into the manager's
phone field). Runs before the vault (cofre, _08) swaps the name for the value, so it still sees §§secret(NAME)."""

import importlib.util
from pathlib import Path

from helpers.extension import Extension


class SenhaSoEmCampoDeSenha(Extension):
    async def execute(self, tool_args=None, tool_name: str = "", **kwargs):
        if tool_name != "browser" or not isinstance(tool_args, dict):
            return
        root = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
        spec = importlib.util.spec_from_file_location("navegador_rapido_correcoes", root / "helpers" / "correcoes.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if not module.segredos_a_digitar(tool_args):
            return
        module.argumentos_de_ref(tool_args)  # a ref written as "input 21" is read as 21 (the _10 does it again, harmless)
        try:
            module.aplicar()
            from plugins._browser.helpers.selector import get_tool_runtime

            sessao = await get_tool_runtime(self.agent)
            campo = await sessao.call("a0_campo", tool_args.get("browser_id"), tool_args.get("ref"),
                                      tool_args.get("selector") or "")
        except Exception as exc:  # the field could not be read (tab closed, page navigating): the tool decides
            print(f"navegador_rapido: campo do segredo não lido: {exc}", flush=True)
            return
        recusa = module.segredo_no_campo(tool_args, campo)
        if recusa:
            from helpers.errors import RepairableException

            raise RepairableException(recusa)
