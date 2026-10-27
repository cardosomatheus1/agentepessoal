"""The staging copy of a plugin deploy (infra/operador/implantar.py): with the Agent Zero stopped, the throwaway container
of its image gets the A0 code on PYTHONPATH (27/10: /a0 is empty there and a suite importing `helpers` failed).
Run from the repository root: python3 infra/operador/tests/test_implantar_estagio.py"""
import importlib.util
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("implantar_teste", RAIZ / "infra" / "operador" / "implantar.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
falhas = []
if m.ambiente_estagio(True) != "":
    falhas.append("com o A0 no ar, o teste roda dentro dele como antes")
if m.ambiente_estagio(False) != "-e PYTHONPATH=/git/agent-zero ":
    falhas.append("com o A0 parado, o container de teste recebe o código do A0 no PYTHONPATH")
fonte = (RAIZ / "infra" / "operador" / "implantar.py").read_text()
if "docker exec -e ESTAGIO=1 {ambiente_estagio(a0_no_ar)}{alvo}" not in fonte:
    falhas.append("o comando da cópia de teste usa ambiente_estagio")
if "{IMAGEM_A0} 3600" not in fonte or "inspect -f '{{{{.Config.Image}}}}' agent-zero" in fonte:
    falhas.append("a cópia de teste usa a imagem pelo nome (o container agent-zero não existe mais)")
if falhas:
    sys.exit("test_implantar_estagio: " + "; ".join(falhas))
print("test_implantar_estagio: ok")
