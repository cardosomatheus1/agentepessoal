#!/bin/bash
# Prints the Google Services Framework ID needed to register this virtual phone at
# https://www.google.com/android/uncertified (required before signing in to the Play Store).
set -u
A=127.0.0.1:5555
adb connect "$A" >/dev/null 2>&1; adb -s "$A" root >/dev/null 2>&1; sleep 2; adb connect "$A" >/dev/null 2>&1
for i in $(seq 1 60); do
  adb -s "$A" exec-out cat /data/data/com.google.android.gsf/databases/gservices.db > /tmp/gservices.db 2>/dev/null
  id=$(python3 -c "import sqlite3; r=sqlite3.connect('/tmp/gservices.db').execute(\"select value from main where name='android_id'\").fetchone(); print(r[0] if r else '')" 2>/dev/null)
  [ -n "$id" ] && { echo "GSF_ID=$id"; exit 0; }
  sleep 5
done
echo "GSF_ID=not-found (Play Services ainda iniciando?)"; exit 1
