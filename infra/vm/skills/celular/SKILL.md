---
name: celular
description: "Controlar o celular Android virtual do usuário: instalar e abrir apps, tocar, deslizar, digitar e jogar, olhando a tela por prints."
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

## Conectar (sempre primeiro)

```bash
adb connect android:5555 >/dev/null; adb -s android:5555 wait-for-device; echo ok
```

Use sempre `adb -s android:5555 ...`.

## Atalho recomendado: `acao.sh`

Faz a ação, tira o print novo e diz se a tela mudou — use em vez de comandos soltos:

```bash
/a0/usr/skills/celular/scripts/acao.sh print            # só o print
/a0/usr/skills/celular/scripts/acao.sh baixo            # cima | baixo | esquerda | direita (deslizar)
/a0/usr/skills/celular/scripts/acao.sh tap 360 640
/a0/usr/skills/celular/scripts/acao.sh texto "olá mundo"
/a0/usr/skills/celular/scripts/acao.sh voltar           # voltar | inicio
/a0/usr/skills/celular/scripts/acao.sh abrir com.android.vending   # abrir um app pelo pacote
```

Cada ação já devolve **o texto da tela** (botões e textos com a posição de cada um). **Decida por esse texto**; só use `vision_load` em `/a0/tmp/celular.png` quando a tela não tiver texto (jogo, imagem) ou o texto não bastar — olhar imagem leva 10–30 s. Se a saída for **NAO_MUDOU**, a ação não fez nada: **não repita a mesma ação** — escolha outra.

Use o celular só para o que é de celular (app Android, pedido explícito). Sites e programas: prefira o Browser/Desktop do computador.

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
