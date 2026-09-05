from pathlib import Path
import os
import sys
import numpy as np

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from ugat_interface import UGATAlgorithm, UGATConfig

base = ROOT.parent / "UGAT" / "official_ugat_best.pt"
agent = UGATAlgorithm(base, UGATConfig())
q_values = agent.q_values([[0.0] * 16, [1.0] * 16])
action = agent.choose_action([0.0] * 16)
frozen = all(not parameter.requires_grad for name, parameter in agent.model.named_parameters() if not name.startswith("adapter."))
print("checkpoint", base)
print("q_shape", q_values.shape)
print("q_finite", bool(np.isfinite(q_values).all()))
print("action", action, "valid", 0 <= action < agent.config.action_dim)
print("backbone_frozen", frozen)
