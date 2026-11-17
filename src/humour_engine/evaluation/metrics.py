"""Metrics with explicit denominators and item-level uncertainty."""

from __future__ import annotations

import numpy as np


def confusion(y: np.ndarray, yhat: np.ndarray, k: int) -> np.ndarray:
    m = np.zeros((k, k), dtype=int)
    for a, b in zip(y, yhat, strict=True):
        m[int(a), int(b)] += 1
    return m


def per_class(y: np.ndarray, yhat: np.ndarray, labels: list[str]) -> dict:
    k = len(labels)
    m = confusion(y, yhat, k)
    out = {}
    for i, name in enumerate(labels):
        tp = m[i, i]
        fp = m[:, i].sum() - tp
        fn = m[i, :].sum() - tp
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        f = 2 * p * r / (p + r) if p + r else 0.0
        out[name] = {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f, 4), "support": int(m[i, :].sum())}
    return out


def macro_f1(y: np.ndarray, yhat: np.ndarray, k: int) -> float:
    pc = per_class(y, yhat, [str(i) for i in range(k)])
    return float(np.mean([v["f1"] for v in pc.values()]))


def micro_f1(y, yhat) -> float:
    return float(np.mean(np.asarray(y) == np.asarray(yhat)))


def brier(p: np.ndarray, y: np.ndarray) -> float:
    onehot = np.eye(p.shape[1])[y]
    return float(np.mean(np.sum((p - onehot) ** 2, axis=1)))


def reliability(p: np.ndarray, y: np.ndarray, bins: int = 10) -> dict:
    conf = p.max(axis=1)
    correct = p.argmax(axis=1) == y
    edges = np.linspace(0, 1, bins + 1)
    rows, ece = [], 0.0
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        m = (conf > lo) & (conf <= hi)
        if m.sum():
            acc, c = float(correct[m].mean()), float(conf[m].mean())
            ece += m.mean() * abs(acc - c)
            rows.append({"bin": f"{lo:.1f}-{hi:.1f}", "n": int(m.sum()), "accuracy": round(acc, 4), "confidence": round(c, 4)})
    return {"ece": round(float(ece), 4), "bins": rows}


def paired_bootstrap(y, pred_a, pred_b, k: int, groups=None, n: int = 2000, seed: int = 7) -> dict:
    """CI for macro-F1(b) - macro-F1(a), resampling independent groups (items or families)."""
    rng = np.random.default_rng(seed)
    y, pa, pb = map(np.asarray, (y, pred_a, pred_b))
    groups = np.arange(len(y)) if groups is None else np.asarray(groups)
    uniq = np.unique(groups)
    idx_by = {g: np.where(groups == g)[0] for g in uniq}
    diffs = []
    for _ in range(n):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        idx = np.concatenate([idx_by[g] for g in pick])
        diffs.append(macro_f1(y[idx], pb[idx], k) - macro_f1(y[idx], pa[idx], k))
    diffs = np.asarray(diffs)
    point = macro_f1(y, pb, k) - macro_f1(y, pa, k)
    return {
        "point": round(float(point), 4),
        "ci95": [round(float(np.percentile(diffs, 2.5)), 4), round(float(np.percentile(diffs, 97.5)), 4)],
        "n_groups": int(len(uniq)),
        "resamples": n,
    }


def coverage_error_curve(conf: np.ndarray, correct: np.ndarray) -> list[dict]:
    order = np.argsort(-conf)
    out = []
    for cov in (0.5, 0.6, 0.7, 0.8, 0.9, 1.0):
        m = max(1, int(round(cov * len(conf))))
        sel = order[:m]
        out.append({"coverage": cov, "n": int(m), "error": round(float(1 - correct[sel].mean()), 4)})
    return out
