"""探测 PZEM-004T：扫描 Modbus 地址并打印一条读数。

用途：设备刚到、第一次上电时，确认「接线对不对、地址是多少」。
默认先试 0xF8（出厂常见）与 0x01，再扫 2–10。

用法::

    python -m tools.pzem_probe --port COM3
    python -m tools.pzem_probe --port COM3 --full      # 扫 0x01–0xF7
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional

from src.pzem import PZEM004T, PZEMError


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="PZEM-004T 地址探测")
    parser.add_argument("--port", required=True, help="串口，例如 COM3")
    parser.add_argument("--full", action="store_true", help="扫描 0x01–0xF7 全部地址")
    parser.add_argument("--baudrate", type=int, default=9600)
    args = parser.parse_args(argv)

    candidates: list[int] = [0xF8, 0x01]
    if args.full:
        candidates = list(range(0x01, 0xF8))
    else:
        candidates += list(range(0x02, 0x0B))

    print(f"[probe] 串口={args.port} 波特率={args.baudrate} 候选地址={len(candidates)} 个")
    found: list[int] = []

    for addr in candidates:
        try:
            with PZEM004T(args.port, address=addr, baudrate=args.baudrate, timeout=0.5) as meter:
                r = meter.read()
            print(
                f"[probe] 命中 0x{addr:02X}：U={r.voltage:.1f}V I={r.current:.3f}A "
                f"P={r.power:.1f}W PF={r.power_factor:.2f} E={r.energy:.4f}kWh"
            )
            found.append(addr)
        except (PZEMError, Exception):
            continue

    if not found:
        print("[probe] 未发现设备。排查顺序：", file=sys.stderr)
        print("  1) TTL 四线是否接全：5V、GND、TX、RX（TX/RX 要交叉）", file=sys.stderr)
        print("  2) USB-TTL 电压档是否为 5V", file=sys.stderr)
        print("  3) PZEM 的 L/N 是否已接 220V（模块靠市电供电）", file=sys.stderr)
        print("  4) 串口是否被其他程序占用、驱动是否装好（设备管理器看 COM 号）", file=sys.stderr)
        print("  5) 若模块是 RS485 版本，需要 USB-RS485 转换器，不能直连 USB-TTL", file=sys.stderr)
        return 1

    print(f"[probe] 可用地址：{['0x%02X' % a for a in found]}")
    print(f"[probe] 采集示例：python -m src.collect --port {args.port} --label e_bike_charger --minutes 30")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
