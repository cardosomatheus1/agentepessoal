"""Runs before Agent Zero's _context_doctor (_10): a reply in Claude's native `<invoke>` format becomes the JSON tool
call Agent Zero reads (helpers/xml_ferramenta.py). Native function calls and valid JSON are left alone; any surprise
leaves the reply as it was."""

import importlib.util
from pathlib import Path

from helpers.extension import Extension

_RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
_spec = importlib.util.spec_from_file_location("prompt_enxuto_carregar", _RAIZ / "helpers" / "carregar.py")
carregar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(carregar)


class XmlParaJson(Extension):
    def execute(self, result_data=None, **kwargs):
        try:
            llm = (result_data or {}).get("llm_result")
            if llm is None or getattr(llm, "function_calls", None):
                return
            resposta = getattr(llm, "response", None)
            if not isinstance(resposta, str) or "invoke" not in resposta:
                return
            from helpers import extract_tools

            if extract_tools.extract_tool_request(resposta.strip()) is not None:
                return
            novo = carregar.modulo("xml_ferramenta").converter(resposta)
            if novo:
                llm.response = novo
                print(f"prompt_enxuto: <invoke> do modelo virou chamada JSON ({novo[:120]})", flush=True)
        except Exception as exc:
            print(f"prompt_enxuto: conversão de <invoke> falhou: {exc}", flush=True)
