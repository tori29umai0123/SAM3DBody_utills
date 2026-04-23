"""起動時にブラウザからアクセスできる URL を列挙して stdout に出す。

Usage:
    python tools/show_urls.py <host> <port>

host が 0.0.0.0 / :: の場合は loopback と LAN IP (IPv4) を両方出す。
それ以外の場合は指定 host の URL のみ出す。
"""
from __future__ import annotations

import socket
import sys


def _get_lan_ipv4() -> list[str]:
    ips: set[str] = set()

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith("127."):
                ips.add(ip)
    except OSError:
        pass

    # 外向き UDP で OS のデフォルトルートの IP を引く (パケットは送らない)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        if ip and not ip.startswith("127."):
            ips.add(ip)
    except OSError:
        pass

    return sorted(ips)


def main() -> int:
    if len(sys.argv) < 3:
        sys.stderr.write("usage: show_urls.py <host> <port>\n")
        return 2

    host = sys.argv[1]
    port = int(sys.argv[2])

    print("Access URL:")
    if host in ("0.0.0.0", "::"):
        print(f"  http://127.0.0.1:{port}       (this PC)")
        for ip in _get_lan_ipv4():
            print(f"  http://{ip}:{port}       (LAN)")
    else:
        print(f"  http://{host}:{port}")
        if host in ("127.0.0.1", "localhost", "::1"):
            print("  (LAN access disabled: set SAM3DBODY_HOST=0.0.0.0 to expose)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
