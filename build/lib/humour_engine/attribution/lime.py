"""LIME-style local attribution for the locally queryable style model.

Explains the full inference path (features, classifier or gate+specialist composition,
temperature) through `StyleModel.predict_proba`. Records seed, sample count, kernel,
local surrogate fidelity (weighted R^2) and top-k stability across seeds.

This is model sensitivity under word removal. It is not a semantic explanation of the
joke and not evidence of why a person finds it funny.
"""

from __future__ import annotations

import re

import numpy as np
from sklearn.linear_model import Ridge

from humour_engine.contracts.analysis import Attribution
from humour_engine.models.style import FINAL

TOKEN = re.compile(r"\S+")


def _explain_once(model, text: str, target: int, n_samples: int, seed: int, kernel_width: float):
    words = TOKEN.findall(text)
    d = len(words)
    if d == 0:
        return words, np.zeros(0), None
    rng = np.random.default_rng(seed)
    Z = rng.integers(0, 2, size=(n_samples, d))
    Z[0] = 1
    texts = [" ".join(w for w, keep in zip(words, z, strict=True) if keep) for z in Z]
    y = model.predict_proba(texts)[:, target]
    dist = 1 - Z.sum(axis=1) / d  # fraction removed
    w = np.exp(-(dist**2) / kernel_width**2)
    reg = Ridge(alpha=1.0, random_state=seed).fit(Z, y, sample_weight=w)
    pred = reg.predict(Z)
    ss_res = np.sum(w * (y - pred) ** 2)
    ss_tot = np.sum(w * (y - np.average(y, weights=w)) ** 2)
    fidelity = float(1 - ss_res / ss_tot) if ss_tot > 0 else None
    return words, reg.coef_, fidelity


def explain(model, text: str, n_samples: int = 500, seed: int = 0, kernel_width: float = 0.25, k: int = 8, seeds: int = 3) -> Attribution:
    target = int(np.argmax(model.predict_proba([text])[0]))
    words, coef, fid = _explain_once(model, text, target, n_samples, seed, kernel_width)
    tops = []
    for s in range(seeds):
        _, c, _ = _explain_once(model, text, target, n_samples, seed + 101 * (s + 1), kernel_width)
        tops.append({int(i) for i in np.argsort(-np.abs(c))[:k]})
    base = {int(i) for i in np.argsort(-np.abs(coef))[:k]}
    stability = float(np.mean([len(base & t) / max(1, len(base | t)) for t in tops])) if tops else None
    order = np.argsort(-np.abs(coef))[:k]
    feats = [(f"{words[i]}#{i}", round(float(coef[i]), 4)) for i in order]
    lims = [
        "Sensitivity of one classifier to word removal; not a semantic explanation.",
        "Perturbed texts are often ungrammatical; attributions are diagnostic only.",
    ]
    if fid is not None and fid < 0.5:
        lims.append("Low local fidelity: the linear surrogate does not track the model well here.")
    return Attribution(
        model=getattr(model, "model_id", "style-model"),
        prediction=FINAL[target],
        method="lime_text_word_removal",
        features=feats,
        settings={"n_samples": n_samples, "seed": seed, "kernel_width": kernel_width, "surrogate": "ridge(alpha=1)", "stability_seeds": seeds},
        fidelity=None if fid is None else round(fid, 4),
        stability=None if stability is None else round(stability, 4),
        limitations=lims,
    )
