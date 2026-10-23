# Imagem do Hermes com os pacotes que os helpers dos nossos plugins usam e a oficial não traz (migração, fase 2).
# O venv da oficial não tem pip: o uv (versão fixa) instala direto nele. Versões fixas; mude com teste.
FROM ghcr.io/astral-sh/uv:0.5.11 AS uv
FROM nousresearch/hermes-agent:v0.22.2
COPY --from=uv /uv /usr/local/bin/uv
RUN uv pip install --no-cache --python /opt/hermes/.venv/bin/python3 \
      beautifulsoup4==4.12.3 dnspython==2.7.0 python-docx==1.1.2 openpyxl==3.1.5 pypdf==5.1.0 xlrd==2.0.1 \
      PyYAML==6.0.2 numpy==2.1.3 \
 && rm /usr/local/bin/uv \
 && /opt/hermes/.venv/bin/python3 -c "import bs4, dns.resolver, docx, openpyxl, pypdf, xlrd, yaml, numpy"
