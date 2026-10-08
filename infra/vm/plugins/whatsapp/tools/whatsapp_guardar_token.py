"""Save the WhatsApp access token or the app secret shown on the Meta page, without the model
ever reading them.

The tool reads the value (token EAA…, or the 32-hex app secret after "Show" on App settings →
Basic) straight from the chat's browser page and hands it to the host bridge, which stores it in
the SSM SecureString and, with both, trades the 1-hour token for a 60-day one. The answer only
says it was saved.
"""

import json
import re
import urllib.request
from pathlib import Path

from helpers.tool import Response, Tool

JS = r"""(padrao) => {
  const achados = new Set();
  const re = new RegExp(padrao, 'g');
  const olhar = (t) => { for (const m of String(t || '').matchAll(re)) achados.add(m[0]); };
  const varrer = (doc) => {
    doc.querySelectorAll('input, textarea').forEach(el => olhar(el.value));
    olhar(doc.body ? doc.body.innerText : '');
    doc.querySelectorAll('iframe').forEach(f => { try { varrer(f.contentDocument); } catch (e) {} });
  };
  varrer(document);
  return [...achados];
}"""


PADROES = {"token": r"EAA[A-Za-z0-9]{80,}", "app_secret": r"\b[0-9a-f]{32}\b"}


class WhatsappGuardarToken(Tool):
    async def execute(self, campo: str = "token", **kwargs) -> Response:
        from plugins._browser.helpers.runtime import get_runtime

        campo = campo if campo in PADROES else "token"
        rt = await get_runtime(self.agent.context.id, create=False)
        if rt is None:
            return Response(message="O navegador desta conversa não está aberto.", break_loop=False)
        script = JS.replace("(padrao) => {", "() => { const padrao = " + json.dumps(PADROES[campo]) + ";", 1)
        resultado = await rt.call("evaluate", None, script)
        valor = resultado.get("result", resultado.get("value")) if isinstance(resultado, dict) else resultado
        achados = [t for t in (valor or []) if isinstance(t, str)]
        if len(achados) != 1:
            dica = ("clique em 'Gerar token de acesso' na Configuração da API" if campo == "token" else
                    "abra Configurações do app → Básico e clique em 'Mostrar' na Chave Secreta do Aplicativo")
            return Response(message=f"Achei {len(achados)} valores na página (preciso de exatamente 1): {dica} e chame de novo.",
                            break_loop=False)
        req = urllib.request.Request("http://host.docker.internal:8789/configurar",
                                     data=json.dumps({campo: achados[0]}).encode(),
                                     headers={"Content-Type": "application/json",
                                              "X-Chave": Path("/a0/usr/whatsapp/.chave").read_text().strip()})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                aviso = json.loads(r.read()).get("aviso", "")
        except urllib.error.HTTPError as e:
            return Response(message=f"Não guardei: {e.read().decode()[:200]}", break_loop=False)
        nome = "Token do WhatsApp" if campo == "token" else "Chave secreta do app"
        return Response(message=f"{nome} guardado no cofre da AWS{f' ({aviso})' if aviso else ''}. "
                                "Não copie nem repita o valor em lugar nenhum.", break_loop=False)
