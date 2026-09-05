"""Frozen UGAT checkpoint and C-MP controller for the CityFlow Atlanta 1x5 network.

The C-MP implementation follows Ahmed et al. (2024): each permitted lane
movement receives an upstream moving-platoon bonus and a downstream
moving-platoon discount. UGAT parameters are loaded strictly and frozen; its
Q-values are logged as a reference diagnostic but do not modify C-MP actions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import numpy as np
import torch
from torch import nn
import torch.nn.functional as F


class FrozenUGAT(nn.Module):
    """Architecture matching the supplied heterogeneous UGAT state dict."""

    def __init__(self, checkpoint: str, rank: int, input_dim: int, action_dim: int):
        super().__init__()
        self.dense_1 = nn.Linear(input_dim, 20)
        self.dense_2 = nn.Linear(20, 20)
        self.dense_3 = nn.Linear(20, action_dim)
        all_states = torch.load(checkpoint, map_location="cpu", weights_only=True)
        state = all_states[str(rank)]
        if set(state) != set(self.state_dict()):
            raise RuntimeError(f"UGAT checkpoint key mismatch at rank {rank}")
        self.load_state_dict(state, strict=True)
        for parameter in self.parameters():
            parameter.requires_grad = False
        self.eval()

    @torch.no_grad()
    def forward(self, x: torch.Tensor, train: bool = False) -> torch.Tensor:
        return self.dense_3(F.relu(self.dense_2(F.relu(self.dense_1(x)))))


class TrainableUGATResidual(nn.Module):
    """Trainable residual adapter; the supplied UGAT network remains frozen."""

    def __init__(self, checkpoint: str, rank: int, input_dim: int, action_dim: int, residual_limit: float = 0.25):
        super().__init__()
        self.ugat = FrozenUGAT(checkpoint, rank, input_dim, action_dim)
        self.adapter = nn.Sequential(
            nn.Linear(input_dim, 32), nn.ReLU(), nn.Linear(32, action_dim)
        )
        self.residual_limit = float(residual_limit)
        # Start exactly at the frozen UGAT policy, then learn only the residual.
        nn.init.zeros_(self.adapter[-1].weight)
        nn.init.zeros_(self.adapter[-1].bias)

    def forward(self, x: torch.Tensor, train: bool = True) -> torch.Tensor:
        base = self.ugat(x, train=False)
        # A bounded residual protects the already-trained UGAT policy from a
        # single unstable Q target during early CityFlow exploration.
        residual = self.residual(x)
        return base + residual

    def residual(self, x: torch.Tensor) -> torch.Tensor:
        return self.residual_limit * torch.tanh(self.adapter(x))


class FRAPResidualAdapter(nn.Module):
    """Phase-aware residual adapter for the C-MP-FRAP hybrid.

    The frozen UGAT branch is retained only as a reference. The trainable
    branch encodes a scale-robust traffic state, current phase, and candidate
    phase embeddings, producing a bounded residual score per candidate action.
    The frozen UGAT branch still receives the original observation unchanged.
    """

    def __init__(self, checkpoint: str, rank: int, input_dim: int, action_dim: int, residual_limit: float = 0.25):
        super().__init__()
        self.ugat = FrozenUGAT(checkpoint, rank, input_dim, action_dim)
        self.action_dim = int(action_dim)
        self.ob_dim = int(input_dim - action_dim)
        if self.ob_dim <= 0:
            raise ValueError(f"FRAP requires observation features before phase one-hot, got input_dim={input_dim}, action_dim={action_dim}")
        self.state_schema = "log1p_relative_saturation_v1"
        self.adapter = nn.ModuleDict({
            "state_encoder": nn.Sequential(nn.Linear(self.ob_dim * 3, 64), nn.ReLU(), nn.Linear(64, 32), nn.ReLU()),
            "phase_encoder": nn.Sequential(nn.Linear(self.action_dim, 16), nn.ReLU()),
            "context_query": nn.Linear(48, 32),
        })
        # Start at an exactly neutral phase preference.  The joint policy is
        # therefore identical to C-MP until FRAP obtains gradient updates.
        phase_relation = nn.Parameter(torch.zeros(self.action_dim, 32))
        self.adapter.register_parameter("phase_relation", phase_relation)
        self.residual_limit = float(residual_limit)

    def forward(self, x: torch.Tensor, train: bool = True) -> torch.Tensor:
        return self.ugat(x, train=False) + self.residual(x)

    def residual(self, x: torch.Tensor) -> torch.Tensor:
        state = x[..., :self.ob_dim]
        phase = x[..., self.ob_dim:self.ob_dim + self.action_dim]
        # CityFlow lane counts have a wide dynamic range.  These three
        # deterministic views preserve lane ordering while exposing absolute
        # demand, local imbalance, and saturation to FRAP.  UGAT is untouched.
        nonnegative_state = torch.clamp(state, min=0.0)
        log_counts = torch.log1p(nonnegative_state)
        local_mean = nonnegative_state.mean(dim=-1, keepdim=True)
        relative_load = (nonnegative_state - local_mean) / (local_mean + 1.0)
        saturation = torch.tanh(nonnegative_state / 10.0)
        frap_state = torch.cat([log_counts, relative_load, saturation], dim=-1)
        context = torch.cat([self.adapter["state_encoder"](frap_state), self.adapter["phase_encoder"](phase)], dim=-1)
        query = torch.tanh(self.adapter["context_query"](context))
        scores = torch.matmul(query, self.adapter.phase_relation.t()) / np.sqrt(32.0)
        return self.residual_limit * torch.tanh(scores)


def pressure_prior_fusion(residual_scores: np.ndarray, pressures: np.ndarray, weight: float) -> np.ndarray:
    """Fuse bounded FRAP residuals with a scale-independent C-MP pressure prior."""
    residual_scores = np.asarray(residual_scores, dtype=np.float32)
    pressures = np.asarray(pressures, dtype=np.float32)
    if len(residual_scores) != len(pressures):
        raise ValueError("FRAP residual and C-MP pressure action dimensions must match")
    spread = float(np.max(pressures) - np.min(pressures))
    normalized_pressure = np.zeros_like(pressures) if spread < 1e-6 else (pressures - np.min(pressures)) / spread
    return residual_scores + float(weight) * normalized_pressure


def cmp_frap_phase_fusion(
    frap_scores: np.ndarray,
    pressures: np.ndarray,
    downstream_mean: np.ndarray,
    downstream_max: np.ndarray,
    pressure_weight: float,
    frap_weight: float,
    downstream_weight: float,
    max_downstream_lane_count: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Build one joint C-MP-FRAP score for every candidate phase.

    This is deliberately not a C-MP action followed by an adapter override.
    C-MP contributes coordinated pressure, FRAP contributes learned phase
    relations, and downstream occupancy contributes a congestion risk term to
    the same candidate-phase ranking.  Only physically unsafe phases are
    masked; minimum-green handling remains the controller's hard constraint.
    """
    arrays = [np.asarray(values, dtype=np.float32) for values in (frap_scores, pressures, downstream_mean, downstream_max)]
    if len({len(values) for values in arrays}) != 1:
        raise ValueError("C-MP-FRAP fusion inputs must have the same action dimension")

    def normalize(values: np.ndarray) -> np.ndarray:
        low = float(np.min(values))
        width = float(np.max(values) - low)
        return np.zeros_like(values) if width < 1e-6 else (values - low) / width

    frap, pressure, mean_load, max_load = arrays
    # FRAP already has a fixed output range [-0.25, 0.25].  Per-decision
    # min-max normalization here would amplify random initialization noise to
    # [0, 1], causing arbitrary phase changes before training.
    bounded_frap = np.clip(frap / 0.25, -1.0, 1.0)
    joint = (
        float(pressure_weight) * normalize(pressure)
        + float(frap_weight) * bounded_frap
        - float(downstream_weight) * normalize(mean_load)
    )
    feasible = max_load <= float(max_downstream_lane_count)
    # A deadlock-safe fallback: if every candidate exceeds the absolute limit,
    # retain all phases and let the joint score select the least-congested one.
    if not np.any(feasible):
        feasible = np.ones_like(feasible, dtype=bool)
    return joint.astype(np.float32), feasible


