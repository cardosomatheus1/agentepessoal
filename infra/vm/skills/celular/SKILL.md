---
name: celular
description: "Controlar o celular Android virtual do usuário: instalar e abrir apps, tocar, deslizar, digitar e jogar, com a ferramenta celular (ação + texto da tela num passo só)."
version: 1.0.0
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

O usuário tem um Android (720x1280, Android 14) rodando na mesma máquina. Você o controla pelo terminal com `adb`. O usuário pode assistir e tocar ao vivo pelo botão **Ver celular** da página de controle.

## Use a ferramenta `celular` (um passo por ação)

Para tudo no celular use a ferramenta **`celular`**: ela faz a ação, espera a tela parar e devolve no mesmo passo o texto da tela (botões e textos com posição), se mudou e o app aberto — ~0,5–2 s. Telas sem texto (jogo, foto, vídeo) já vêm com uma imagem pequena anexada. **Não** tire print + `vision_load` separado: são 3 passos lentos.

```json
{"tool_name": "celular", "tool_args": {"acao": "abrir", "pacote": "com.android.vending"}}
{"tool_name": "celular", "tool_args": {"acao": "tocar_texto", "texto": "Sign in"}}
{"tool_name": "celular", "tool_args": {"acao": "digitar", "texto": "olá", "enviar": true}}
{"tool_name": "celular", "tool_args": {"acao": "deslizar", "direcao": "cima"}}
{"tool_name": "celular", "tool_args": {"acao": "ver", "imagem": "true"}}
```

Se vier **NÃO MUDOU**, a ação não fez nada: **não repita a mesma ação** — escolha outra. Para dezenas de passos repetidos (jogos), escreva um script com a skill **piloto-rapido**.

Use o celular só para o que é de celular (app Android, pedido explícito). Sites e programas: prefira o Browser/Desktop do computador.

## Terminal (só para o que a ferramenta não faz)

Instalar APK, `pm`, arquivos: `adb connect android:5555 >/dev/null; adb -s android:5555 ...`. O atalho antigo `/a0/usr/skills/celular/scripts/acao.sh` ainda existe, mas é mais lento que a ferramenta.

## Ver a tela (comandos soltos)

```bash
adb -s android:5555 exec-out screencap -p > /a0/tmp/celular.png
```

Depois use a ferramenta `vision_load` com `/a0/tmp/celular.png`. As coordenadas da imagem são as mesmas da tela (largura 720, altura 1280).

Para achar botões com precisão (texto e posição), prefira a árvore da interface:

```bash
adb -s android:5555 shell uiautomator dump /sdcard/ui.xml >/dev/null && adb -s android:5555 exec-out cat /sdcard/ui.xml
```

Cada elemento tem `text`, `resource-id` e `bounds="[x1,y1][x2,y2]"`; toque no centro.

## Agir

| Ação | Comando |
|---|---|
| Tocar | `adb -s android:5555 shell input tap X Y` |
| Deslizar | `adb -s android:5555 shell input swipe X1 Y1 X2 Y2 200` |
| Digitar | `adb -s android:5555 shell input text 'ola%smundo'` (`%s` = espaço) |
| Voltar / Início / Enter | `adb -s android:5555 shell input keyevent 4` / `3` / `66` |
| Abrir app | `/a0/usr/skills/celular/scripts/acao.sh abrir PACOTE` (usa `am start`; o `monkey` não funciona nesta imagem) |
| Apps instalados | `adb -s android:5555 shell pm list packages -3` |
| Instalar APK | baixe com `curl -L -o /a0/tmp/app.apk URL` e rode `adb -s android:5555 install -r /a0/tmp/app.apk` |

Apps já instalados: **Play Store** (`com.android.vending`; o usuário faz o login), **2048** (`com.uberspot.a2048`) e **Aurora Store** (`com.aurora.store`, baixa apps da Play Store sem conta Google — use o login anônimo). Apps de código aberto também podem vir do F-Droid (`https://f-droid.org/repo/<pacote>_<versão>.apk`).

## Como trabalhar

1. Conecte, tire um print e descreva rapidamente o que está na tela.
2. Faça uma ação por vez e confira com novo print (ou `uiautomator dump`) antes da próxima.
3. Em jogos, repita: `acao.sh <jogada>` → `vision_load` do print → decidir a próxima. Seja rápido: uma frase de raciocínio por jogada, sem repetir análises longas. Informe o placar a cada ~5 jogadas.
   - **2048:** use `acao.sh baixo|esquerda|direita|cima`. Estratégia: manter o maior número num canto de baixo; prefira **baixo** e **esquerda**, use **direita** quando essas não mudarem a tela e **cima** só em último caso. Se der NAO_MUDOU, passe para a próxima direção da lista.
4. Nunca faça a mesma ação mais de 2 vezes seguidas sem a tela mudar. Se ficar travado, volte (`acao.sh voltar`) ou reabra o app.

## Tarefas repetitivas e jogos

Para jogar ou repetir muitos passos parecidos, use a skill **piloto-rapido**: um script lê a tela e o Jev decide cada passo em ~0,3 s, em vez de você analisar cada print (15–30 s por passo).

## Regras

- Nunca faça compras, pagamentos, assinaturas ou aceite termos sem confirmação explícita do usuário.
- Não entre em contas do usuário sem ele pedir; para login ou captcha, peça que ele faça pelo **Ver celular** e continue depois.
- Apps de banco e alguns apps com verificação de segurança do Google podem não abrir neste celular virtual; avise o usuário se acontecer.
