"""06/11: no kit da Raiz (body.e-kit) o acento "à mão" dos moldes (classe .mao, Caveat) sai na Manrope da marca.
O Crítico reprovava a letra manuscrita pela identidade e o carrossel do dia caiu 4 vezes seguidas."""
import json
import pathlib
import subprocess
import unittest

AQUI = pathlib.Path(__file__).resolve().parent
JS = r"""
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch(); const pg = await b.newPage(); const out = {};
  for (const c of ['e-kit', 'e-vidro']) {
    await pg.setContent(`<style>${process.argv[process.argv.length - 1]}</style><body class="${c}"><span class="mao" id="m">x</span></body>`);
    out[c] = await pg.$eval('#m', (e) => getComputedStyle(e).fontFamily);
  }
  await b.close(); console.log(JSON.stringify(out));
})();
"""


class KitSemManuscrita(unittest.TestCase):
    def test_kit_troca_a_letra_a_mao_pela_manrope(self):
        css = (AQUI / "motor.css").read_text(encoding="utf-8")
        r = subprocess.run(["node", "-e", JS, "--", css], capture_output=True, text=True, timeout=120, cwd=AQUI)
        fontes = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertTrue(fontes["e-kit"].startswith("M"), fontes)    # Raiz: Manrope
        self.assertTrue(fontes["e-vidro"].startswith("H"), fontes)  # outras marcas mantêm a letra à mão


if __name__ == "__main__":
    unittest.main()