def pressure_trust_region(pressures: np.ndarray, maximum_regret: float) -> np.ndarray:
    """Keep joint optimization inside C-MP's near-optimal pressure set.

    The mask is a constraint on the joint argmax, not a second-stage override:
    FRAP still ranks every admissible phase.  It prevents a learned local score
    from selecting a phase with materially lower network pressure.
    """
    values = np.asarray(pressures, dtype=np.float32)
    if values.size == 0:
        raise ValueError("pressure trust region requires at least one phase")
    low = float(np.min(values))
    spread = float(np.max(values) - low)
    normalized = np.zeros_like(values) if spread < 1e-6 else (values - low) / spread
    return normalized >= float(np.max(normalized) - maximum_regret)


@dataclass
class CMPDiagnostics:
    decisions: int = 0
    ugat_agreements: int = 0
    score_mse: List[float] = field(default_factory=list)
    normalized_score_mse: List[float] = field(default_factory=list)
    phase_pressure: List[float] = field(default_factory=list)
    upstream_speed_ratio: List[float] = field(default_factory=list)
    downstream_speed_ratio: List[float] = field(default_factory=list)

    def summary(self) -> Dict[str, float]:
        mean = lambda values: float(np.mean(values)) if values else 0.0
        return {
            "decisions": self.decisions,
            "ugat_agreement_rate": self.ugat_agreements / self.decisions if self.decisions else 0.0,
            "cmp_ugat_score_mse": mean(self.score_mse),
            "cmp_ugat_normalized_score_mse": mean(self.normalized_score_mse),
            "mean_selected_phase_pressure": mean(self.phase_pressure),
            "mean_upstream_speed_ratio": mean(self.upstream_speed_ratio),
            "mean_downstream_speed_ratio": mean(self.downstream_speed_ratio),
        }


