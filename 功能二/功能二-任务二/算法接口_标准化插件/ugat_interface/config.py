"""Configuration with the official frozen UGAT defaults exposed as fields."""
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Mapping


@dataclass
class UGATConfig:
    input_dim: int = 16
    hidden_dim: int = 20
    action_dim: int = 8
    adapter_hidden: int = 20
    learning_rate: float = 0.001
    gamma: float = 0.95
    epsilon: float = 0.10
    epsilon_min: float = 0.01
    epsilon_decay: float = 0.995
    seed: int = 20260806
    device: str = "cpu"
    deterministic: bool = True

    def __post_init__(self) -> None:
        if self.input_dim <= 0 or self.hidden_dim <= 0 or self.action_dim <= 0:
            raise ValueError("input_dim, hidden_dim and action_dim must be positive")
        if not 0 <= self.epsilon_min <= self.epsilon <= 1:
            raise ValueError("epsilon_min <= epsilon <= 1 is required")
        if not 0 < self.epsilon_decay <= 1 or self.learning_rate <= 0:
            raise ValueError("epsilon_decay must be in (0,1] and learning_rate must be positive")

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "UGATConfig":
        names = {f.name for f in fields(cls)}
        aliases = {
            "output_dim": "action_dim", "random_seed": "seed",
            "official_learning_rate": "learning_rate", "official_gamma": "gamma",
            "official_epsilon": "epsilon", "official_epsilon_min": "epsilon_min",
            "official_epsilon_decay": "epsilon_decay",
        }
        data = {}
        for key, value in values.items():
            key = aliases.get(key, key)
            if key in names:
                data[key] = value
        return cls(**data)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "UGATConfig":
        """Read the simple key/value official YAML without requiring PyYAML."""
        values: dict[str, Any] = {}
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue
            key, raw = (part.strip() for part in line.split(":", 1))
            if raw.lower() in {"true", "false"}:
                value: Any = raw.lower() == "true"
            else:
                try:
                    value = float(raw) if any(c in raw for c in ".eE") else int(raw)
                except ValueError:
                    value = raw.strip("'\"")
            values[key] = value
        return cls.from_mapping(values)
