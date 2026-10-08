# interface_celular

Navegação mais leve no celular, sem mexer nos arquivos do Agent Zero.

| O que | Como |
|---|---|
| Conversa longa abria devagar (a da Meta mandava 13,6 MB e levava ~4 s) | `helpers/aliviar.py`: ao abrir a conversa, os 150 passos mais recentes vão inteiros; passos até o 1.000º vão resumidos; os mais antigos que isso ficam de fora (o Agent Zero também só salva os últimos 1.000). As mensagens do usuário e as respostas do agente vão sempre. Nada muda no servidor. Medido: 1,75 MB, ~1 s. |
| O menu de conversas ficava aberto por cima da conversa escolhida | `webui/interface-celular.js` fecha o menu ao escolher ou criar uma conversa (só no celular). |
| As ferramentas (arquivos, navegador, computador, celular…) flutuavam por cima do texto e deslizavam com o dedo | Ficam escondidas atrás do botão ▦ no topo (`chat-top-end`) e abrem como uma coluna logo abaixo dele, sem a alça de arrastar; fecham ao escolher uma ferramenta ou tocar fora. |
| Quatro botões de rolagem fixos sobre o texto | Fica só "ir para o fim", e só quando a conversa está rolada para cima. |
| Transições e desfoques que pesam no celular; a rolagem de uma lista arrastava a tela de trás | Desligados no celular; `overscroll-behavior: contain`. |
| Interface em inglês | Rótulos principais em português (só textos exatos; o conteúdo da conversa nunca é traduzido). |

As regras de layout valem só até 768 px de largura (o mesmo corte do menu lateral); no computador nada muda além da tradução.

A parte do servidor é aplicada em `startup_migration` e `agent_init`. Um `aliviar.py` atualizado vale a partir da próxima conversa criada (o arquivo é recarregado e substitui a versão anterior), sem reiniciar. Depois de mudar arquivos da interface, rode `/api/cache_reset` (só funciona de dentro do contêiner) e recarregue a página.