class CMPController:
    """Decentralized coordinated max-pressure controller at one intersection."""

    def __init__(self, world, intersection, beta: float, alpha: float, min_green: int):
        self.world = world
        self.intersection = intersection
        self.beta = float(beta)
        self.alpha = float(alpha)
        self.min_green = int(min_green)
        self.diagnostics = CMPDiagnostics()

    def _lane_speed_ratio(self, lane: str, lane_vehicles: Dict[str, List[str]], vehicle_speeds: Dict[str, float]) -> float:
        vehicles = lane_vehicles.get(lane, [])
        if not vehicles:
            return 0.0
        free_flow = max(float(self.world.all_lanes_speed.get(lane, 0.0)), 1e-6)
        mean_speed = float(np.mean([max(0.0, float(vehicle_speeds.get(vehicle, 0.0))) for vehicle in vehicles]))
        return float(np.clip(mean_speed / free_flow, 0.0, 1.0))

    def phase_pressures(self) -> Tuple[np.ndarray, float, float]:
        lane_count = self.world.get_info("lane_count")
        lane_vehicles = self.world.get_info("lane_vehicles")
        try:
            vehicle_speeds = self.world.eng.get_vehicle_speed()
        except Exception:
            vehicle_speeds = {}
        scores = []
        up_ratios, down_ratios = [], []
        for lane_links in self.intersection.phase_available_lanelinks:
            pressure = 0.0
            for upstream, downstream in lane_links:
                up_count = float(lane_count.get(upstream, 0.0))
                down_count = float(lane_count.get(downstream, 0.0))
                up_ratio = self._lane_speed_ratio(upstream, lane_vehicles, vehicle_speeds)
                down_ratio = self._lane_speed_ratio(downstream, lane_vehicles, vehicle_speeds)
                # C-MP Eq. (6), with turning proportion 1 for an explicit lane-link.
                pressure += up_count * (1.0 + self.beta * up_ratio)
                pressure -= down_count * (1.0 - self.alpha * down_ratio)
                up_ratios.append(up_ratio)
                down_ratios.append(down_ratio)
            scores.append(pressure)
        return np.asarray(scores, dtype=np.float32), (float(np.mean(up_ratios)) if up_ratios else 0.0), (float(np.mean(down_ratios)) if down_ratios else 0.0)

    def phase_downstream_loads(self) -> Tuple[np.ndarray, np.ndarray]:
        """Return mean and maximum downstream lane vehicle counts per phase."""
        lane_count = self.world.get_info("lane_count")
        means, maximums = [], []
        for lane_links in self.intersection.phase_available_lanelinks:
            downstream_lanes = {downstream for _, downstream in lane_links}
            counts = [float(lane_count.get(lane, 0.0)) for lane in downstream_lanes]
            means.append(float(np.mean(counts)) if counts else 0.0)
            maximums.append(float(np.max(counts)) if counts else 0.0)
        return np.asarray(means, dtype=np.float32), np.asarray(maximums, dtype=np.float32)

    def choose(self, ugat_q: np.ndarray) -> int:
        action, _, _ = self.choose_with_details(ugat_q)
        return action

    @staticmethod
    def _normalize_phase_scores(scores: np.ndarray) -> np.ndarray:
        """Normalize one decision's phase scores for a scale-independent diagnostic."""
        low = float(np.min(scores))
        width = float(np.max(scores) - low)
        if width <= 1e-6:
            return np.zeros_like(scores, dtype=np.float32)
        return ((scores - low) / width).astype(np.float32)

    def choose_with_details(self, ugat_q: np.ndarray) -> Tuple[int, float, bool]:
        """Return C-MP action, pressure margin, and whether a change is allowed."""
        # Do not interrupt an active green before its minimum duration.
        if self.intersection.current_phase_time < self.min_green:
            return int(self.intersection.current_phase), float("inf"), False
        pressures, up_ratio, down_ratio = self.phase_pressures()
        cmp_action = int(np.argmax(pressures))
        ugat_action = int(np.argmax(ugat_q))
        # Keep the diagnostic in the original score units. It is not trained and
        # is intentionally not normalized to [0, 1].
        if len(pressures) > 1:
            n = min(len(pressures), len(ugat_q))
            self.diagnostics.score_mse.append(float(np.mean((pressures[:n] - ugat_q[:n]) ** 2)))
            normalized_pressure = self._normalize_phase_scores(pressures[:n])
            normalized_ugat = self._normalize_phase_scores(ugat_q[:n])
            self.diagnostics.normalized_score_mse.append(
                float(np.mean((normalized_pressure - normalized_ugat) ** 2))
            )
        self.diagnostics.decisions += 1
        self.diagnostics.ugat_agreements += int(cmp_action == ugat_action)
        self.diagnostics.phase_pressure.append(float(pressures[cmp_action]))
        self.diagnostics.upstream_speed_ratio.append(up_ratio)
        self.diagnostics.downstream_speed_ratio.append(down_ratio)
        if len(pressures) < 2:
            return cmp_action, float("inf"), True
        sorted_pressures = np.sort(pressures)
        return cmp_action, float(sorted_pressures[-1] - sorted_pressures[-2]), True
