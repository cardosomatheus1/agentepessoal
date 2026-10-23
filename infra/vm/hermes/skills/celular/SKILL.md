---
name: celular
description: "Controlar o celular Android virtual do usuário: instalar e abrir apps, tocar, deslizar, digitar e jogar, com a ferramenta celular (ação + texto da tela num passo só)."
version: 1.0.0
adaptada_hermes: 2026-10-23
origem_a0: 1.0.0
tags: ["android", "celular", "app", "jogo", "adb", "phone"]
trigger_patterns:
  - "celular"
  - "android"
  - "no app"
  - "instalar app"
  - "jogar"
  - "jogo"
---

# Celular Android virtual

O usuário tem um Android (720x1280, Android 14) rodando na mesma máquina. Você o controla pela ferramenta `celular` e, para o resto, pelo `terminal` com `adb`. O usuário pode assistir e tocar ao vivo pelo botão **Ver celular** da página de controle.

## Use a ferramenta `celular` (um passo por ação)

Para tudo no celular use a ferramenta **`celular`**. Ela faz a ação, espera a tela parar e devolve no mesmo passo:
- o texto da tela (botões e textos com posição);
- se a tela mudou;
- o app aberto.

Leva cerca de 0,5–2 s. Telas sem texto (jogo, foto, vídeo) já vêm com uma imagem pequena anexada. **Não** tire print + `vision_analyze` separado: são 3 passos lentos.

```json
{"acao": "abrir", "pacote": "com.android.vending"}
{"acao": "tocar_texto", "texto": "Sign in"}
{"acao": "digitar", "texto": "olá", "enviar": true}
{"acao": "deslizar", "direcao": "cima"}
{"acao": "ver", "imagem": "true"}
```

(Argumentos da ferramenta `celular`.)

Se vier **NÃO MUDOU**, a ação não fez nada: **não repita a mesma ação** — escolha outra. Para dezenas de passos repetidos (jogos), escreva um script com a skill **piloto-rapido**.

Use o celular só para o que é de celular (app Android, pedido explícito). Para sites e programas, prefira o navegador do computador (`browser_navigate`, `browser_snapshot` etc.).

## Terminal (só para o que a ferramenta não faz)

Para instalar APK, usar `pm` ou mexer em arquivos, use o `terminal`:

`adb connect android:5555 >/dev/null; adb -s android:5555 ...`

O atalho antigo `/a0/usr/skills/celular/scripts/acao.sh` ainda existe, mas é mais lento que a ferramenta.

## Ver a tela (comandos soltos)

No `terminal`:

```bash
adb -s android:5555 exec-out screencap -p > /a0/tmp/celular.png
```

Depois use `vision_analyze` com `/a0/tmp/celular.png`. As coordenadas da imagem são as mesmas da tela (largura 720, altura 1280).

Para achar botões com precisão (texto e posição), prefira a árvore da interface:

```bash
adb -s android:5555 shell uiautomator dump /sdcard/ui.xml >/dev/null && adb -s android:5555 exec-out cat /sdcard/ui.xml
```

Cada elemento tem `text`, `resource-id` e `bounds="[x1,y1][x2,y2]"`; toque no centro.

## Agir

Comandos para rodar no `terminal`:

| Ação | Comando |
|---|---|
| Tocar | `adb -s android:5555 shell input tap X Y` |
| Deslizar | `adb -s android:5555 shell input swipe X1 Y1 X2 Y2 200` |
| Digitar | `adb -s android:5555 shell input text 'ola%smundo'` (`%s` = espaço) |
| Voltar / Início / Enter | `adb -s android:5555 shell input keyevent 4` / `3` / `66` |
| Abrir app | `/a0/usr/skills/celular/scripts/acao.sh abrir PACOTE` (usa `am start`; o `monkey` não funciona nesta imagem) |
| Apps instalados | `adb -s android:5555 shell pm list packages -3` |
| Instalar APK | baixe com `curl -L -o /a0/tmp/app.apk URL` e rode `adb -s android:5555 install -r /a0/tmp/app.apk` |

Apps já instalados:
- **Play Store** (`com.android.vending`): o usuário faz o login.
- **2048** (`com.uberspot.a2048`).
- **Aurora Store** (`com.aurora.store`): baixa apps da Play Store sem conta Google. Use o login anônimo.

Apps de código aberto também podem vir do F-Droid (`https://f-droid.org/repo/<pacote>_<versão>.apk`).

## Como trabalhar

1. Conecte, tire um print e descreva rapidamente o que está na tela.
2. Faça uma ação por vez. Confira com novo print (ou `uiautomator dump`) antes da próxima.
3. Em jogos, repita este ciclo: `acao.sh <jogada>` → `vision_analyze` do print → decidir a próxima.
   - Seja rápido: uma frase de raciocínio por jogada, sem repetir análises longas.
   - Informe o placar a cada ~5 jogadas.
   - **2048:** use `acao.sh baixo|esquerda|direita|cima`.
     - Estratégia: manter o maior número num canto de baixo.
     - Prefira **baixo** e **esquerda**. Use **direita** quando essas não mudarem a tela e **cima** só em último caso.
     - Se der NAO_MUDOU, passe para a próxima direção da lista.
4. Nunca faça a mesma ação mais de 2 vezes seguidas sem a tela mudar. Se ficar travado, volte (`acao.sh voltar`) ou reabra o app.

## Tarefas repetitivas e jogos

Para jogar ou repetir muitos passos parecidos, use a skill **piloto-rapido**. Nela, um script lê a tela e o Jev decide cada passo em ~0,3 s, em vez de você analisar cada print (15–30 s por passo).

## Regras

- Nunca faça compras, pagamentos ou assinaturas, nem aceite termos, sem confirmação explícita do usuário.
- Não entre em contas do usuário sem ele pedir. Para login ou captcha, peça que ele faça pelo **Ver celular** e continue depois.
- Apps de banco e alguns apps com verificação de segurança do Google podem não abrir neste celular virtual. Avise o usuário se acontecer.
