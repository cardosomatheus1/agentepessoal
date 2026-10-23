# Imagem do Hermes com os pacotes que os helpers dos nossos plugins usam e a oficial não traz (migração, fase 2;
# faster-whisper na fase 6: o áudio do celular, a mesma versão do A0; adb + uiautomator2 na virada: o celular Android,
# as mesmas versões do A0; patchright e flask: os moldes de vídeo e a suíte do Segundo Cérebro, como no A0).
# O venv da oficial não tem pip: o uv (versão fixa) instala direto nele. Versões fixas; mude com teste.
FROM ghcr.io/astral-sh/uv:0.5.11 AS uv
FROM nousresearch/hermes-agent:v0.22.2
COPY --from=uv /uv /usr/local/bin/uv
RUN apt-get update -q && DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends adb \
 && rm -rf /var/lib/apt/lists/*
RUN uv pip install --no-cache --python /opt/hermes/.venv/bin/python3 \
      beautifulsoup4==4.12.3 dnspython==2.7.0 python-docx==1.1.2 openpyxl==3.1.5 pypdf==5.1.0 xlrd==2.0.1 \
      PyYAML==6.0.2 numpy==2.1.3 faster-whisper==1.2.1 ctranslate2==4.8.2 uiautomator2==3.7.0 adbutils==2.12.0 patchright==1.61.2 \
      flask==3.0.3 \
 && rm /usr/local/bin/uv \
 && /opt/hermes/.venv/bin/python3 -c "import bs4, dns.resolver, docx, openpyxl, pypdf, xlrd, yaml, numpy, faster_whisper, uiautomator2, patchright, flask" \
 && adb version
