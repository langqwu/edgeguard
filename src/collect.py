"""采集主程序：从 PZEM-004T 读取电参量，存 CSV 并可选实时绘图。

示例::

    python -m src.collect --port COM3 --label e_bike_charger --minutes 30
    python -m src.collect --port /dev/ttyUSB0 --label kettle --minutes 10 --interval 1
    python -m src.collect --port COM3 --label normal --minutes 5 --plot

产出::

    data/raw/<label>/<YYYYmmdd-HHMMSS>.csv
    data/raw/<label>/<YYYYmmdd-HHMMSS>.meta.json

CSV 列：timestamp, elapsed_s, voltage, current, power, energy, frequency, power_factor
"""

from __future__ import annotations

import argparse
import csv
import json
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.pzem import PZEM004T, PZEMError, Reading

FIELDNAMES = [
    "timestamp",
    "elapsed_s",
    "voltage",
    "current",
    "power",
    "energy",
    "frequency",
    "power_factor",
]

_shutdown_requested = False


def _handle_sigint(signum, frame) -> None:  # noqa: ARG001
    global _shutdown_requested
    _shutdown_requested = True
    print("\n收到中断信号，正在保存并退出……", file=sys.stderr)


def _output_path(label: str) -> Path:
    out_dir = Path("data") / "raw" / label
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return out_dir / f"{stamp}.csv"


def collect(
    port: str,
    label: str,
    minutes: float,
    interval: float,
    plot: bool,
    address: int = 1,
) -> Path:
    """采集 ``minutes`` 分钟的电参量，返回 CSV 路径。"""
    signal.signal(signal.SIGINT, _handle_sigint)

    csv_path = _output_path(label)
    meta_path = csv_path.with_suffix(".meta.json")
    total_seconds = minutes * 60.0
    started = time.monotonic()
    samples = 0
    failures = 0
    peak_power = 0.0

    plotter = None
    if plot:
        plotter = _make_plotter()

    print(f"[collect] 串口={port} 标签={label} 时长={minutes:g} 分钟 间隔={interval:g}s")
    print(f"[collect] 输出 -> {csv_path}")

    with PZEM004T(port, address=address) as meter, csv_path.open(
        "w", newline="", encoding="utf-8"
    ) as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()

        try:
            while not _shutdown_requested:
                elapsed = time.monotonic() - started
                if elapsed >= total_seconds:
                    break
                tick = time.monotonic()
                try:
                    reading = meter.read()
                except PZEMError as exc:
                    failures += 1
                    print(f"[collect] 读取失败（{failures}）：{exc}", file=sys.stderr)
                    time.sleep(interval)
                    continue

                row = _row(reading, elapsed)
                writer.writerow(row)
                fh.flush()
                samples += 1
                peak_power = max(peak_power, reading.power)

                if plotter is not None:
                    plotter.update(elapsed, reading)

                if samples % 10 == 0:
                    print(
                        f"[collect] t={elapsed:7.1f}s  "
                        f"P={reading.power:8.1f}W  U={reading.voltage:6.1f}V  "
                        f"I={reading.current:6.3f}A  PF={reading.power_factor:.2f}"
                    )

                spent = time.monotonic() - tick
                time.sleep(max(0.0, interval - spent))
        finally:
            meta = {
                "label": label,
                "port": port,
                "address": address,
                "interval_s": interval,
                "duration_s": round(time.monotonic() - started, 1),
                "samples": samples,
                "failures": failures,
                "peak_power_w": round(peak_power, 2),
                "started_at": datetime.now(timezone.utc).isoformat(),
                "tool": "EdgeGuard collect v0.1",
            }
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), "utf-8")
            if plotter is not None:
                plotter.close()

    print(f"[collect] 完成：{samples} 条样本，失败 {failures} 次，峰值 {peak_power:.1f} W")
    print(f"[collect] 元数据 -> {meta_path}")
    return csv_path


def _row(reading: Reading, elapsed: float) -> dict:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "elapsed_s": round(elapsed, 3),
        "voltage": round(reading.voltage, 2),
        "current": round(reading.current, 4),
        "power": round(reading.power, 2),
        "energy": round(reading.energy, 4),
        "frequency": round(reading.frequency, 2),
        "power_factor": round(reading.power_factor, 3),
    }


class _LivePlotter:
    """用 matplotlib 的交互模式画一条实时功率曲线。"""

    def __init__(self) -> None:
        import matplotlib

        matplotlib.use("TkAgg")
        import matplotlib.pyplot as plt

        self._plt = plt
        plt.ion()
        self.fig, self.ax = plt.subplots(figsize=(10, 4))
        (self.line,) = self.ax.plot([], [], lw=1.2)
        self.ax.set_xlabel("elapsed (s)")
        self.ax.set_ylabel("power (W)")
        self.ax.set_title("PZEM-004T live power")
        self.ax.grid(True, alpha=0.3)
        self._xs: list[float] = []
        self._ys: list[float] = []

    def update(self, x: float, reading: Reading) -> None:
        self._xs.append(x)
        self._ys.append(reading.power)
        self.line.set_data(self._xs, self._ys)
        self.ax.relim()
        self.ax.autoscale_view()
        self.fig.canvas.draw_idle()
        self.fig.canvas.flush_events()

    def close(self) -> None:
        self._plt.ioff()
        self._plt.close(self.fig)


def _make_plotter() -> Optional[_LivePlotter]:
    try:
        return _LivePlotter()
    except Exception as exc:  # matplotlib 缺失或没有图形界面
        print(f"[collect] 实时绘图不可用（{exc}），继续纯采集。", file=sys.stderr)
        return None


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="PZEM-004T 数据采集")
    parser.add_argument("--port", required=True, help="串口，例如 COM3")
    parser.add_argument(
        "--label",
        required=True,
        help="负载标签，如 e_bike_charger / kettle / hair_dryer / aircon / normal",
    )
    parser.add_argument("--minutes", type=float, default=30.0, help="采集时长（分钟）")
    parser.add_argument("--interval", type=float, default=1.0, help="采样间隔（秒）")
    parser.add_argument("--address", type=int, default=1, help="模块地址，默认 1")
    parser.add_argument("--plot", action="store_true", help="是否实时绘图")
    args = parser.parse_args(argv)

    try:
        collect(
            port=args.port,
            label=args.label,
            minutes=args.minutes,
            interval=args.interval,
            plot=args.plot,
            address=args.address,
        )
    except KeyboardInterrupt:
        print("[collect] 已中断。", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
