# Calibração dos agentes

Casos que o Matheus julgou no AR Board (https://claude.ai/artifact/7LFmwYACCRBHspUv9QGwcx) e os critérios que
saem deles, um diretório por agente. Como montar rodadas e ler os vereditos: `.claude/skills/ar-board/SKILL.md`.

- `<agente>/casos.jsonl`: um caso julgado por linha (só acrescenta). Serve de teste: o revisor do agente precisa
  aprovar os "A" e reprovar os "R".
- `<agente>/criterios.md`: regras curtas, cada uma citando os casos que a sustentam.
