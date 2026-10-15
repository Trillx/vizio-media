"""Run one lightweight server bound to the interface that reaches the TV."""

import socket
import uvicorn

from app.config import Settings
from app.main import create_app

if __name__ == "__main__":
    settings = Settings.from_env()
    if settings.bind_ip in {"0.0.0.0", "::"}:
        raise SystemExit("Set VIZIO_BIND_IP to a specific LAN address, not every interface.")
    url = f"http://{settings.bind_ip}:{settings.port}/"
    print(f"Vizio Media: {url}", flush=True)
    print(f'Launch: vizaio app launch-config 17 4 "{url}"', flush=True)
    print(f"Allowed clients: this server and TV {settings.tv_ip}. Press Ctrl+C to stop.", flush=True)
    print(f"Account manager on the server's loopback: http://127.0.0.1:{settings.port}/manage",flush=True)
    sockets=[]
    try:
        for address in dict.fromkeys([settings.bind_ip,"127.0.0.1"]):
            listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
            listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            listener.bind((address,settings.port))
            listener.set_inheritable(True)
            sockets.append(listener)
        config=uvicorn.Config(create_app(settings),workers=1,proxy_headers=False,access_log=False)
        uvicorn.Server(config).run(sockets=sockets)
    finally:
        for listener in sockets:
            listener.close()
