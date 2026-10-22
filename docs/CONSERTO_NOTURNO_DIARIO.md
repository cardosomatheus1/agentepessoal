# Diário do conserto noturno

Uma linha por noite (docs/CONSERTO_NOTURNO.md, passo 6).

- 21/10 (manual, na sessão do dia): levantamento criado; encontrados e deixados para a 1ª noite: ref escrita "button 22" (25×), key_chord com `key` em vez de `keys` (3×).
- 21/10: sessão fixa criada; clone, leitura das falhas e envio conferidos.
- 22/10: 2 corrigidos e no ar (navegador_rapido @ 5ae54ac, conferido no servidor numa conversa de teste): aba já fechada "Browser N is not open" (6×, 3 conversas; a156a73) e o caso marcado da 99, senha do cofre só em campo de senha (065f6aa, 118c55d, 1ed1fd6). OpenCode 2 + Opus 5.5: aprovado; reprovou 1× (shadow root fechado bloqueava), corrigido. Pulados: laço (37×) e resposta repetida (21×), avisos sem defeito de ferramenta; terminal ainda rodando (10×), dica existe desde 21/10 13:57 e o resto são esperas de propósito; key_chord (2×) e upload por seletor (3×), falhas anteriores aos consertos de 21/10. Achados: a VM estava hibernando (liguei) e hibernou no meio de uma revisão (5ae54ac: a revisão marca atividade); o teste t_upload_pela_janela_de_arquivos_do_botao falha às vezes na suíte inteira, também no código de antes (1 em 4), não mexi.
