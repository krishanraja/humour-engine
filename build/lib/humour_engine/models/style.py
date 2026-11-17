"""Source-specific humour-style classifiers (MaryKenneth five-class label space).

Independent implementation. Two variants on identical features:
- single:       one five-class classifier.
- hierarchical: a four-class gate (affiliative+aggressive merged) and a binary
                affiliative-vs-aggressive specialist, composed softly:
                P(se)=G0, P(sd)=G1, P(af)=G2*B0, P(ag)=G2*B1, P(ne)=G3.
The full distribution is always computed (no hard-routing shortcuts, no
threshold relabelling). These are social-function predictions for one dataset's
labels; they are not a comprehension result.
"""

from __future__ import annotations

import hashlib
import json
import pickle
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion

from humour_engine.contracts.analysis import StylePrediction, Uncertainty

FINAL = ["self-enhancing", "self-deprecating", "affiliative", "aggressive", "neutral"]
FINAL_TO_GATE = {0: 0, 1: 1, 2: 2, 3: 2, 4: 3}
BINARY_TO_FINAL = {0: 2, 1: 3}


def features() -> FeatureUnion:
    return FeatureUnion(
        [
            ("word", TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)),
            ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=2, sublinear_tf=True)),
        ]
    )


def _lr(C: float, seed: int) -> LogisticRegression:
    return LogisticRegression(C=C, max_iter=3000, random_state=seed)


def _full_proba(clf: LogisticRegression, X, n_classes: int) -> np.ndarray:
    """Probability matrix aligned to class ids 0..n-1 even if a class was absent in training."""
    p = clf.predict_proba(X)
    out = np.zeros((X.shape[0], n_classes))
    for j, c in enumerate(clf.classes_):
        out[:, int(c)] = p[:, j]
    return out


def compose_hierarchical(gate: np.ndarray, binary: np.ndarray) -> np.ndarray:
    """Soft composition into the five-class space. Rows sum to 1 when inputs do."""
    if gate.shape[1] != 4 or binary.shape[1] != 2 or gate.shape[0] != binary.shape[0]:
        raise ValueError("gate must be (n,4) and binary (n,2)")
    out = np.zeros((gate.shape[0], 5))
    out[:, 0] = gate[:, 0]
    out[:, 1] = gate[:, 1]
    out[:, 2] = gate[:, 2] * binary[:, 0]
    out[:, 3] = gate[:, 2] * binary[:, 1]
    out[:, 4] = gate[:, 3]
    return out


def temper(p: np.ndarray, T: float) -> np.ndarray:
    logp = np.log(np.clip(p, 1e-12, 1)) / T
    logp -= logp.max(axis=1, keepdims=True)
    e = np.exp(logp)
    return e / e.sum(axis=1, keepdims=True)


def fit_temperature(p: np.ndarray, y: np.ndarray) -> float:
    def nll(T):
        q = temper(p, T)
        return -np.mean(np.log(np.clip(q[np.arange(len(y)), y], 1e-12, 1)))

    return float(minimize_scalar(nll, bounds=(0.05, 20), method="bounded").x)


@dataclass
class StyleModel:
    variant: str  # "single" | "hierarchical"
    C: float
    seed: int = 13
    vec: FeatureUnion | None = None
    clf: LogisticRegression | None = None
    gate: LogisticRegression | None = None
    binary: LogisticRegression | None = None
    temperature: float | None = None
    calibration_ref: str | None = None
    train_manifest_seal: str | None = None
    meta: dict = field(default_factory=dict)

    @property
    def model_id(self) -> str:
        return f"style-{self.variant}-C{self.C}-{(self.train_manifest_seal or 'unsealed')[:8]}"

    def fit(self, texts: list[str], y: list[int]) -> StyleModel:
        y = np.asarray(y)
        self.vec = features()
        X = self.vec.fit_transform(texts)
        if self.variant == "single":
            self.clf = _lr(self.C, self.seed).fit(X, y)
        elif self.variant == "hierarchical":
            g = np.array([FINAL_TO_GATE[int(v)] for v in y])
            self.gate = _lr(self.C, self.seed).fit(X, g)
            mask = np.isin(y, [2, 3])
            if mask.sum() == 0 or len(set(y[mask])) < 2:
                raise ValueError("specialist needs both affiliative and aggressive training examples")
            yb = np.where(y[mask] == 2, 0, 1)
            self.binary = _lr(self.C, self.seed).fit(X[mask], yb)
        else:
            raise ValueError(f"unknown variant {self.variant}")
        return self

    def raw_proba(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 5))
        X = self.vec.transform(texts)
        if self.variant == "single":
            return _full_proba(self.clf, X, 5)
        return compose_hierarchical(_full_proba(self.gate, X, 4), _full_proba(self.binary, X, 2))

    def predict_proba(self, texts: list[str]) -> np.ndarray:
        """Full inference path used by evaluation, the engine and attribution alike."""
        p = self.raw_proba(texts)
        return temper(p, self.temperature) if self.temperature else p

    def calibrate(self, texts: list[str], y: list[int], ref: str) -> None:
        self.temperature = fit_temperature(self.raw_proba(texts), np.asarray(y))
        self.calibration_ref = ref

    def predict_one(self, text: str) -> StylePrediction:
        p = self.predict_proba([text])[0]
        k = int(np.argmax(p))
        calibrated = self.temperature is not None
        return StylePrediction(
            model=self.model_id,
            label_namespace="mk5",
            distribution={FINAL[i]: round(float(p[i]), 4) for i in range(5)},
            predicted=FINAL[k],
            uncertainty=Uncertainty(
                score=round(float(p[k]), 4),
                score_kind="calibrated_probability" if calibrated else "uncalibrated_model_score",
                calibration_ref=self.calibration_ref if calibrated else None,
            ),
            limitations=[
                "Trained on one dataset's five style labels (MaryKenneth); scope is that label space only.",
                "'neutral' in this namespace means a non-humorous control text.",
                "Says nothing about the speaker's personality.",
            ],
        )

    def save(self, path: Path) -> str:
        path.parent.mkdir(parents=True, exist_ok=True)
        blob = pickle.dumps(self)
        path.write_bytes(blob)
        digest = hashlib.sha256(blob).hexdigest()
        path.with_suffix(".json").write_text(
            json.dumps({"model_id": self.model_id, "sha256": digest, "meta": self.meta}, indent=1)
        )
        return digest

    @staticmethod
    def load(path: Path) -> StyleModel:
        """Load only a locally produced artifact whose digest matches its sidecar."""
        side = json.loads(path.with_suffix(".json").read_text())
        blob = path.read_bytes()
        if hashlib.sha256(blob).hexdigest() != side["sha256"]:
            raise ValueError("style model artifact digest mismatch; refusing to load")
        return pickle.loads(blob)  # noqa: S301 - digest-verified local artifact
