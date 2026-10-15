"""Explicit IPv4 settings for a local TV and its application server."""

import os
import socket
from dataclasses import dataclass
from ipaddress import IPv4Address
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def lan_address(tv_ip: str) -> str:
    """Ask the routing table which local interface reaches the television."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
            connection.connect((tv_ip, 7345))
            return str(connection.getsockname()[0])
    except OSError:
        return "127.0.0.1"


@dataclass(frozen=True)
class Settings:
    bind_ip: str
    tv_ip: str = "192.0.2.20"
    port: int = 8765
    data_dir: Path = ROOT / "data"
    media_dir: Path = ROOT / "media"

    def __post_init__(self):
        for name,value in (("VIZIO_BIND_IP",self.bind_ip),("VIZIO_TV_IP",self.tv_ip)):
            try:
                address=IPv4Address(value)
            except ValueError:
                raise ValueError(f"{name} must be an IPv4 address.") from None
            if address.is_unspecified or address.is_multicast or str(address)=="255.255.255.255":
                raise ValueError(f"{name} must identify a specific network interface or device.")
        if not 1<=self.port<=65535:
            raise ValueError("VIZIO_PORT must be between 1 and 65535.")

    @classmethod
    def from_env(cls) -> "Settings":
        tv_ip = os.getenv("VIZIO_TV_IP", "").strip()
        if not tv_ip:
            raise ValueError("Set VIZIO_TV_IP to your television's LAN IPv4 address.")
        return cls(
            bind_ip=os.getenv("VIZIO_BIND_IP") or lan_address(tv_ip),
            tv_ip=tv_ip,
            port=int(os.getenv("VIZIO_PORT", "8765")),
            data_dir=Path(os.getenv("VIZIO_DATA_DIR", str(ROOT / "data"))),
            media_dir=Path(os.getenv("VIZIO_MEDIA_DIR", str(ROOT / "media"))),
        )
