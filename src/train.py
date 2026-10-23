"""训练基线分类模型并输出可复现的指标。

用法::

    python -m src.train                        # 用 data/processed/segments.csv
    python -m src.train --leave-one-out        # 留一法（样本少时更可信）
    python -m src.train --save-model

产出：::

    data/processed/metrics.json
    data/processed/confusion_matrix.png
    data/processed/models/model.joblib        # 仅 --save-model
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

FEATURE_COLS = [
    "mean_power",
    "std_power",
    "max_power",
    "min_power",
    "p95_power",
    "p05_power",
    "plateau_ratio",
    "step_ratio",
    "cv",
    "high_ratio",
    "longest_high_s",
    "pf_mean",
    "pf_std",
    "mean_voltage",
]

# 初赛阶段先做「三类」：充电 / 大功率电器 / 正常
# 后续数据够了再细分到具体电器
CLASS_GROUPS = {
    "e_bike_charger": "charging",
    "charger": "charging",
    "kettle": "high_power",
    "hair_dryer": "high_power",
    "aircon": "high_power",
    "heater": "high_power",
    "normal": "normal",
    "standby": "normal",
}

TARGET = "group"


def load_features(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df[TARGET] = df["label"].map(lambda x: CLASS_GROUPS.get(str(x).lower(), "other"))
    df = df[df[TARGET] != "other"].reset_index(drop=True)
    missing = [c for c in FEATURE_COLS if c not in df.columns]
    df = df.dropna(subset=[c for c in FEATURE_COLS if c in df.columns])
    if missing:
        print(f"[train] 警告：缺少特征列 {missing}")
    return df


def _estimator():
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    return Pipeline(
        [
            ("scaler", StandardScaler()),
            (
                "clf",
                RandomForestClassifier(
                    n_estimators=300,
                    max_depth=6,
                    min_samples_leaf=1,
                    random_state=42,
                    class_weight="balanced",
                ),
            ),
        ]
    )


def leave_one_out(df: pd.DataFrame) -> dict:
    """留一交叉验证：样本少时比随机划分诚实得多。"""
    from sklearn.metrics import accuracy_score, confusion_matrix, f1_score

    X = df[FEATURE_COLS].to_numpy(dtype=float)
    y = df[TARGET].to_numpy()
    preds = []
    for i in range(len(df)):
        train_mask = np.ones(len(df), dtype=bool)
        train_mask[i] = False
        model = _estimator()
        model.fit(X[train_mask], y[train_mask])
        preds.append(model.predict(X[i : i + 1])[0])

    labels = sorted(set(y))
    cm = confusion_matrix(y, preds, labels=labels)
    return {
        "protocol": "leave-one-out",
        "n_samples": int(len(df)),
        "accuracy": round(float(accuracy_score(y, preds)), 4),
        "macro_f1": round(float(f1_score(y, preds, average="macro")), 4),
        "labels": labels,
        "confusion_matrix": cm.tolist(),
        "per_class_recall": {
            lab: round(float(cm[j, j] / cm[j].sum()), 4) if cm[j].sum() else None
            for j, lab in enumerate(labels)
        },
    }


def holdout(df: pd.DataFrame, test_ratio: float = 0.3) -> dict:
    """随机留出法（每类至少留 1 个测试样本）。"""
    from sklearn.metrics import accuracy_score, confusion_matrix, f1_score
    from sklearn.model_selection import train_test_split

    X = df[FEATURE_COLS].to_numpy(dtype=float)
    y = df[TARGET].to_numpy()
    n_classes = len(set(y))
    if len(df) < n_classes * 2:
        raise SystemExit(
            f"[train] 样本太少（{len(df)} 段 / {n_classes} 类），"
            "请先采更多数据，或改用 --leave-one-out"
        )
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=test_ratio, random_state=42, stratify=y
    )
    model = _estimator()
    model.fit(X_tr, y_tr)
    pred = model.predict(X_te)
    labels = sorted(set(y))
    cm = confusion_matrix(y_te, pred, labels=labels)
    result = {
        "protocol": f"holdout({int((1 - test_ratio) * 100)}/{int(test_ratio * 100)})",
        "n_samples": int(len(df)),
        "n_train": int(len(X_tr)),
        "n_test": int(len(X_te)),
        "accuracy": round(float(accuracy_score(y_te, pred)), 4),
        "macro_f1": round(float(f1_score(y_te, pred, average="macro")), 4),
        "labels": labels,
        "confusion_matrix": cm.tolist(),
        "per_class_recall": {
            lab: round(float(cm[j, j] / cm[j].sum()), 4) if cm[j].sum() else None
            for j, lab in enumerate(labels)
        },
    }
    return result, model


def plot_confusion(result: dict, out_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cm = np.array(result["confusion_matrix"])
    labels = result["labels"]
    fig, ax = plt.subplots(figsize=(5, 4))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(labels)), labels, rotation=30, ha="right")
    ax.set_yticks(range(len(labels)), labels)
    ax.set_xlabel("predicted")
    ax.set_ylabel("true")
    ax.set_title(f"confusion matrix · accuracy={result['accuracy']:.2%}")
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(j, i, int(cm[i, j]), ha="center", va="center",
                    color="white" if cm[i, j] > cm.max() / 2 else "black")
    fig.colorbar(im, ax=ax, shrink=0.8)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"[train] 混淆矩阵 -> {out_path}")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="基线分类器训练与评估")
    parser.add_argument("--features", type=Path, default=Path("data/processed/segments.csv"))
    parser.add_argument("--leave-one-out", action="store_true", help="用留一法评估")
    parser.add_argument("--save-model", action="store_true", help="保存训练好的模型")
    args = parser.parse_args(argv)

    if not args.features.exists():
        print(f"[train] 找不到 {args.features}，先运行 python -m src.analyze --features")
        return 1

    df = load_features(args.features)
    if df.empty:
        print("[train] 特征表为空。")
        return 1

    print(f"[train] 样本 {len(df)} 段，类别分布：\n{df[TARGET].value_counts().to_string()}")

    model = None
    if args.leave_one_out:
        result = leave_one_out(df)
        model = _estimator().fit(df[FEATURE_COLS].to_numpy(float), df[TARGET].to_numpy())
    else:
        result, model = holdout(df)

    result["features"] = FEATURE_COLS
    result["classes"] = sorted(df[TARGET].unique())

    out = Path("data/processed/metrics.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf-8")
    print(f"[train] 指标 -> {out}")
    print(json.dumps({k: v for k, v in result.items() if k != "confusion_matrix"},
                     ensure_ascii=False, indent=2))

    plot_confusion(result, Path("data/processed/confusion_matrix.png"))

    if args.save_model and model is not None:
        try:
            import joblib
        except ImportError:
            print("[train] 未安装 joblib，跳过保存模型。")
            return 0
        model_path = Path("data/processed/models/model.joblib")
        model_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"model": model, "features": FEATURE_COLS, "target": TARGET}, model_path)
        print(f"[train] 模型 -> {model_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
