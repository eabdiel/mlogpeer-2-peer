from __future__ import annotations
import socket
from typing import Optional, Callable, Dict, Any
from .util import get_local_ip
from zeroconf import Zeroconf, ServiceInfo, ServiceBrowser, ServiceStateChange

SERVICE_TYPE = "_mlog._tcp.local."

def _get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

class Discovery:
    def __init__(self, author_id: str, p2p_port: int, web_port: int):
        self.author_id = author_id
        self.p2p_port = p2p_port
        self.web_port = web_port
        self.zc = Zeroconf()
        self.info: Optional[ServiceInfo] = None
        self.browser: Optional[ServiceBrowser] = None

    def start_advertise(self, host_ip: Optional[str] = None) -> None:
        ip = host_ip or _get_local_ip()
        name = f"P2PMlog-{self.author_id}.{SERVICE_TYPE}"
        props = {
            b"author_id": self.author_id.encode("utf-8"),
            b"p2p_port": str(self.p2p_port).encode("utf-8"),
            b"web_port": str(self.web_port).encode("utf-8"),
            b"ws": f"ws://{ip}:{self.p2p_port}".encode("utf-8"),
        }
        self.info = ServiceInfo(
            SERVICE_TYPE,
            name,
            addresses=[socket.inet_aton(ip)],
            port=self.p2p_port,
            properties=props,
            server=f"{self.author_id}.local.",
        )
        self.zc.register_service(self.info)

    def start_browse(self, on_peer: Callable[[Dict[str, Any]], None]) -> None:
        def handler(zc: Zeroconf, service_type: str, name: str, state_change: ServiceStateChange):
            if state_change.name not in ("Added", "Updated"):
                return
            info = zc.get_service_info(service_type, name)
            if not info:
                return
            props = info.properties or {}
            try:
                aid = props.get(b"author_id", b"").decode("utf-8")
                ws = props.get(b"ws", b"").decode("utf-8")
                web_port = int((props.get(b"web_port", b"0").decode("utf-8") or "0"))
                p2p_port = int((props.get(b"p2p_port", b"0").decode("utf-8") or "0"))
                on_peer({"author_id": aid, "ws": ws, "p2p_port": p2p_port, "web_port": web_port, "name": name})
            except Exception:
                return

        self.browser = ServiceBrowser(self.zc, SERVICE_TYPE, handlers=[handler])

    def close(self) -> None:
        try:
            if self.info:
                self.zc.unregister_service(self.info)
        except Exception:
            pass
        try:
            self.zc.close()
        except Exception:
            pass
