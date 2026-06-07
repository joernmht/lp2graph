"""Stage-2 calibrated linear SVM, one-vs-rest (M4).

A small, dependency-free linear classifier so the labeling service has no hard
ML dependency and stays bit-for-bit reproducible. Each class gets a linear
SVM (hinge loss + L2) trained by deterministic sub-gradient descent; the raw
margins are turned into per-class probabilities by a logistic squashing and
normalized across classes, giving the calibrated *confidence* the closed-loop
gates read.

Determinism: the feature axis is the sorted union of training keys, classes
are sorted, and the per-epoch example order is driven by a seeded
:class:`random.Random`. Same ``(data, seed, version)`` → same model.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from lp2graph.mining.versions import LABEL_LEXICON_VERSION


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


@dataclass(frozen=True, slots=True)
class LinearSVM:
    """A fitted one-vs-rest linear SVM with logistic calibration."""

    classes: tuple[str, ...]
    features: tuple[str, ...]
    weights: dict[str, tuple[float, ...]]
    biases: dict[str, float]
    calib_scale: float
    version: str

    @property
    def is_trained(self) -> bool:
        return bool(self.classes)

    @classmethod
    def train(
        cls,
        x: Sequence[Mapping[str, float]],
        y: Sequence[str],
        *,
        seed: int = 0,
        epochs: int = 50,
        lr: float = 0.1,
        reg: float = 0.01,
        calib_scale: float = 1.5,
        version: str = LABEL_LEXICON_VERSION,
    ) -> LinearSVM:
        """Train one linear SVM per class by deterministic sub-gradient descent."""
        if len(x) != len(y):
            raise ValueError("x and y must have equal length")
        feature_set: set[str] = set()
        for row in x:
            feature_set.update(row.keys())
        features = tuple(sorted(feature_set))
        classes = tuple(sorted(set(y)))
        f_index = {f: i for i, f in enumerate(features)}

        def vec(row: Mapping[str, float]) -> list[float]:
            out = [0.0] * len(features)
            for k, v in row.items():
                idx = f_index.get(k)
                if idx is not None:
                    out[idx] = v
            return out

        vectors = [vec(row) for row in x]
        weights: dict[str, tuple[float, ...]] = {}
        biases: dict[str, float] = {}
        rng = random.Random(seed)
        order = list(range(len(vectors)))

        for c in classes:
            w = [0.0] * len(features)
            b = 0.0
            targets = [1.0 if y[i] == c else -1.0 for i in range(len(y))]
            for _ in range(epochs):
                epoch_order = order[:]
                rng.shuffle(epoch_order)
                for i in epoch_order:
                    xi = vectors[i]
                    ti = targets[i]
                    margin = ti * (sum(wj * xj for wj, xj in zip(w, xi, strict=True)) + b)
                    if margin < 1.0:
                        for j in range(len(w)):
                            w[j] += lr * (ti * xi[j] - reg * w[j])
                        b += lr * ti
                    else:
                        for j in range(len(w)):
                            w[j] -= lr * reg * w[j]
            weights[c] = tuple(w)
            biases[c] = b

        return cls(
            classes=classes,
            features=features,
            weights=weights,
            biases=biases,
            calib_scale=calib_scale,
            version=version,
        )

    def _vec(self, row: Mapping[str, float]) -> list[float]:
        f_index = {f: i for i, f in enumerate(self.features)}
        out = [0.0] * len(self.features)
        for k, v in row.items():
            idx = f_index.get(k)
            if idx is not None:
                out[idx] = v
        return out

    def scores(self, row: Mapping[str, float]) -> dict[str, float]:
        """Raw decision margin per class."""
        x = self._vec(row)
        return {
            c: sum(wj * xj for wj, xj in zip(self.weights[c], x, strict=True)) + self.biases[c]
            for c in self.classes
        }

    def predict_proba(self, row: Mapping[str, float]) -> dict[str, float]:
        """Calibrated, normalized class probabilities."""
        if not self.classes:
            return {}
        if len(self.classes) == 1:
            return {self.classes[0]: 1.0}
        raw = self.scores(row)
        squashed = {c: _sigmoid(self.calib_scale * s) for c, s in raw.items()}
        total = sum(squashed.values())
        if total == 0.0:
            uniform = 1.0 / len(self.classes)
            return {c: uniform for c in self.classes}
        return {c: p / total for c, p in squashed.items()}

    def predict(self, row: Mapping[str, float]) -> tuple[str, float]:
        """Most probable class and its calibrated confidence.

        Returns ``("", 0.0)`` for an untrained model. Ties are broken by class
        name for determinism.
        """
        proba = self.predict_proba(row)
        if not proba:
            return ("", 0.0)
        # Deterministic: highest probability, ties broken by smallest class name.
        top = max(proba.values())
        best_label = min(c for c in proba if proba[c] == top)
        return (best_label, proba[best_label])


__all__ = ["LinearSVM"]
