"""串口枚举：采集前先确认 PZEM 挂在哪一个串口上。

用法::

    python -m tools.list_ports
"""

from __future__ import annotations

import sys


def main() -> int:
    try:
        from serial.tools import list_ports
    except ImportError:
        print("需要 pyserial：pip install pyserial", file=sys.stderr)
        return 1

    ports = sorted(list_ports.comports(), key=lambda p: p.device)
    if not ports:
        print("没有发现串口。检查 USB 转 TTL 是否插好、驱动是否安装。")
        return 0

    print(f"发现 {len(ports)} 个串口：\n")
    for port in ports:
        print(f"  {port.device:<12} {port.description}")
        if port.hwid:
            print(f"  {'':<12} {port.hwid}")
    print(
        "\n提示：CH340/CP2102 通常显示为 USB-SERIAL CH340 或 Silicon Labs CP210x。"
        "\n用法：python -m src.collect --port <上面的设备名> --label <负载标签> --minutes 30"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
