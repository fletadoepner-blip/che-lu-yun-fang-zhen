"""Common algorithm adapter contract used by the CityFlow platform."""
from __future__ import annotations

from abc import ABC, abstractmethod
import numpy as np


class SignalAlgorithm(ABC):
    name: str
    @abstractmethod
    def choose(self, states: np.ndarray) -> np.ndarray: """Return one 0..7 phase action per controlled intersection."""


class FixedTimeAlgorithm(SignalAlgorithm):
    name = "fixed_time"
    def __init__(self, count: int): self.count = count; self.step = 0
    def choose(self, states: np.ndarray) -> np.ndarray:
        action = np.full(self.count, (self.step // 3) % 4, dtype=np.int64); self.step += 1; return action


class MaxPressureAlgorithm(SignalAlgorithm):
    name = "max_pressure"
    # The controller state order is [WL, WT, EL, ET, NL, NT, SL, ST, pad...].
    ACTION_LANES = ((1, 3), (5, 7), (0, 2), (4, 6), (0, 1), (2, 3), (6, 7), (4, 5))
    def choose(self, states: np.ndarray) -> np.ndarray:
        demand = states[:, :8]
        score = np.stack([demand[:, pair].sum(axis=1) for pair in self.ACTION_LANES], axis=1)
        return score.argmax(axis=1).astype(np.int64)
