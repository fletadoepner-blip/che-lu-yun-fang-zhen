"""Lazy PyTorch implementation of the frozen official network and adapter."""
from pathlib import Path
from typing import Any


def _torch():
    try:
        import torch
        from torch import nn
        import torch.nn.functional as F
        return torch, nn, F
    except ImportError as exc:
        raise RuntimeError("UGAT inference requires PyTorch; install torch in the runtime environment") from exc


def build_model(checkpoint: str | Path, input_dim: int = 16, hidden_dim: int = 20,
                action_dim: int = 8, adapter_hidden: int = 20, device: str = "cpu",
                adapter_checkpoint: str | Path | None = None):
    torch, nn, F = _torch()

    class Net(nn.Module):
        def __init__(self):
            super().__init__()
            self.dense_1 = nn.Linear(input_dim, hidden_dim)
            self.dense_2 = nn.Linear(hidden_dim, hidden_dim)
            self.dense_3 = nn.Linear(hidden_dim, action_dim)
            self.adapter = nn.Sequential(nn.Linear(action_dim, adapter_hidden), nn.ReLU(), nn.Linear(adapter_hidden, action_dim))
            # No adapter checkpoint means exact official-backbone inference.
            for layer in (self.adapter[0], self.adapter[2]):
                nn.init.zeros_(layer.weight)
                nn.init.zeros_(layer.bias)

        def forward(self, x):
            with torch.no_grad():
                base = self.dense_3(F.relu(self.dense_2(F.relu(self.dense_1(x)))))
            return base + self.adapter(base)

    model = Net().to(device)
    state = torch.load(Path(checkpoint), map_location=device, weights_only=True)
    base_keys = {"dense_1.weight", "dense_1.bias", "dense_2.weight", "dense_2.bias", "dense_3.weight", "dense_3.bias"}
    if set(state) != base_keys:
        raise RuntimeError(f"official checkpoint keys mismatch: expected {sorted(base_keys)}, got {sorted(state)}")
    model.load_state_dict({**state, **{k: v for k, v in model.state_dict().items() if k.startswith("adapter.")}}, strict=True)
    for name, parameter in model.named_parameters():
        parameter.requires_grad = name.startswith("adapter.")
    if adapter_checkpoint:
        adapter_state = torch.load(Path(adapter_checkpoint), map_location=device, weights_only=True)
        model.adapter.load_state_dict(adapter_state.get("adapter", adapter_state), strict=True)
    model.eval()
    return model
