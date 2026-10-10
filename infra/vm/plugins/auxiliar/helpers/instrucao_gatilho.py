"""Write the person's "google" trigger instruction from gatilho_google.md (the watcher runs per Google account).

    python3 instrucao_gatilho.py <login> <Nome> [<e-mail Google conectado>]
"""

import sys
from pathlib import Path

modelo = (Path(__file__).resolve().parents[1] / "gatilho_google.md").read_text(encoding="utf-8")
login, nome = sys.argv[1], sys.argv[2]
email = sys.argv[3] if len(sys.argv) > 3 else ""
ler = (f"leia o e-mail inteiro pelo id com o conector `google` (user_google_email = {email})" if email else
       "use o trecho que veio no aviso (o conector Google desta pessoa não está ligado)")
destino = Path(f"/a0/usr/gatilhos/{login}/google.md")
destino.parent.mkdir(parents=True, exist_ok=True)
destino.write_text(modelo.replace("{NOME}", nome).replace("{LER_EMAIL}", ler), encoding="utf-8")
print(destino)
