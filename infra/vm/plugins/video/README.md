# Assistir vídeo

O navegador do agente é o Chromium do Playwright, que não toca H.264/AAC (o formato dos vídeos do
Instagram e de muitos sites): o player dá erro e o quadro fica preto. E mesmo quando toca, o agente só
vê prints. `assistir_video` resolve pelos dois lados:

1. baixa o vídeo com `yt-dlp` (sem login; se o site exigir, com os cookies do próprio navegador do agente,
   onde ele já está logado) ou usa um arquivo já anexado;
2. tira até 16 quadros espalhados pelo vídeo (`ffmpeg`) e transcreve o áudio (faster-whisper);
3. manda quadros + transcrição numa chamada ao modelo de visão e devolve a descrição, a transcrição e
   os caminhos dos arquivos (`/a0/usr/workdir/videos/<id>/`).

Limites: até 20 min e 300 MB por vídeo.
