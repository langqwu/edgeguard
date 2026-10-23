"""生成合成波形数据，用于在硬件到货前验证整条流水线。

⚠️ 合成数据只用于**验证代码**与**演示流程**，不得作为方案书里的实验指标来源。
所有合成文件会在 meta 中标注 ``synthetic: true``。

用法::

    python -m src.synth --out data/raw --per-class 6
    python -m src.analyze --plot --features
    python -m src.train --leave-one-out
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

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

# 各类负载的物理特征参数（区间用于制造样本间差异）
PROFILES = {
    # 电瓶车充电器：先恒流后恒压，中间长平台
    "e_bike_charger": dict(peak=(120, 260), plateau=(0.85, 0.95), duration=(120, 180),
                           pf=(0.55, 0.7), shape="plateau"),
    # 电热水壶：快速升到高功率，到温后突降归零
    "kettle": dict(peak=(1400, 1800), plateau=(0.05, 0.15), duration=(6, 9),
                   pf=(0.95, 1.0), shape="burst"),
    # 吹风机：高功率但档位频繁跳变
    "hair_dryer": dict(peak=(900, 1500), plateau=(0.5, 0.7), duration=(8, 14),
                       pf=(0.9, 0.99), shape="choppy"),
    # 正常负载：低功率待机/小电器
    "normal": dict(peak=(10, 80), plateau=(0.7, 0.95), duration=(20, 40),
                   pf=(0.4, 0.8), shape="flat"),
}


def _power_series(profile: dict, seconds: int, rng: random.Random) -> list[float]:
    peak = rng.uniform(*profile["peak"])
    plateau = rng.uniform(*profile["plateau"])
    ramp = rng.uniform(1.0, 4.0)
    shape = profile["shape"]
    base = rng.uniform(2.0, 12.0)
    series: list[float] = []

    for t in range(seconds):
        if shape == "plateau":
            # 阶跃上升 → 长平台 → 尾段缓降
            if t < ramp:
                p = base + (peak - base) * (t / ramp)
            elif t < seconds * 0.9:
                p = peak * plateau
            else:
                k = (t - seconds * 0.9) / (seconds * 0.1 + 1e-6)
                p = peak * plateau * (1 - 0.8 * k)
        elif shape == "burst":
            p = peak if t < seconds * 0.82 else base
        elif shape == "choppy":
            gear = 1.0 if (t // 7) % 2 == 0 else rng.uniform(0.35, 0.6)
            p = peak * gear if t < seconds * 0.9 else base
        else:  # flat
            p = peak * rng.uniform(0.85, 1.0)
        # 加测量噪声
        p = max(0.0, p * rng.uniform(0.985, 1.015))
        series.append(p)
    return series


def generate_class(label: str, count: int, out_root: Path) -> int:
    profile = PROFILES[label]
    rng = random.Random(hash(label) & 0xFFFF)
    out_dir = out_root / label
    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0

    for i in range(count):
        minutes = rng.uniform(*profile["duration"])
        seconds = int(minutes * 60)
        powers = _power_series(profile, seconds, rng)
        pf = rng.uniform(*profile["pf"])
        voltage = rng.uniform(218, 232)
        energy_wh = 0.0
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = out_dir / f"synth-{stamp}-{i:02d}.csv"

        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
            writer.writeheader()
            for t, power in enumerate(powers):
                energy_wh += power / 3600.0
                current = power / max(voltage, 1.0) / max(pf, 0.1)
                writer.writerow(
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "elapsed_s": t,
                        "voltage": round(voltage + rng.uniform(-1, 1), 2),
                        "current": round(current, 4),
                        "power": round(power, 2),
                        "energy": round(energy_wh / 1000.0, 5),
                        "frequency": round(50.0 + rng.uniform(-0.05, 0.05), 2),
                        "power_factor": round(min(1.0, pf + rng.uniform(-0.02, 0.02)), 3),
                    }
                )

        meta = {
            "label": label,
            "synthetic": True,
            "generator": "src/synth.py",
            "note": "合成数据仅用于流程验证，不可作为实验指标来源",
            "duration_min": round(minutes, 1),
            "samples": seconds,
        }
        path.with_suffix(".meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), "utf-8"
        )
        written += 1
    return written


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="生成合成波形（仅用于流程验证）")
    parser.add_argument("--out", type=Path, default=Path("data/raw"))
    parser.add_argument("--per-class", type=int, default=6)
    parser.add_argument("--classes", nargs="*", default=list(PROFILES))
    args = parser.parse_args(argv)

    total = 0
    for label in args.classes:
        if label not in PROFILES:
            print(f"[synth] 未知类别 {label}，可选：{list(PROFILES)}")
            continue
        n = generate_class(label, args.per_class, args.out)
        print(f"[synth] {label:<20} 生成 {n} 段")
        total += n
    print(f"[synth] 共 {total} 段，输出目录 {args.out}")
    print("[synth] 提醒：合成数据不得写进方案的实验指标")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
