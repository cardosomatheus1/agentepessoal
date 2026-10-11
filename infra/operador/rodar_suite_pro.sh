# Roda a suíte da prospecção DENTRO do contêiner do agente (sem login na interface). Uso, na VM:
#   docker cp rodar_suite_pro.sh agent-zero:/tmp/rs.sh && docker exec agent-zero bash /tmp/rs.sh [parte_do_nome]
cd /a0 && /opt/venv-a0/bin/python - "$1" <<'PY'
import asyncio, importlib.util, json, sys
spec = importlib.util.spec_from_file_location("prospeccao_testes", "/a0/usr/plugins/prospeccao/tests/suite.py")
s = importlib.util.module_from_spec(spec); spec.loader.exec_module(s)
d = asyncio.run(s.Suite().rodar(sys.argv[1] if len(sys.argv) > 1 else ""))
for x in d.get("resultados", []):
    if not x["ok"]: print("✗", x["teste"], x.get("erro", "")[:300])
print(f"{d.get('passou')}/{d.get('total')}")
PY
