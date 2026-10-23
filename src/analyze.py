"""数据分析：清洗、重采样、特征提取、可视化。

用法::

    python -m src.analyze --plot                 # 生成各类负载的功率曲线对比图
    python -m src.analyze --features data/processed/segments.csv   # 导出特征表

输入：``data/raw/<label>/*.csv``（由 ``src.collect`` 生成）
输出：
- ``data/processed/segments.csv``    每段（每份采集文件一个窗口）的特征
- ``data/processed/curves_<label>.png`` 各类负载典型曲线
- ``data/processed/compare.png``     四类负载叠加对比图
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
import pandas as pd

RAW_DIR = Path("data") / "raw"
PROCESSED_DIR = Path("data") / "processed"

# 采集文件里我们关心的列
NUMERIC_COLS = ["voltage", "current", "power", "energy", "frequency", "power_factor"]

# 每段取前 N 分钟做特征窗口（充电器典型平台期较长，取 30 分钟）
DEFAULT_WINDOW_MIN = 30.0


# --------------------------------------------------------------------------
# 数据加载
# --------------------------------------------------------------------------
def load_file(path: Path) -> pd.DataFrame:
    """读一份采集 CSV，补齐时间列并去重排序。"""
    df = pd.read_csv(path)
    if "elapsed_s" not in df.columns:
        raise ValueError(f"{path} 缺少 elapsed_s 列")
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["elapsed_s", "power"]).sort_values("elapsed_s")
    df = df.drop_duplicates(subset=["elapsed_s"], keep="last")
    # 丢掉明显离群的尖峰（>10 倍中位数且只出现一次），避免接触抖动干扰
    med = df["power"].median()
    if med > 0:
        df = df[df["power"] <= med * 10]
    return df.reset_index(drop=True)


def load_all(raw_dir: Path = RAW_DIR) -> dict[str, list[pd.DataFrame]]:
    """返回 {label: [DataFrame, ...]}。"""
    result: dict[str, list[pd.DataFrame]] = {}
    if not raw_dir.exists():
        return result
    for label_dir in sorted(p for p in raw_dir.iterdir() if p.is_dir()):
        frames = []
        for csv_path in sorted(label_dir.glob("*.csv")):
            try:
                frames.append(load_file(csv_path))
            except Exception as exc:  # 单文件坏了不影响整体
                print(f"[analyze] 跳过 {csv_path}: {exc}")
        if frames:
            result[label_dir.name] = frames
    return result


# --------------------------------------------------------------------------
# 重采样
# --------------------------------------------------------------------------
def resample(df: pd.DataFrame, interval_s: float = 1.0) -> pd.DataFrame:
    """按固定时间网格重采样，线性插值，保证各段可比。"""
    if df.empty:
        return df
    grid = np.arange(0.0, df["elapsed_s"].max(), interval_s)
    if grid.size == 0:
        return df
    out = pd.DataFrame({"elapsed_s": grid})
    for col in NUMERIC_COLS:
        if col in df.columns:
            out[col] = np.interp(grid, df["elapsed_s"].to_numpy(), df[col].to_numpy())
    return out


def window(df: pd.DataFrame, minutes: float) -> pd.DataFrame:
    """截取前 N 分钟。"""
    limit = minutes * 60.0
    return df[df["elapsed_s"] <= limit]


# --------------------------------------------------------------------------
# 特征提取（每个采集文件一段）
# --------------------------------------------------------------------------
def extract_features(df: pd.DataFrame, label: str, source: str) -> dict:
    """从一段曲线提取用于分类的统计与形态特征。

    设计依据（充电器 vs 大功率电器 vs 正常）：
    - 充电器：功率阶跃上升后进入**长时恒功率平台**，功率因数中等且稳定，谐波三次占比偏高；
    - 电热水壶：短时高功率、到温后**突降归零**，功率因数接近 1；
    - 吹风机：功率随档位**频繁跳变**，方差大；
    - 正常（待机/小电器）：功率低且平稳。
    """
    p = df["power"].to_numpy(dtype=float)
    n = p.size
    if n < 5:
        return {}

    mean_p = float(np.mean(p))
    std_p = float(np.std(p))
    max_p = float(np.max(p))
    min_p = float(np.min(p))
    p95 = float(np.percentile(p, 95))
    p05 = float(np.percentile(p, 5))

    # 平台度：接近中位数的样本占比（充电器很高）
    med = float(np.median(p))
    plateau_ratio = float(np.mean(np.abs(p - med) <= max(5.0, 0.05 * max(med, 1.0))))

    # 阶跃强度：一阶差分的最大正向跳变 / 峰值
    diff = np.diff(p)
    step_up = float(np.max(diff)) if diff.size else 0.0
    step_ratio = step_up / max_p if max_p > 0 else 0.0

    # 波动性：标准差 / 均值（吹风机高）
    cv = std_p / mean_p if mean_p > 1.0 else 0.0

    # 高功率占比与持续时间
    high = p >= max(50.0, 0.5 * p95)
    high_ratio = float(np.mean(high))
    # 最长连续高功率时长（秒）
    longest, current = 0, 0
    for flag in high:
        current = current + 1 if flag else 0
        longest = max(longest, current)

    # 功率因数
    pf = df["power_factor"].to_numpy(dtype=float) if "power_factor" in df else np.array([0.0])
    pf_mean = float(np.nanmean(pf))
    pf_std = float(np.nanstd(pf))

    # 三次谐波指标（用电流的简单过零间隔近似不够准，这里用功率因数的稳定性替代，
    # 真正谐波需更高采样率；保留字段便于后续替换）
    return {
        "label": label,
        "source": source,
        "n_samples": int(n),
        "duration_s": float(df["elapsed_s"].max()),
        "mean_power": round(mean_p, 2),
        "std_power": round(std_p, 2),
        "max_power": round(max_p, 2),
        "min_power": round(min_p, 2),
        "p95_power": round(p95, 2),
        "p05_power": round(p05, 2),
        "plateau_ratio": round(plateau_ratio, 4),
        "step_ratio": round(step_ratio, 4),
        "cv": round(cv, 4),
        "high_ratio": round(high_ratio, 4),
        "longest_high_s": int(longest),
        "pf_mean": round(pf_mean, 3),
        "pf_std": round(pf_std, 4),
        "mean_voltage": round(float(np.nanmean(df["voltage"])), 2),
    }


def build_feature_table(
    data: dict[str, list[pd.DataFrame]],
    window_min: float = DEFAULT_WINDOW_MIN,
    out_path: Path = PROCESSED_DIR / "segments.csv",
) -> pd.DataFrame:
    rows = []
    for label, frames in data.items():
        for i, df in enumerate(frames):
            seg = window(resample(df), window_min)
            feats = extract_features(seg, label, source=f"{label}/{i}")
            if feats:
                rows.append(feats)
    table = pd.DataFrame(rows)
    if not table.empty:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        table.to_csv(out_path, index=False)
        print(f"[analyze] 特征表 -> {out_path}（{len(table)} 段）")
    return table


# --------------------------------------------------------------------------
# 可视化
# --------------------------------------------------------------------------
def plot_each(data: dict[str, list[pd.DataFrame]], out_dir: Path = PROCESSED_DIR) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]

    for idx, (label, frames) in enumerate(sorted(data.items())):
        fig, ax = plt.subplots(figsize=(10, 3.5))
        for j, df in enumerate(frames[:6]):  # 每类最多画 6 段，避免太乱
            seg = window(resample(df), DEFAULT_WINDOW_MIN)
            ax.plot(seg["elapsed_s"] / 60.0, seg["power"], lw=1.0,
                    color=colors[idx % len(colors)], alpha=0.55 if j else 0.95,
                    label=label if j == 0 else None)
        ax.set_xlabel("elapsed (min)")
        ax.set_ylabel("power (W)")
        ax.set_title(f"{label} — power curve")
        ax.grid(True, alpha=0.3)
        if len(frames) > 1:
            ax.legend([label])
        path = out_dir / f"curves_{label}.png"
        fig.tight_layout()
        fig.savefig(path, dpi=140)
        plt.close(fig)
        print(f"[analyze] 曲线图 -> {path}")


def plot_compare(data: dict[str, list[pd.DataFrame]], out_dir: Path = PROCESSED_DIR) -> None:
    """把所有标签的典型曲线叠在一张图上（方案书里最好用的一张图）。"""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if not data:
        print("[analyze] 没有数据，跳过对比图")
        return
    out_dir.mkdir(parents=True, exist_ok=True)
    labels = sorted(data)
    fig, axes = plt.subplots(len(labels), 1, figsize=(11, 2.2 * len(labels)), sharex=True)
    if len(labels) == 1:
        axes = [axes]
    for ax, label in zip(axes, labels):
        frames = data[label]
        # 选峰值最接近该标签中位数的那段作为"典型"
        peaks = [float(f["power"].max()) for f in frames]
        target = float(np.median(peaks))
        pick = frames[int(np.argmin([abs(pk - target) for pk in peaks]))]
        seg = window(resample(pick), DEFAULT_WINDOW_MIN)
        ax.plot(seg["elapsed_s"] / 60.0, seg["power"], lw=1.4)
        ax.set_ylabel(f"{label}\n(W)")
        ax.grid(True, alpha=0.3)
        ax.set_ylim(bottom=0)
    axes[-1].set_xlabel("elapsed (min)")
    fig.suptitle("Power-curve signature by load type", fontsize=12)
    fig.tight_layout()
    path = out_dir / "compare.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    print(f"[analyze] 对比图 -> {path}")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="波形清洗、特征与可视化")
    parser.add_argument("--raw", type=Path, default=RAW_DIR, help="原始数据目录")
    parser.add_argument("--plot", action="store_true", help="生成曲线图")
    parser.add_argument("--features", nargs="?", const=str(PROCESSED_DIR / "segments.csv"),
                        help="导出特征表（可选路径）")
    parser.add_argument("--window-min", type=float, default=DEFAULT_WINDOW_MIN)
    args = parser.parse_args(argv)

    data = load_all(args.raw)
    if not data:
        print(f"[analyze] {args.raw} 下没有可用数据，先去采集吧。")
        return 1

    print(f"[analyze] 载入 {len(data)} 类共 {sum(len(v) for v in data.values())} 段数据")
    for label, frames in sorted(data.items()):
        durations = [f["elapsed_s"].max() / 60 for f in frames]
        print(f"  - {label:<20} {len(frames):>2} 段，时长 {min(durations):.1f}–{max(durations):.1f} 分钟")

    if args.features:
        build_feature_table(data, args.window_min, Path(args.features))
    if args.plot:
        plot_each(data)
        plot_compare(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
