"""Repasse do CDP do navegador do Hermes (navegador.sh): o Chromium sem tela só escuta no loopback do próprio container
(ignora --remote-debugging-address), então este processo escuta na rede "hermes" (porta 9223) e repassa cada conexão
para 127.0.0.1:9222. Sem mudar nada: o Chromium monta o webSocketDebuggerUrl com o Host pedido (o IP do container), que
volta por aqui. Só a biblioteca padrão."""
import socket
import sys
import threading

DESTINO = ("127.0.0.1", 9222)
ESCUTA = ("0.0.0.0", int(sys.argv[1]) if len(sys.argv) > 1 else 9223)
if len(sys.argv) > 2:  # virada: o mesmo repasse leva o adb da rede do Hermes ao celular (hermes-celular, subir.sh)
    _h, _, _p = sys.argv[2].rpartition(":")
    DESTINO = (_h, int(_p))


def _bombear(origem: socket.socket, destino: socket.socket) -> None:
    try:
        while True:
            dados = origem.recv(65536)
            if not dados:
                break
            destino.sendall(dados)
    except OSError:
        pass
    finally:
        for s in (origem, destino):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def _atender(cliente: socket.socket) -> None:
    try:
        alvo = socket.create_connection(DESTINO, timeout=10)
        alvo.settimeout(None)
    except OSError:
        cliente.close()
        return
    threading.Thread(target=_bombear, args=(cliente, alvo), daemon=True).start()
    _bombear(alvo, cliente)
    cliente.close()
    alvo.close()


def main() -> None:
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    servidor.bind(ESCUTA)
    servidor.listen(64)
    while True:
        cliente, _ = servidor.accept()
        threading.Thread(target=_atender, args=(cliente,), daemon=True).start()


if __name__ == "__main__":
    main()
