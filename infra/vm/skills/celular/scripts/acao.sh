#!/bin/bash
# Uma ação no celular + print novo + aviso se a tela mudou.
# Uso: acao.sh cima|baixo|esquerda|direita | tap X Y | texto "algo" | voltar | inicio | print
set -u
A=android:5555
OUT=/a0/tmp/celular.png
adb connect "$A" >/dev/null 2>&1
before=$(adb -s "$A" exec-out screencap -p | md5sum | cut -d' ' -f1)
case "${1:-print}" in
  cima)     adb -s "$A" shell input swipe 360 1000 360 450 120 ;;
  baixo)    adb -s "$A" shell input swipe 360 450 360 1000 120 ;;
  esquerda) adb -s "$A" shell input swipe 600 750 120 750 120 ;;
  direita)  adb -s "$A" shell input swipe 120 750 600 750 120 ;;
  tap)      adb -s "$A" shell input tap "$2" "$3" ;;
  texto)    adb -s "$A" shell input text "$(printf '%s' "$2" | sed 's/ /%s/g')" ;;
  voltar)   adb -s "$A" shell input keyevent 4 ;;
  inicio)   adb -s "$A" shell input keyevent 3 ;;
  print)    ;;
  *) echo "ação desconhecida: $1"; exit 2 ;;
esac
[ "${1:-print}" = print ] || sleep 0.8
adb -s "$A" exec-out screencap -p > "$OUT"
after=$(md5sum < "$OUT" | cut -d' ' -f1)
if [ "${1:-print}" = print ]; then echo "PRINT $OUT"
elif [ "$before" = "$after" ]; then echo "NAO_MUDOU — a ação não teve efeito; NÃO repita, tente outra. Print: $OUT"
else echo "MUDOU — print: $OUT"; fi
