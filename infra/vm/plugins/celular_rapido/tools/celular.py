import asyncio
import base64
import importlib.util
import sys
import time
from pathlib import Path

from helpers import chat_media, history
from helpers.tool import Response, Tool

DIRECOES = {  # direction the finger moves
    "cima": (360, 900, 360, 380), "baixo": (360, 380, 360, 900),
    "esquerda": (600, 640, 120, 640), "direita": (120, 640, 600, 640),
}
TECLAS = {"voltar": "back", "inicio": "home", "enter": "enter", "apagar": "delete", "recentes": "recent"}


def _aparelho():
    """Load helpers/aparelho.py once per server (reusing the phone connection); reload if it changed."""
    name = "celular_rapido_aparelho"
    root = next(p for p in Path(__file__).resolve().parents if (p / "plugin.yaml").exists())
    path = root / "helpers" / "aparelho.py"
    mtime = path.stat().st_mtime
    module = sys.modules.get(name)
    if module is None or getattr(module, "_mtime", None) != mtime:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module._mtime = mtime
        sys.modules[name] = module
    return module


class Celular(Tool):
    async def execute(self, acao: str = "ver", acoes: list | None = None, **kwargs) -> Response:
        self._imagem: bytes | None = None
        try:
            if acoes:
                texto = await asyncio.to_thread(self._sequencia, acoes, kwargs)
            else:
                texto = await asyncio.to_thread(self._rodar, str(acao or "ver").strip().lower(), kwargs)
        except Exception as exc:
            texto = f"ERRO no celular: {str(exc)[:500]}"
        return Response(message=texto, break_loop=False)

    def _sequencia(self, acoes: list, geral: dict) -> str:
        """Several actions in one step; only the final screen is returned. Stops at the first problem."""
        feitas = []
        for i, item in enumerate(acoes[:15], 1):
            item = dict(item or {})
            acao = str(item.pop("acao", "ver")).strip().lower()
            ultima = i == len(acoes[:15])
            if ultima and "imagem" in geral and "imagem" not in item:
                item["imagem"] = geral["imagem"]
            if not ultima:
                item["imagem"] = "false"
            try:
                saida = self._rodar(acao, item)
            except Exception as exc:
                feitas.append(f"{i}. {acao}: ERRO {str(exc)[:200]} — parei aqui")
                return "\n".join(feitas) + "\n" + self._rodar("ver", {"imagem": geral.get("imagem", "auto")})
            cabecalho = saida.splitlines()[0]
            problema = "não achei" in saida.split("TELA:")[0]  # "NÃO MUDOU" is reported but not fatal (e.g. home on home)
            feitas.append(f"{i}. {acao}: {cabecalho}")
            if ultima or problema:
                if problema and not ultima:
                    feitas[-1] += " — parei aqui; o resto não foi feito"
                return "\n".join(feitas) + "\n" + saida.split("\n", 1)[1]
        return "\n".join(feitas)

    def _rodar(self, acao: str, a: dict) -> str:
        ap = _aparelho()
        t0 = time.time()

        def passo(d):
            antes = ap.estado(d)
            antes_xml = antes[0]
            nota = self._agir(d, ap, acao, a, antes_xml)
            if acao == "ver" or nota.startswith("não achei"):
                xml, mudou = antes_xml, (None if acao == "ver" else False)
            else:
                xml, mudou = ap.esperar_parar(d, antes, maximo=float(a.get("esperar_max", 2) or 2))
            els = ap.elementos(xml)
            quer = str(a.get("imagem", "auto")).lower()
            com_imagem = quer in ("true", "sim", "1") or (quer == "auto" and sum(1 for e in els if e["rotulo"]) < 4)
            if com_imagem:
                self._imagem = ap.imagem_pequena(d)
            return xml, els, mudou, nota, ap.app_atual(d)

        xml, els, mudou, nota, app = ap.com_retry(passo)
        estado = "" if mudou is None else ("MUDOU" if mudou else "NÃO MUDOU (a ação não teve efeito visível — não repita igual)")
        partes = [f"{estado} · app: {app} · {time.time() - t0:.1f}s".strip(" ·")]
        if nota:
            partes.append(nota)
        partes.append("TELA:\n" + ap.texto_da_tela(els))
        if self._imagem:
            partes.append("[imagem da tela anexada logo abaixo, 360 px de largura = 720 px reais: multiplique as coordenadas da imagem por 2]")
        return "\n".join(partes)

    def _agir(self, d, ap, acao: str, a: dict, xml: str) -> str:
        if acao == "ver":
            return ""
        if acao == "tocar":
            d.click(int(a["x"]), int(a["y"]))
        elif acao == "tocar_longo":
            x, y, ms = int(a["x"]), int(a["y"]), int(float(a.get("segundos", 0.8)) * 1000)
            d.shell(["input", "swipe", str(x), str(y), str(x), str(y), str(ms)])
        elif acao == "tocar_texto":
            alvo = str(a.get("texto", "")).strip().lower()
            achados = [e for e in ap.elementos(xml) if alvo and alvo in e["rotulo"].lower()]
            if not achados:
                return f"não achei '{a.get('texto')}' na tela; nada foi tocado"
            exato = [e for e in achados if e["rotulo"].lower() == alvo]
            e = (exato or achados)[0]
            d.click(*e["centro"])
            return f"toquei em \"{e['rotulo']}\" {e['centro']}"
        elif acao == "deslizar":
            if all(k in a for k in ("x1", "y1", "x2", "y2")):
                pts = tuple(int(a[k]) for k in ("x1", "y1", "x2", "y2"))
            else:
                pts = DIRECOES[str(a.get("direcao", "cima")).lower()]
            ms = int(float(a.get("duracao", 0.15)) * 1000)
            d.shell(["input", "swipe", *map(str, pts), str(ms)])  # d.swipe() takes ~2 s here
        elif acao == "digitar":
            texto = str(a.get("texto", ""))
            campo = d(focused=True)
            if campo.exists:
                campo.set_text((campo.get_text() or "") + texto if a.get("acrescentar") else texto)
            else:
                d.send_keys(texto)
            if a.get("enviar"):
                d.press("enter")
        elif acao in TECLAS or acao == "tecla":
            d.press(TECLAS.get(acao) or str(a.get("tecla", "back")))
        elif acao == "abrir":
            ap.abrir(d, str(a["pacote"]))
        elif acao == "esperar":
            time.sleep(min(float(a.get("segundos", 2)), 30))
        else:
            raise ValueError(f"ação desconhecida: {acao}")
        return ""

    async def after_execution(self, response: Response, **kwargs):
        await super().after_execution(response, **kwargs)
        if not self._imagem:
            return
        saved = chat_media.save_image_base64(
            context_id=self.agent.context.id,
            data=base64.b64encode(self._imagem).decode(),
            mime_type="image/jpeg",
            category="screenshots",
            source="celular",
            preferred_name=f"celular-{int(time.time())}.jpg",
        )
        self.log.update(Screenshot=f"img://{saved.path}&t={time.time()}")
        self.agent.hist_add_message(
            False,
            content=history.RawMessage(
                raw_content=[{"type": "image_url", "image_url": {"url": saved.a0_path}}],
                preview="<tela do celular>",
            ),
            tokens=400,
        )
