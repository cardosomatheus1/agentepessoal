#!/bin/bash
# First boot: install a test game (2048) and Aurora Store (Play Store apps without a Google account).
set -u
ADB="adb -s 127.0.0.1:5555"
adb connect 127.0.0.1:5555 >/dev/null 2>&1
for i in $(seq 1 90); do
  [ "$($ADB shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ] && break
  adb connect 127.0.0.1:5555 >/dev/null 2>&1; sleep 5
done
mkdir -p /opt/agentepessoal/apks && cd /opt/agentepessoal/apks
for apk in com.uberspot.a2048_25.apk com.aurora.store_76.apk; do
  pkg=${apk%_*}
  $ADB shell pm list packages | grep -q "package:${pkg}$" && continue
  curl -sSfL -o "$apk" "https://f-droid.org/repo/$apk" && $ADB install -r "$apk"
done
$ADB shell settings put system screen_off_timeout 2147483647 || true
