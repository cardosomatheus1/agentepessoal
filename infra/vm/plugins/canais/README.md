# canais

Canais por assunto (22/10, do Claude Duet: "canais separados por tópico, que dividem a mesma memória"). Diga ao agente
"cria um canal para a Raiz" (ferramenta `canal`): nasce uma conversa **# Raiz** com o propósito que você deu, e ela já
chega com 3 sugestões de tarefa que o agente pode fazer ali. "Transforma esta conversa no canal NEXOS" também vale.

- O propósito entra nas instruções daquela conversa a cada mensagem (`extensions/python/system_prompt/_29_canal.py`).
- A memória é a mesma de todas as suas conversas (a sua ficha, decisões e pendências).
- Registro em `/a0/usr/canais/<login>.json` (nome, propósito, conversa); nada é apagado por aqui.
