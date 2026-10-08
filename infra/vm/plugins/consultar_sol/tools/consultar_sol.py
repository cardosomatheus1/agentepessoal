"""Ask GPT-6.1 Sol for advice from an agent that runs on the cheaper GPT-6 Luna.

Luna does the work; when it is unsure (an ambiguous instruction, an action hard to undo, a
deliverable someone will judge) it sends only the case to Sol: its question and summary, this
chat's contexto.md, the user's last message and up to 8 images. Sol answers with a
recommendation; it never stands in for the user's authorization. Each consultation is a few
thousand tokens on Sol, logged to <chat>/conselhos_sol.md.
"""

import base64
import io
import json
import time
import urllib.request
from pathlib import Path

from helpers.tool import Response, Tool

URL = "http://host.docker.internal:8787/openai/v1/responses"
MODELO = "openai.gpt-6.1-sol"
MAX_IMAGENS = 8
LADO_MAX = 1600
MAX_TEXTO = 12_000  # per text block sent to Sol

INSTRUCOES = """Você é o conselheiro sênior de um agente de IA que trabalha para o usuário (Matheus). O agente roda num modelo mais simples e te consulta quando está em dúvida. Você não vê a conversa: só o caso abaixo.

Responda em português, curto, nesta forma:
1. **Recomendação:** siga / siga com ajuste / pare e pergunte ao usuário — em uma frase.
2. **Por quê:** 2–4 linhas, citando a instrução ou regra do usuário que decide o caso.
3. **Como:** os passos concretos (ou, numa revisão, o que corrigir, em ordem de importância).

Regras:
- Se a instrução do usuário já cobre o caso, diga para seguir — não mande perguntar à toa; perguntas desnecessárias atrasam o trabalho.
- Nunca autorize o que as regras do usuário proíbem ou o que só ele pode decidir: pagamento ou forma de pagamento, aceitar termos legais em nome dele, mexer em contas reais, apagar dados, enviar algo para análise de terceiros sem o ok dele. Nesses casos: "pare e pergunte ao usuário", dizendo exatamente o que perguntar.
- Numa revisão de entrega, avalie como o avaliador final avaliaria: dá para ler? parece real e completo? cumpre o pedido?"""


def _ler(path: Path, limite: int = MAX_TEXTO) -> str:
    try:
        texto = path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return texto if len(texto) <= limite else texto[:limite] + "\n…(truncado)"


def _jpeg_b64(path: Path) -> str | None:
    try:
        from PIL import Image

        img = Image.open(path).convert("RGB")
        img.thumbnail((LADO_MAX, LADO_MAX))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None


def _ultima_mensagem_do_usuario(agent) -> str:
    try:
        for msg in reversed(agent.history.output()):
            content = msg.get("content")
            if msg.get("ai") or not isinstance(content, dict):
                continue
            texto = content.get("user_message")
            if isinstance(texto, str) and texto.strip():
                return texto.strip()[:MAX_TEXTO]
    except Exception:
        pass
    return ""


def _perguntar(texto: str, imagens: list[str]) -> str:
    content = [{"type": "input_text", "text": texto}]
    for b64 in imagens:
        content.append({"type": "input_image", "image_url": f"data:image/jpeg;base64,{b64}", "detail": "high"})
    body = {
        "model": MODELO,
        "reasoning": {"effort": "medium"},
        "instructions": INSTRUCOES,
        "input": [{"role": "user", "content": content}],
    }
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    erro = ""
    for tentativa in range(3):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                data = json.loads(r.read())
            partes = [c.get("text", "") for item in data.get("output", []) if item.get("type") == "message"
                      for c in item.get("content", []) if c.get("type") == "output_text"]
            return "\n".join(partes).strip() or "(o Sol não respondeu)"
        except Exception as exc:
            erro = str(exc)[:200]
            time.sleep(2 * (tentativa + 1))
    return f"(erro ao consultar o Sol: {erro})"


class ConsultarSol(Tool):
    async def execute(self, pergunta: str = "", contexto: str = "", imagens=None, **kwargs) -> Response:
        import asyncio

        if not pergunta.strip():
            return Response(message="Informe a `pergunta` (o que você precisa decidir).", break_loop=False)
        chat_dir = Path("/a0/usr/chats") / self.agent.context.id
        if isinstance(imagens, str):
            imagens = [i.strip() for i in imagens.replace("\n", ",").split(",") if i.strip()]
        caminhos = [Path(str(i)) for i in (imagens or [])][:MAX_IMAGENS]
        codificadas = [b for b in (_jpeg_b64(p) for p in caminhos if p.is_file()) if b]

        partes = [f"## Pergunta do agente\n{pergunta.strip()}", f"## Contexto que o agente resumiu\n{contexto.strip()[:MAX_TEXTO] or '(nenhum)'}"]
        ultima = _ultima_mensagem_do_usuario(self.agent)
        if ultima:
            partes.append(f"## Última mensagem do usuário\n{ultima}")
        memoria = _ler(chat_dir / "contexto.md")
        if memoria:
            partes.append(f"## contexto.md desta conversa (objetivo, decisões, regras)\n{memoria}")
        if caminhos:
            partes.append(f"## Imagens anexadas\n{len(codificadas)} de {len(caminhos)}: " + ", ".join(p.name for p in caminhos))

        await self.set_progress("consultando o Sol…")
        resposta = await asyncio.to_thread(_perguntar, "\n\n".join(partes), codificadas)

        try:
            chat_dir.mkdir(parents=True, exist_ok=True)
            with (chat_dir / "conselhos_sol.md").open("a", encoding="utf-8") as f:
                f.write(f"\n## {time.strftime('%d/%m %H:%M')} — {pergunta.strip()[:200]}\n\n{resposta}\n")
        except OSError:
            pass
        return Response(
            message=f"Conselho do Sol (só aconselha; não substitui a autorização do usuário):\n\n{resposta}",
            break_loop=False,
        )
