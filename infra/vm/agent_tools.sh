#!/bin/bash
# Make sure adb exists inside the Agent Zero container (it is lost if the container is recreated).
for i in $(seq 1 30); do docker exec agent-zero true 2>/dev/null && break; sleep 5; done
for i in $(seq 1 20); do
  docker exec agent-zero sh -c 'command -v adb >/dev/null || (apt-get update -qq && apt-get install -y -qq adb)' && break
  sleep 15   # the container may be running its own apt at startup
done
docker exec agent-zero adb connect android:5555 >/dev/null 2>&1 || true
# Persistent screen reader for the "celular" tool (server venv) and piloto-rapido scripts (/opt/venv).
for py in /opt/venv-a0/bin/python /opt/venv/bin/python; do
  for i in 1 2 3; do
    docker exec agent-zero sh -c "$py -c 'import uiautomator2' 2>/dev/null || $py -m pip install -q uiautomator2" && break
    sleep 10
  done
done
