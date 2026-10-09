# Assistir vídeo

O navegador do agente é o Chromium do Playwright, que não toca H.264/AAC (o formato dos vídeos do
Instagram e de muitos sites): o player dá erro e o quadro fica preto. E mesmo quando toca, o agente só
vê prints. `assistir_video` resolve pelos dois lados:

1. baixa o vídeo com `yt-dlp` (sem login; se o site exigir, com os cookies do próprio navegador do agente,
   onde ele já está logado) ou usa um arquivo já anexado;
2. o **TwelveLabs Pegasus 1.5** (Bedrock, pelo proxy da VM) assiste o vídeo inteiro, imagem e áudio, e
   descreve em ordem com os tempos. É vendido pelo AWS Marketplace (a conta assinou no primeiro uso; o papel
   da VM pode assinar só via Bedrock) e entra no crédito da AWS como os outros modelos de terceiros.
   Preço: US$ 0,00049/s de vídeo + US$ 7,50/M tokens de saída (~US$ 0,035 por minuto). Vídeos acima de
   20 MB são recodificados em 480p antes de enviar;
3. a fala exata (faster-whisper, com tempos) volta junto, para citações;
4. se o Pegasus falhar: **Amazon Nova 2 Lite** assiste o vídeo com a transcrição no mesmo pedido (o Nova não
   ouve áudio); se também falhar, até 16 quadros (`ffmpeg`) + transcrição num modelo de visão.

Tudo fica em `/a0/usr/workdir/videos/<id>/`. Limites: até 20 min e 300 MB por vídeo. Um vídeo de 1 min
leva ~11 s no Pegasus (mais a transcrição).
