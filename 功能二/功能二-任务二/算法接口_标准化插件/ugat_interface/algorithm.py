"""UGAT policy facade: stable NumPy boundary around the frozen PyTorch model."""
from pathlib import Path
from typing import Any
import numpy as np
from .config import UGATConfig
from .contract import AlgorithmContext
from .model import build_model, _torch


class UGATAlgorithm:
    name = "ugat"

    def __init__(self, checkpoint: str | Path, config: UGATConfig | None = None,
                 adapter_checkpoint: str | Path | None = None):
        self.config = config or UGATConfig()
        self.context = AlgorithmContext()
        torch, _, _ = _torch()
        self._torch = torch
        self.model = build_model(checkpoint, self.config.input_dim, self.config.hidden_dim,
                                 self.config.action_dim, self.config.adapter_hidden,
                                 self.config.device, adapter_checkpoint)
        self.rng = np.random.default_rng(self.config.seed)

    def _observation(self, observation: Any):
        array = np.asarray(observation, dtype=np.float32)
        single = array.ndim == 1
        if single:
            array = array[None, :]
        if array.ndim != 2 or array.shape[1] != self.config.input_dim:
            raise ValueError(f"observation must have shape [{self.config.input_dim}] or [N,{self.config.input_dim}], got {array.shape}")
        if not np.isfinite(array).all():
            raise ValueError("observation contains NaN or infinity")
        return self._torch.from_numpy(array).to(self.config.device), single

    def q_values(self, observation: Any) -> np.ndarray:
        x, _ = self._observation(observation)
        with self._torch.no_grad():
            values = self.model(x).detach().cpu().numpy()
        return values

    def choose_action(self, observation: Any, *, explore: bool = False) -> int | np.ndarray:
        x, single = self._observation(observation)
        with self._torch.no_grad():
            q = self.model(x).detach().cpu().numpy()
        actions = np.argmax(q, axis=1).astype(np.int64)
        if explore and self.config.epsilon > 0:
            mask = self.rng.random(len(actions)) < self.config.epsilon
            actions[mask] = self.rng.integers(0, self.config.action_dim, size=int(mask.sum()))
        self.context.step += 1
        return int(actions[0]) if single else actions

    act = choose_action

    def update(self, observation: Any, action: Any, reward: Any, next_observation: Any, done: Any = False) -> dict[str, float]:
        """Hook for a trainer; the frozen inference facade deliberately does not optimize weights."""
        return {"updated": 0.0, "reason": "frozen_model"}

    def reset(self) -> None:
        self.context = AlgorithmContext()
