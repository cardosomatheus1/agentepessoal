"""Narration voice: Carolina (Amazon Nova 2 Sonic) by default, and a reading that is not the exact text is redone.
No network: the Sonic call is replaced by a fake. A live reading runs in testar.py (narrated templates)."""
import json, subprocess, sys, tempfile, glob
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render  # noqa: E402
from render import VOZ_PADRAO, mesma_fala, narrar_sonic  # noqa: E402

ok = falhou = 0


def caso(nome, cond):
    global ok, falhou
    if cond: ok += 1
    else: falhou += 1; print("FALHOU:", nome)


caso("padrão é a Carolina do Nova 2 Sonic (pedido do Matheus, 14/10)", VOZ_PADRAO == {"id": "carolina", "motor": "nova-sonic"})
marcas = sorted(glob.glob(str(Path(__file__).resolve().parent.parent / "marcas" / "*" / "marca.json")))
fora = [Path(m).parent.name for m in marcas if (json.loads(Path(m).read_text()).get("voz") or VOZ_PADRAO) != VOZ_PADRAO]
caso(f"toda marca narra com a Carolina (fora: {fora})", marcas and not fora)

caso("mesma fala, pontuação e caixa diferentes", mesma_fala("Investe em anúncio? O NEXOS mostra.", "investe em anúncio  o nexos mostra"))
caso("palavra a mais reprova", not mesma_fala("Agende sua demonstração.", "Claro! Agende sua demonstração."))
caso("palavra trocada reprova", not mesma_fala("Faltam 17 dias.", "Faltam 7 dias."))
caso("palavra a menos reprova", not mesma_fala("Sete dias depois, o resultado volta.", "Sete dias depois o resultado"))
caso("dinheiro e porcentagem contam", not mesma_fala("R$ 31,08 e 20%", "R$ 31,08 e 2%"))
caso("transcrição vazia reprova", not mesma_fala("Oi.", ""))


class Falso:
    """Stands in for subprocess.run: the node call answers with the queued transcripts; ffmpeg copies the file."""
    def __init__(self, transcricoes):
        self.transcricoes, self.chamadas = list(transcricoes), 0

    def __call__(self, cmd, **kw):
        if cmd[0] == "node":
            self.chamadas += 1
            Path(cmd[2]).write_bytes(b"RIFF")
            t = self.transcricoes.pop(0)
            if t is None:
                return subprocess.CompletedProcess(cmd, 1, "", "ValidationException: tempo esgotado")
            return subprocess.CompletedProcess(cmd, 0, json.dumps({"segundos": 1.0, "transcricao": t}) + "\n", "")
        Path(cmd[-1]).write_bytes(Path(cmd[cmd.index("-i") + 1]).read_bytes())
        return subprocess.CompletedProcess(cmd, 0, "", "")


with tempfile.TemporaryDirectory() as d:
    destino = Path(d) / "f.wav"
    f = Falso(["Olá! Chegou o NEXOS.", "Chegou o NEXOS."])
    narrar_sonic("Chegou o NEXOS.", "carolina", destino, rodar=f)
    caso("leitura com palavra a mais é refeita e a certa é usada", f.chamadas == 2 and destino.exists())
    caso("arquivo bruto apagado depois de usar", not destino.with_suffix(".bruto.wav").exists())

    f = Falso([None, "Chegou o NEXOS."])
    destino.unlink()
    narrar_sonic("Chegou o NEXOS.", "carolina", destino, rodar=f)
    caso("erro do Bedrock numa tentativa: tenta de novo", f.chamadas == 2 and destino.exists())

    f = Falso(["Oi.", "Oi.", "Oi."])
    try:
        narrar_sonic("Chegou o NEXOS.", "carolina", Path(d) / "g.wav", rodar=f); caso("três leituras erradas falham", False)
    except RuntimeError as e:
        caso("três leituras erradas falham, nunca usam a errada", "3 tentativas" in str(e) and not (Path(d) / "g.wav").exists())

print(f"voz: {ok} ok, {falhou} falharam")
sys.exit(1 if falhou else 0)
