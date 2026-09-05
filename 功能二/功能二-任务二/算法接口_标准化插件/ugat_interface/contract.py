"""Small stable contract implemented by every external traffic algorithm."""
from dataclasses import dataclass, field
from typing import Any, Protocol
import numpy as np


@dataclass
class AlgorithmContext:
    step: int = 0
    episode: int = 0
    extras: dict[str, Any] = field(default_factory=dict)


class Algorithm(Protocol):
    name: str

    def choose_action(self, observation: Any, *, explore: bool = False) -> int | np.ndarray: ...
    def update(self, observation: Any, action: Any, reward: Any, next_observation: Any, done: Any = False) -> dict[str, float]: ...
    def reset(self) -> None: ...
