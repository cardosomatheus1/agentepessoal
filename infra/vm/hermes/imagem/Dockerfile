# Imagem do Hermes com os pacotes que os helpers dos nossos plugins usam e a oficial não traz (migração, fase 2;
# faster-whisper na fase 6: o áudio do celular, a mesma versão do A0; adb + uiautomator2 na virada: o celular Android,
# as mesmas versões do A0; patchright e flask: os moldes de vídeo e a suíte do Segundo Cérebro, como no A0).
# patches/: correções no código do navegador da oficial (cabeçalho de cada um diz o quê e por quê), aplicadas com git
# apply; se a oficial mudar e um não encaixar, o build para (nada sobe pela metade).
# xvfb e xdotool: a tela do navegador e o toque do "Resolver aqui" como mouse de verdade (navegador.sh), como no A0.
# O venv da oficial não tem pip: o uv (versão fixa) instala direto nele. Versões fixas; mude com teste.
FROM ghcr.io/astral-sh/uv:0.5.11 AS uv
FROM nousresearch/hermes-agent:v0.22.2
COPY --from=uv /uv /usr/local/bin/uv
RUN apt-get update -q && DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends adb xvfb xdotool \
 && rm -rf /var/lib/apt/lists/*
RUN uv pip install --no-cache --python /opt/hermes/.venv/bin/python3 \
      beautifulsoup4==4.12.3 dnspython==2.7.0 python-docx==1.1.2 openpyxl==3.1.5 pypdf==5.1.0 xlrd==2.0.1 \
      PyYAML==6.0.2 numpy==2.1.3 faster-whisper==1.2.1 ctranslate2==4.8.2 uiautomator2==3.7.0 adbutils==2.12.0 patchright==1.61.2 \
      flask==3.0.3 \
 && rm /usr/local/bin/uv \
 && /opt/hermes/.venv/bin/python3 -c "import bs4, dns.resolver, docx, openpyxl, pypdf, xlrd, yaml, numpy, faster_whisper, uiautomator2, patchright, flask" \
 && adb version && which Xvfb xdotool && /opt/hermes/.venv/bin/python3 -c "import PIL.features as f; assert f.check_feature('xcb')"
COPY patches /tmp/patches
RUN cd /opt/hermes/tools && for p in /tmp/patches/*.patch; do git apply -p1 "$p" || exit 1; done \
 && ! grep -q '"Runtime.enable"' browser_supervisor_frames.py \
 && grep -q 'challenges' browser_supervisor_dialogs.py && grep -q '_acquire_own_tab' browser_tool_session.py \
 && cd /opt/hermes && /opt/hermes/.venv/bin/python3 -c "import tools.browser_tool, tools.browser_supervisor, tools.browser_cdp_tool" \
 && rm -rf /tmp/patches
