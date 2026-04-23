"""指定 host の start から順に bind を試し、最初に成功したポート番号を stdout に出す。

Usage:
    python tools/find_free_port.py <host> <start_port> [max_scan=100]

run.cmd / run.sh から呼び、実際に uvicorn をバインドする前の空きポート探索に使う。
"""
from __future__ import annotations

import socket
import sys


def main() -> int:
    if len(sys.argv) < 3:
        sys.stderr.write("usage: find_free_port.py <host> <start_port> [max_scan]\n")
        return 2

    host = sys.argv[1]
    start = int(sys.argv[2])
    max_scan = int(sys.argv[3]) if len(sys.argv) >= 4 else 100

    for port in range(start, start + max_scan):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
            except OSError:
                continue
        print(port)
        return 0

    sys.stderr.write(f"no free port found in [{start}, {start + max_scan})\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
