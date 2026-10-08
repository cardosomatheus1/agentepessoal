"""Drop the empty "[EXTRAS]" block that prepare_prompt still appends after the history.

The extras now live in the history (message_loop_prompts_after/_98_extras_no_historico.py), so the
block Agent Zero adds at the end is always empty. Left there it would end every prompt with text
that the next prompt does not repeat at that position, and the provider cache would miss again.
"""

from helpers.extension import Extension

EMPTY = "[EXTRAS]\n{}"


def _strip(content):
    if isinstance(content, str):
        if content == EMPTY:
            return None
        if content.endswith("\n" + EMPTY):
            return content[: -len(EMPTY) - 1]
        return content
    if isinstance(content, list) and content:
        last = content[-1]
        if isinstance(last, dict) and last.get("type") == "text" and last.get("text") == EMPTY:
            return content[:-1] or None
    return content


class TirarExtrasVazio(Extension):
    def execute(self, data: dict | None = None, **kwargs):
        prompt = (data or {}).get("result")
        if not isinstance(prompt, list) or len(prompt) < 2:
            return
        last = prompt[-1]
        content = _strip(getattr(last, "content", None))
        if content is getattr(last, "content", None):
            return
        if content is None:
            prompt.pop()
        else:
            prompt[-1] = type(last)(content=content)
        # responses_history replays native tool calls and reasoning only when the prompt it is
        # handed matches the text remembered in prepare_prompt: remember the trimmed prompt.
        agent = self.agent
        remembered = getattr(getattr(agent, "loop_data", None), "params_temporary", {}).get("responses_history")
        if isinstance(remembered, dict):
            from langchain_core.prompts import ChatPromptTemplate

            remembered["text"] = ChatPromptTemplate.from_messages(prompt).format()
