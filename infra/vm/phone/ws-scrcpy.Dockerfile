# Live view/control of the virtual phone in the browser (official ws-scrcpy, pinned commit).
FROM node:22-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends adb git python3 make g++ \
 && rm -rf /var/lib/apt/lists/*
RUN git clone https://github.com/NetrisTV/ws-scrcpy.git /src && cd /src && git checkout cd6cea6 \
 && npm install --no-audit --no-fund && npm run dist \
 && cd dist && npm install --omit=dev --no-audit --no-fund
WORKDIR /src/dist
CMD ["sh", "-c", "(while true; do adb connect android:5555 >/dev/null 2>&1; sleep 10; done) & exec node index.js"]
