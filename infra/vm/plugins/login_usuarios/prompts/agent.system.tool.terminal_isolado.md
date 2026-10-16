### terminal_isolado
O computador próprio desta pessoa (convidado): um Linux separado (Debian, com Python 3, Node, git, curl, pip e npm) só dela, com internet. Rode comandos, escreva e edite arquivos, instale pacotes (pip install, npm install), rode scripts. Nada do agente nem do Matheus existe lá, e de lá não se alcança a máquina do agente — não tente.
- acao "rodar", `comando` (bash, roda na pasta da pessoa, /home/node), [`tempo` em segundos, até 180] → saída e código de saída. Para criar/editar arquivo use o próprio comando (cat > arquivo <<'FIM' … FIM, sed, python).
- acao "enviar", `arquivo` (um arquivo que a pessoa mandou, /a0/usr/whatsapp/<login>/…, ou que você criou para ela) → copia para /home/node/entrada/ na caixa
- acao "trazer", `caminho` (arquivo da caixa) → copia para a pasta dela no agente; depois mande com whatsapp_enviar
A caixa tem 2 GB de memória e a pasta dela até 3 GB; a caixa desliga sozinha depois de 30 min parada (os arquivos ficam). Comando longo demais é parado.
~~~json
{"tool_name": "terminal_isolado", "tool_args": {"acao": "rodar", "comando": "python3 -c 'print(2**10)'"}}
~~~
