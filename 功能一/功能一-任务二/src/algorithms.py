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
    def __init__(self, count: int, phase_hold_decisions: int = 3, phase_offset: int = 0, phase_order: tuple[int, ...] = tuple(range(8))): self.count = count; self.step = 0; self.phase_hold_decisions = phase_hold_decisions; self.phase_offset = phase_offset; self.phase_order = phase_order
    def choose(self, states: np.ndarray) -> np.ndarray:
        # The roadnet has eight controllable green phases (plus clearance at index 0).
        # Cycle all eight phases so the baseline cannot starve half of the movements.
        action = np.full(self.count, self.phase_order[(self.phase_offset + self.step // self.phase_hold_decisions) % 8], dtype=np.int64); self.step += 1; return action


class CoordinatedFixedAlgorithm(SignalAlgorithm):
    """Fixed green cycle with topology-based offsets for progression testing."""
    name = "coordinated_fixed"
    def __init__(self, positions: list[list[int]], hold_decisions: int = 1, offset_scale: int = 3):
        self.step=0; self.hold=hold_decisions
        self.offsets=np.asarray([(int(pos[0])+int(pos[1]))*offset_scale for pos in positions],dtype=np.int64)%8
    def choose(self, states: np.ndarray) -> np.ndarray:
        actions=((self.offsets + self.step//self.hold)%8).astype(np.int64); self.step+=1; return actions


class MaxPressureAlgorithm(SignalAlgorithm):
    name = "max_pressure"
    # collect_state order is [WL, WT, WR, EL, ET, ER, NL, NT, NR, SL, ST, SR].
    ACTION_LANES = ((1, 4), (7, 10), (0, 3), (6, 9), (0, 1), (3, 4), (9, 10), (6, 7))
    def choose(self, states: np.ndarray) -> np.ndarray:
        demand = states[:, :12]
        score = np.stack([demand[:, pair].sum(axis=1) for pair in self.ACTION_LANES], axis=1)
        return score.argmax(axis=1).astype(np.int64)


class ActuatedPressureAlgorithm(SignalAlgorithm):
    """Pressure control with a green hold to avoid 10-second phase chatter."""
    name = "actuated_pressure"
    ACTION_LANES = MaxPressureAlgorithm.ACTION_LANES

    def __init__(self, count: int, min_green_decisions: int = 2, max_green_decisions: int = 6, switch_ratio: float = 1.10):
        self.current = np.zeros(count, dtype=np.int64)
        self.age = np.zeros(count, dtype=np.int64)
        self.min_green = min_green_decisions; self.max_green = max_green_decisions; self.switch_ratio = switch_ratio

    def choose(self, states: np.ndarray) -> np.ndarray:
        demand = states[:, :12]
        score = np.stack([demand[:, pair].sum(axis=1) for pair in self.ACTION_LANES], axis=1)
        best = score.argmax(axis=1).astype(np.int64); current_score = score[np.arange(len(states)), self.current]; best_score = score[np.arange(len(states)), best]
        can_switch = (self.age >= self.min_green) & ((best_score > current_score * self.switch_ratio) | (self.age >= self.max_green))
        actions = np.where(can_switch, best, self.current)
        self.age = np.where(actions == self.current, self.age + 1, 0); self.current = actions
        return actions
