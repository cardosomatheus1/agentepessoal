# Assistir vídeo

O navegador do agente é o Chromium do Playwright, que não toca H.264/AAC (o formato dos vídeos do
Instagram e de muitos sites): o player dá erro e o quadro fica preto. E mesmo quando toca, o agente só
vê prints. `assistir_video` resolve pelos dois lados:

1. baixa o vídeo com `yt-dlp` (sem login; se o site exigir, com os cookies do próprio navegador do agente,
   onde ele já está logado) ou usa um arquivo já anexado;
2. o **Amazon Nova 2 Lite** (Bedrock, pelo proxy da VM) assiste o vídeo inteiro e, junto com a transcrição
   da fala (o Nova não ouve áudio), descreve em ordem com os tempos; vídeos acima de 20 MB são recodificados
   em 480p antes de enviar. (O TwelveLabs Pegasus ouve o áudio também, mas exige assinatura no AWS Marketplace.)
3. a transcrição da fala (faster-whisper, com tempos) vai antes, no mesmo pedido, e volta junto para citações;
4. se o Nova falhar: até 16 quadros (`ffmpeg`) + transcrição numa chamada ao modelo de visão.

Tudo fica em `/a0/usr/workdir/videos/<id>/`. Limites: até 20 min e 300 MB por vídeo. Um vídeo de 1 min
leva ~10 s no Nova (mais a transcrição).
