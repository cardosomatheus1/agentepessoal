# Segundo Cérebro: preparar, implantar, reverter

O que vai para a VM: o build standalone do `app/` (Next) e o plugin `infra/vm/plugins/segundo_cerebro` (o gateway
dentro do Agent Zero). Contrato de sessão e de rotas: `app/SECOND_BRAIN.md`. Código: `infra/operador/segundo_cerebro.py`
(daqui) e `infra/operador/segundo_cerebro_vm.py` (roda na VM). Nenhuma infraestrutura nova: mesmo bucket S3, mesmo
SSM, mesma VM e mesmo container `agent-zero`. Nenhuma porta pública nova: o Next só escuta em `127.0.0.1` dentro do
container.

## 1. Preparar localmente (sem AWS, sem commit)

```bash
python3 infra/operador/segundo_cerebro.py preparar --saida /tmp/segundo-cerebro-preparo \
  --python-suite /opt/venv-a0/bin/python
# ou: python3 infra/operador/implantar.py --segundo-cerebro --preparar --python-suite /opt/venv-a0/bin/python
#     (saída numa pasta temporária nova, impressa no fim)
```

- Fonte: `git archive HEAD` mais só os arquivos do Segundo Cérebro do working tree (`FOCO_LOCAL`). Mudanças de
  outras frentes ficam de fora e aparecem em `sujos_deixados_de_fora` no relatório.
- Roda a suíte do plugin (precisa de Flask: use o Python do Agent Zero), os testes Node e `next build`. O build usa
  uma **cópia** do `app/node_modules` existente; nada é instalado.
- Offline de verdade: todo proxy aponta para `127.0.0.1:9` e as fontes Geist do `next/font/google` vêm, embutidas
  (`data:`), do build anterior em `app/.next/static/media` (`NEXT_FONT_GOOGLE_MOCKED_RESPONSES`). Se esse build
  anterior não existir, o `next build` falha em vez de baixar.
- Saída: `segundo-cerebro-local-<head>.tgz` (`release/` com `server.js`, `.next/static`, `public`; `plugin/`; `vm/`;
  `MANIFESTO.json` com SHA-256 de cada arquivo), `relatorio.json`, `testes-node.log` e `build.log`.
- O pacote local **não serve para implantar**: a VM só aceita versão = commit de 40 caracteres.

## 2. Implantar

Antes: commit e push de `app/`, do plugin e de `infra/operador/segundo_cerebro*.py` (esses caminhos precisam estar
limpos e com `HEAD == origin/<ramo>`).

```bash
python3 infra/operador/implantar.py --segundo-cerebro [--python-suite /caminho/python-com-flask]
```

A suíte do plugin roda aqui antes do envio e precisa de Flask (por padrão, o mesmo `python3`). O build copia o
`app/node_modules` deste checkout, que já tem que estar instalado.

Passos (qualquer falha para tudo; não existe `--forcar`):

1. `_conferir_git` nos caminhos aprovados (sujo, ou HEAD diferente do remoto: recusa).
2. Confere a conta AWS (`964862484412`) e se a VM `i-0498b4f39560b01a9` está online no SSM.
3. `git archive HEAD` → suíte do plugin → testes Node → `next build` (com rede, para as fontes) → pacote.
4. Envia ao bucket existente (`tmp/implantar-segundo-cerebro-<commit>.tgz`) e baixa numa pasta nova em
   `/tmp/implantar-segundo-cerebro/` na VM.
5. **conferir** (VM): manifesto íntegro (nenhum arquivo a mais ou alterado, nenhum link para fora); destinos
   esperados ou ausentes (`/opt/a0/usr/plugins/segundo_cerebro` tem que ser pasta comum com `name: segundo_cerebro`
   e `.versao`; `/opt/a0/usr/segundo_cerebro` pasta comum; release desta versão ainda não instalada); container
   rodando; `node >= 20.9` e `/opt/venv-a0/bin/python` no container. Caso contrário: "runtime desconhecido", e nada
   muda.
6. Guarda de versão: o plugin e a release que estão no ar têm que estar no histórico deste checkout.
7. **estagiar** (VM): cópia em `segundo_cerebro/estagio/<commit>`, suíte do plugin dentro do container e um início
   real da release (porta e bearer próprios), checando API 200 com `owner: matheus`, 401 sem bearer, página 200 e um
   asset 200. Se falhar, nada é trocado.
8. **trocar** (VM): o plugin atual vira snapshot em `segundo_cerebro/plugins-anteriores/`, a release entra em
   `segundo_cerebro/releases/<commit>`, `atual` aponta para ela, `anterior.json` guarda o que voltar, e uma cópia do
   script da VM fica em `segundo_cerebro/vm/` (para o rollback). Só renomeações, nada apagado.
9. **sondar** (VM): sem sessão, `/segundo-cerebro` e `/api/segundo-cerebro` têm que dar 401, e `/login` tem que dar
   200/302; a release no ar tem que subir saudável. Se o gateway ainda não está registrado (primeira instalação: ele
   entra quando o Agent Zero inicia), o container é reiniciado **uma vez** e a sonda repete.
10. URL pública do parâmetro SSM existente `/agentepessoal/agent-url`: `/segundo-cerebro` e `/api/segundo-cerebro`
    sem sessão = 401 e `/login` = 200.
11. Se 9 ou 10 falham: **reverter automático** (sem reiniciar: com o plugin fora do lugar, o gateway não serve nada).

Atualizações seguintes não precisam reiniciar: o gateway recarrega `gateway.py`/`processo.py` quando mudam e
reinicia o Node quando `atual` aponta para outra release.

## 3. Reverter

```bash
python3 infra/operador/implantar.py --segundo-cerebro --rollback
```

- Volta o **snapshot do plugin e a release que rodavam antes do último deploy**, não a versão do git.
- Primeira instalação: o plugin sai do lugar (vai para `segundo_cerebro/retirados/`), `atual` = `desativado`, e as
  rotas voltam a não existir (404), sem reiniciar.
- O plugin desfeito vai para `retirados/`; snapshots e releases ficam. Nada é apagado. O mesmo deploy não se reverte
  duas vezes.

## Na VM (para conferir)

```
/opt/a0/usr/plugins/segundo_cerebro/.versao      commit e hora do plugin no ar
/opt/a0/usr/segundo_cerebro/atual                release no ar (ou "desativado")
/opt/a0/usr/segundo_cerebro/anterior.json        o que o rollback põe de volta
/opt/a0/usr/segundo_cerebro/historico.log        trocas, reinícios e reversões
/opt/a0/usr/segundo_cerebro/node.log             saída do Node (sem o bearer)
```

## Limites e o que ainda não foi verificado

- Nada disto rodou contra a AWS: o caminho de deploy está testado só com SSM, S3 e `docker` falsos
  (`infra/operador/tests/test_segundo_cerebro.py`).
- Não se sabe ainda se o container `agent-zero` tem `node >= 20.9`. Se não tiver, o deploy para no passo 5. Instalar
  o Node no container é decisão à parte.
- O reinício da primeira instalação derruba conversas em andamento por alguns segundos.
- O teste da URL pública supõe que o caminho até o Agent Zero devolve o 401 sem trocar por outra página.
- O build de deploy baixa as fontes Geist do Google (como qualquer `next build` deste app). Só o preparo local é
  offline.
- `/icon.svg` e `/manifest.webmanifest` não passam pelo gateway (lista fechada de caminhos).
