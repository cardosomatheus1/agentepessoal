# Login com vários usuários

- Contas em `/a0/usr/usuarios.json` (só hash PBKDF2, fora do git). Criar/trocar senha na VM:
  `sudo python3 /opt/agentepessoal/usuarios.py <login> "<Nome>" '<senha>'` · remover: `--remover <login>`.
- Sessão de 400 dias (navegador e app). Hibernar não desloga; depois de um reinício completo da
  máquina o endereço do agente muda e é preciso entrar de novo uma vez.
- 5 senhas erradas do mesmo IP bloqueiam por 15 minutos.
- Cada pessoa tem a sua ficha `memoria/usuarios/<login>.md`; o agente sabe quem está falando em cada conversa.
- As conversas são compartilhadas: todos os usuários veem todas.
