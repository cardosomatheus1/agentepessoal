"""A result identical to an earlier one of the same task (512+ characters) goes to the history as "igual ao resultado
do passo N" (helpers/guardas.py; Hermes dedupes byte-identical tool results the same way).

Why here and not in tool_execute_after: this changes only what goes into the history (and the native function-call
output sent to Responses models); the chat window keeps showing the whole result. Only the NEW history item changes,
never an earlier one, so each prompt still starts with the whole previous prompt and the provider cache (cache_prompt)
is not lost. The earlier copy must still be whole in the history (not summarized), or nothing is replaced. Runs before
resultados_grandes (hist_add_tool_result/_50), so a long repeat is not saved to a file again.
"""

import importlib.util
from pathlib import Path

from helpers.extension import Extension

_RAIZ = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
_spec = importlib.util.spec_from_file_location("controle_agente_guardas", _RAIZ / "helpers" / "guardas.py")
guardas = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guardas)

PARAMS = ("tool_name", "tool_result")  # hist_add_tool_result(self, tool_name, tool_result, **kwargs)


class ResultadoRepetido(Extension):
    def execute(self, data: dict | None = None, **kwargs):
        agent = self.agent
        agent_data = getattr(agent, "data", None)
        if not isinstance(data, dict) or not isinstance(agent_data, dict):
            return
        agent_data.pop("_guardas_resultado_pendente", None)
        try:
            args = list(data.get("args") or ())
            kw = data.get("kwargs") if isinstance(data.get("kwargs"), dict) else {}
            valores = dict(zip(PARAMS, args[1:]))
            valores.update({k: kw[k] for k in PARAMS if k in kw})
            tool, texto = str(valores.get("tool_name") or ""), valores.get("tool_result")
            atual = getattr(getattr(agent, "loop_data", None), "current_tool", None)
            if not isinstance(texto, str) or atual is None or getattr(atual, "name", "") != tool:
                return  # only a tool's own result in a step (not a subordinate's answer handed up, etc.)
            resultados = guardas.Resultados(agent_data.setdefault("_guardas_resultados", {}))
            novo, k = resultados.trocar(
                tool, texto, agent_data.get("_detector_loop_args") or {}, int(agent_data.get("_guardas_passos") or 0),
                lambda msg: guardas.visivel_no_historico(agent.history, msg))
            agent_data["_guardas_resultado_pendente"] = k
            if novo is texto:
                return
            if "tool_result" in kw:
                kw["tool_result"] = novo
            else:
                args[2] = novo
                data["args"] = tuple(args)
            for nome in ("_responses_output_item", "responses_item"):
                item = kw.get(nome)
                if isinstance(item, dict) and isinstance(item.get("output"), str):
                    item["output"] = novo
        except Exception as exc:  # never lose a result over this
            print(f"controle_agente: resultado repetido: {exc}", flush=True)
