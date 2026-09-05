import argparse
import csv
import json
import os
import shutil
import sys
import threading
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, "/DaRL/UGAT_Docker")
sys.path.insert(0, "/workspace/final")
import task, trainer, dataset, agent, torch  # noqa: E402,F401
from agent.dqn import DQNAgent as BaseDQN  # noqa: E402
from common.registry import Registry  # noqa: E402
from ugat_cmp_1x5 import CMPController, FrozenUGAT, TrainableUGATResidual, FRAPResidualAdapter, cmp_frap_phase_fusion, pressure_trust_region  # noqa: E402
import trainer.tsc_trainer as tsc  # noqa: E402
from agent import utils  # noqa: E402

METRIC_FIELDS = [
    "timestamp", "policy", "test_steps", "seed", "beta", "alpha", "travel_time",
    "throughput", "queue", "delay_ratio_apx", "rewards", "decisions",
    "ugat_agreement_rate", "cmp_ugat_score_mse", "cmp_ugat_normalized_score_mse", "mean_selected_phase_pressure",
    "mean_upstream_speed_ratio", "mean_downstream_speed_ratio",
    "adapter_decisions", "adapter_uncertain_decisions", "adapter_overrides", "adapter_downstream_vetoes",
]

CITYFLOW_CONFIG = Path("/DaRL/UGAT_Docker/configs/sim/cityflow_atlanta1x5.cfg")


def set_cityflow_seed(seed):
    """Inject the requested seed into CityFlow instead of only seeding PyTorch."""
    original = CITYFLOW_CONFIG.read_text(encoding="utf-8")
    config = json.loads(original)
    config["seed"] = int(seed)
    CITYFLOW_CONFIG.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return original


def safe_log(traj, lanes, fix_time=30):
    from collections import defaultdict
    max_i = max((int((r[0][1] + r[0][2] - 1) // fix_time) for r in traj.values() if r), default=119)
    rec = {i: defaultdict(int, {lane: 0 for lane in lanes}) for i in range(max(120, max_i + 1))}
    for record in traj.values():
        if record:
            rec[int((record[0][1] + record[0][2] - 1) // fix_time)][record[0][0]] += 1
    return rec


tsc.log_passing_lane_actinon = safe_log
ORIGINAL_TEST = tsc.TSCTrainer.test


def test_with_artifacts(self, drop_load=True):
    done = threading.Event()
    def heartbeat():
        elapsed = 0
        while not done.wait(30):
            elapsed += 30
            print(f"progress_heartbeat: wall_seconds={elapsed}, simulator_time={self.world.eng.get_current_time()}", flush=True)
    threading.Thread(target=heartbeat, daemon=True).start()
    try:
        result = ORIGINAL_TEST(self, drop_load=drop_load)
    finally:
        done.set()
    setting = Registry.mapping["model_mapping"]["setting"].param
    summaries = [agent.cmp.diagnostics.summary() for agent in self.agents if hasattr(agent, "cmp")]
    aggregate = {key: float(np.mean([item[key] for item in summaries])) if summaries else 0.0 for key in summaries[0]} if summaries else {}
    metrics = self.metric
    row = {
        "timestamp": datetime.now().isoformat(timespec="seconds"), "policy": setting["policy"],
        "test_steps": setting["test_steps"], "seed": setting["seed"], "beta": setting["cmp_beta"], "alpha": setting["cmp_alpha"],
        "travel_time": float(metrics.real_average_travel_time()), "throughput": float(metrics.throughput()),
        "queue": float(metrics.queue()), "delay_ratio_apx": float(metrics.delay()), "rewards": float(metrics.rewards()), **aggregate,
    }
    adapter_agents = [agent for agent in self.agents if hasattr(agent, "adapter_overrides")]
    row.update({
        "adapter_decisions": int(sum(agent.adapter_decisions for agent in adapter_agents)),
        "adapter_uncertain_decisions": int(sum(agent.adapter_uncertain_decisions for agent in adapter_agents)),
        "adapter_overrides": int(sum(agent.adapter_overrides for agent in adapter_agents)),
        "adapter_downstream_vetoes": int(sum(agent.adapter_downstream_vetoes for agent in adapter_agents)),
    })
    if setting["policy"] in {"cmp_adapter", "cmp_frap"}:
        print(
            f"adapter_inference_summary: decisions={row['adapter_decisions']}, "
            f"uncertain={row['adapter_uncertain_decisions']}, overrides={row['adapter_overrides']}, downstream_vetoes={row['adapter_downstream_vetoes']}",
            flush=True,
        )
    out = Path("/workspace/final/logs"); out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "1x5_cmp_simulation_metrics.csv"; exists = csv_path.exists()
    if exists:
        with csv_path.open(newline="", encoding="utf-8") as handle:
            existing_rows = list(csv.DictReader(handle))
            existing_fields = handle.seek(0) or next(csv.reader(handle), [])
        if existing_fields != METRIC_FIELDS:
            with csv_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=METRIC_FIELDS)
                writer.writeheader()
                writer.writerows(existing_rows)
    with csv_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=METRIC_FIELDS)
        if not exists: writer.writeheader()
        writer.writerow(row)
    (out / "1x5_cmp_latest_metrics.json").write_text(json.dumps(row, indent=2), encoding="utf-8")
    make_plots(csv_path, out)
    return result


def make_plots(csv_path, out):
    try:
        import matplotlib.pyplot as plt
        with csv_path.open(encoding="utf-8") as handle: rows = list(csv.DictReader(handle))
        if not rows: return
        x = range(1, len(rows) + 1)
        fig, axes = plt.subplots(2, 2, figsize=(10, 7))
        for axis, key, label in zip(axes.flat, ["travel_time", "throughput", "queue", "delay_ratio_apx"], ["Travel Time (s)", "Throughput", "Queue", "Approx. delay ratio"]):
            axis.plot(x, [float(row[key]) for row in rows], marker="o")
            axis.set_xlabel("run"); axis.set_ylabel(label); axis.grid(alpha=0.3)
        fig.tight_layout(); fig.savefig(out / "1x5_cmp_simulation_metrics.png", dpi=160); plt.close(fig)
        fig, axis = plt.subplots(figsize=(7, 4))
        axis.plot(x, [float(row["cmp_ugat_score_mse"]) for row in rows], marker="o", color="#B04A30")
        axis.set_xlabel("run"); axis.set_ylabel("Raw C-MP / UGAT score MSE\n(diagnostic; arbitrary score squared)"); axis.grid(alpha=0.3)
        fig.tight_layout(); fig.savefig(out / "1x5_cmp_raw_score_mse_diagnostic.png", dpi=160); plt.close(fig)
    except Exception as exc:
        print(f"plot_warning={exc}")


tsc.TSCTrainer.test = test_with_artifacts


@Registry.register_model("cmp1x5")
class CMP1x5Agent(BaseDQN):
    def __init__(self, world, rank):
        super().__init__(world, rank)
        setting = Registry.mapping["model_mapping"]["setting"].param
        self.rank = rank
        self.ugat = FrozenUGAT("/workspace/final/model/ugat1x5_best.pt", rank, self.ob_length, self.action_space.n)
        self.model = self.ugat
        self.target_model = self.ugat
        self.adapter_model = None
        self.adapter_decisions = 0
        self.adapter_uncertain_decisions = 0
        self.adapter_overrides = 0
        self.adapter_downstream_vetoes = 0
        adapter_dir = setting.get("adapter_dir", "")
        if adapter_dir:
            checkpoint_name = f"best_rank_{rank}.pt" if setting.get("use_best_adapter", False) else f"episode_{setting['adapter_episode']}_rank_{rank}.pt"
            adapter_checkpoint = os.path.join(adapter_dir, checkpoint_name)
            if not os.path.exists(adapter_checkpoint):
                if setting.get("use_best_adapter", False):
                    raise FileNotFoundError("No adapter checkpoint passed the formal baseline gate; run policy=cmp, or continue training until Travel Time/queue/delay all qualify.")
                raise FileNotFoundError(f"trained adapter checkpoint not found: {adapter_checkpoint}")
            adapter_cls = FRAPResidualAdapter if setting.get("policy") == "cmp_frap" else TrainableUGATResidual
            self.adapter_model = adapter_cls("/workspace/final/model/ugat1x5_best.pt", rank, self.ob_length, self.action_space.n)
            checkpoint = torch.load(adapter_checkpoint, map_location="cpu", weights_only=True)
            if int(checkpoint["rank"]) != rank:
                raise RuntimeError(f"adapter checkpoint rank mismatch: expected {rank}")
            if setting.get("policy") == "cmp_frap" and checkpoint.get("state_schema") != self.adapter_model.state_schema:
                raise RuntimeError("FRAP checkpoint uses an obsolete state schema. Train a new adapter; do not mix it with the updated FRAP architecture.")
            if setting.get("policy") == "cmp_frap" and checkpoint.get("policy_schema") != "joint_cmp_frap_v2":
                raise RuntimeError("FRAP checkpoint predates the joint C-MP-FRAP policy. Train a new adapter; legacy override checkpoints are not valid for the fused policy.")
            self.adapter_model.adapter.load_state_dict(checkpoint["adapter"], strict=True)
            self.adapter_model.eval()
            print(f"loaded_trained_adapter_rank={rank}, checkpoint={adapter_checkpoint}", flush=True)
        # C-MP requires the per-lane vehicle IDs in addition to UGAT's counts.
        self.world.subscribe(["lane_vehicles"])
        self.cmp = CMPController(world, self.inter, setting["cmp_beta"], setting["cmp_alpha"], setting["t_min"])
        frozen = sum(parameter.numel() for parameter in self.ugat.parameters())
        print(f"frozen_ugat_rank={rank}, frozen_parameters={frozen}, trainable_parameters=0")

    def load_model(self, e, customized_path=""):
        print("skip_legacy_dqn_load=true")

    def reset(self):
        super().reset()
        self.adapter_decisions = 0
        self.adapter_uncertain_decisions = 0
        self.adapter_overrides = 0
        self.adapter_downstream_vetoes = 0

    def get_action(self, ob, phase, test=True):
        if self.phase and self.one_hot:
            feature = np.concatenate([ob, utils.idx2onehot(phase, self.action_space.n)], axis=1)
        elif self.phase:
            feature = np.concatenate([ob, phase], axis=1)
        else:
            feature = ob
        with torch.no_grad():
            ugat_q = self.ugat(torch.tensor(feature, dtype=torch.float32)).numpy()[0]
        policy = Registry.mapping["model_mapping"]["setting"].param["policy"]
        if policy == "ugat":
            return np.asarray([int(np.argmax(ugat_q))])
        if policy == "adapter":
            if self.adapter_model is None:
                raise RuntimeError("policy=adapter requires --adapter_checkpoint")
            with torch.no_grad():
                adapted_q = self.adapter_model.residual(torch.tensor(feature, dtype=torch.float32)).numpy()[0]
            return np.asarray([int(np.argmax(adapted_q))])
        if policy == "cmp_legacy_adapter":
            if self.adapter_model is None:
                raise RuntimeError("policy=cmp_legacy_adapter requires legacy adapter checkpoints")
            cmp_action, pressure_margin, can_change = self.cmp.choose_with_details(ugat_q)
            self.adapter_decisions += 1
            with torch.no_grad():
                adapted_q = self.adapter_model.residual(torch.tensor(feature, dtype=torch.float32)).numpy()[0]
            candidate = int(np.argmax(adapted_q))
            advantage = float(adapted_q[candidate] - adapted_q[cmp_action])
            is_uncertain = pressure_margin <= float(Registry.mapping["model_mapping"]["setting"].param["cmp_uncertainty_margin"])
            self.adapter_uncertain_decisions += int(is_uncertain)
            if can_change and is_uncertain and candidate != cmp_action and advantage >= float(Registry.mapping["model_mapping"]["setting"].param["override_advantage"]):
                self.adapter_overrides += 1
                return np.asarray([candidate])
            return np.asarray([cmp_action])
        if policy in {"cmp_adapter", "cmp_frap"}:
            if self.adapter_model is None:
                raise RuntimeError("policy=cmp_adapter requires trained adapter checkpoints")
            cmp_action, _, can_change = self.cmp.choose_with_details(ugat_q)
            self.adapter_decisions += 1
            with torch.no_grad():
                adapted_q = self.adapter_model.residual(torch.tensor(feature, dtype=torch.float32)).numpy()[0]
            setting = Registry.mapping["model_mapping"]["setting"].param
            pressures, _, _ = self.cmp.phase_pressures()
            downstream_mean, downstream_max = self.cmp.phase_downstream_loads()
            fused_scores, feasible = cmp_frap_phase_fusion(adapted_q, pressures, downstream_mean, downstream_max, float(setting["pressure_weight"]), float(setting["frap_weight"]), float(setting["downstream_weight"]), float(setting["max_downstream_lane_count"]))
            feasible &= pressure_trust_region(pressures, float(setting["max_normalized_pressure_regret"]))
            feasible[cmp_action] = True
            fused_scores = fused_scores.copy()
            fused_scores[np.arange(len(fused_scores)) != cmp_action] -= float(setting["action_deviation_penalty"])
            candidate = int(np.argmax(np.where(feasible, fused_scores, -np.inf)))
            self.adapter_uncertain_decisions += int(candidate != cmp_action)
            self.adapter_downstream_vetoes += int(not feasible[int(np.argmax(fused_scores))])
            if can_change and candidate != cmp_action:
                self.adapter_overrides += 1
            return np.asarray([candidate if can_change else cmp_action])
        return np.asarray([self.cmp.choose(ugat_q)])


def main():
    parser = argparse.ArgumentParser(description="Frozen UGAT + C-MP CityFlow evaluator for the 1x5 network")
    parser.add_argument("--thread_num", type=int, default=4)
    parser.add_argument("--seed", type=int, default=4444)
    parser.add_argument("--prefix", default="1x5_cmp_9000")
    parser.add_argument("--test_steps", type=int, default=9000)
    parser.add_argument("--policy", choices=["cmp", "ugat", "adapter", "cmp_adapter", "cmp_frap", "cmp_legacy_adapter"], default="cmp")
    parser.add_argument("--beta", type=float, default=0.60, help="upstream platoon bonus, non-negative")
    parser.add_argument("--alpha", type=float, default=0.60, help="downstream platoon discount in [0, 1]")
    parser.add_argument("--adapter_dir", default="/workspace/final/logs/cmp_frap_checkpoints", help="directory containing episode_<N>_rank_<R>.pt")
    parser.add_argument("--adapter_episode", type=int, default=-1, help="trained adapter episode to evaluate with policy=adapter")
    parser.add_argument("--use_best_adapter", action="store_true", help="load best_rank_<R>.pt selected by gated training")
    parser.add_argument("--cmp_uncertainty_margin", type=float, default=2.0, help="adapter gate: C-MP top-two pressure gap must be at most this value")
    parser.add_argument("--override_advantage", type=float, default=0.05, help="minimum adapter Q advantage required to replace C-MP")
    parser.add_argument("--pressure_prior_weight", type=float, default=0.0, help="C-MP normalized pressure contribution in FRAP candidate ranking")
    parser.add_argument("--max_pressure_regret", type=float, default=2.0, help="maximum C-MP pressure loss allowed for a FRAP override")
    parser.add_argument("--max_downstream_mean_increase", type=float, default=0.0, help="maximum candidate downstream mean load above C-MP action")
    parser.add_argument("--max_downstream_lane_count", type=float, default=15.0, help="absolute downstream lane vehicle-count veto threshold")
    parser.add_argument("--max_override_rate", type=float, default=0.02, help="maximum fraction of decisions the FRAP policy may replace")
    parser.add_argument("--pressure_weight", type=float, default=1.00, help="joint C-MP-FRAP score weight for normalized C-MP pressure")
    parser.add_argument("--frap_weight", type=float, default=0.08, help="joint C-MP-FRAP score weight for bounded learned FRAP phase relation")
    parser.add_argument("--downstream_weight", type=float, default=0.00, help="joint C-MP-FRAP score penalty weight for downstream mean occupancy")
    parser.add_argument("--max_normalized_pressure_regret", type=float, default=0.03, help="joint action may be at most this normalized C-MP pressure below the best phase")
    parser.add_argument("--action_deviation_penalty", type=float, default=0.005, help="joint-score regularizer charged to a phase different from C-MP's pressure optimum")
    args = parser.parse_args()
    if args.beta < 0 or not 0 <= args.alpha <= 1:
        parser.error("--beta must be non-negative and --alpha must be in [0, 1]")
    if args.policy in {"adapter", "cmp_adapter", "cmp_frap", "cmp_legacy_adapter"} and args.adapter_episode < 0 and not args.use_best_adapter:
        parser.error("adapter policies require --adapter_episode >= 0")
    if args.cmp_uncertainty_margin < 0 or args.override_advantage < 0 or args.pressure_prior_weight < 0 or args.max_pressure_regret < 0 or args.max_downstream_mean_increase < 0 or args.max_downstream_lane_count < 0 or not 0 <= args.max_normalized_pressure_regret <= 1 or args.action_deviation_penalty < 0 or args.pressure_weight < 0 or args.frap_weight < 0 or args.downstream_weight < 0 or args.pressure_weight + args.frap_weight + args.downstream_weight <= 0 or not 0 <= args.max_override_rate <= 1:
        parser.error("gating thresholds must be non-negative")
    shutil.copyfile("/workspace/final/configs/cmp1x5.yml", "/DaRL/UGAT_Docker/configs/tsc/cmp1x5.yml")
    cityflow_original = set_cityflow_seed(args.seed)
    old_argv = sys.argv
    sys.argv = ["run_cmp_1x5.py", "-t", "tsc", "-a", "cmp1x5", "-w", "cityflow", "-n", "cityflow_atlanta1x5", "-d", "onfly", "--thread_num", str(args.thread_num), "--seed", str(args.seed), "--prefix", args.prefix, "--interface", "libsumo", "--delay_type", "apx"]
    try:
        from run import Runner
        ns = argparse.Namespace(thread_num=args.thread_num, ngpu="-1", prefix=args.prefix, seed=args.seed, debug=False, interface="libsumo", delay_type="apx", task="tsc", agent="cmp1x5", world="cityflow", network="cityflow_atlanta1x5", dataset="onfly")
        runner = Runner(ns)
        model_setting = Registry.mapping["model_mapping"]["setting"].param
        model_setting.update({"policy": args.policy, "cmp_beta": args.beta, "cmp_alpha": args.alpha, "test_steps": args.test_steps, "seed": args.seed, "adapter_dir": args.adapter_dir if args.policy in {"adapter", "cmp_adapter", "cmp_frap", "cmp_legacy_adapter"} else "", "adapter_episode": args.adapter_episode, "use_best_adapter": args.use_best_adapter, "cmp_uncertainty_margin": args.cmp_uncertainty_margin, "override_advantage": args.override_advantage, "pressure_prior_weight": args.pressure_prior_weight, "max_pressure_regret": args.max_pressure_regret, "max_downstream_mean_increase": args.max_downstream_mean_increase, "max_downstream_lane_count": args.max_downstream_lane_count, "max_override_rate": args.max_override_rate, "pressure_weight": args.pressure_weight, "frap_weight": args.frap_weight, "downstream_weight": args.downstream_weight, "max_normalized_pressure_regret": args.max_normalized_pressure_regret, "action_deviation_penalty": args.action_deviation_penalty})
        runner.config["trainer"]["test_steps"] = args.test_steps
        Registry.mapping["trainer_mapping"]["setting"].param["test_steps"] = args.test_steps
        if args.policy in {"adapter", "cmp_adapter", "cmp_frap", "cmp_legacy_adapter"}:
            print("training_enabled=false, reason=loading_trained_adapter_for_evaluation", flush=True)
        else:
            print("training_enabled=false, reason=frozen_UGAT_and_deterministic_C-MP_test_mode", flush=True)
        print(f"protocol: policy={args.policy}, beta={args.beta}, alpha={args.alpha}, test_steps={args.test_steps}, seed={args.seed}", flush=True)
        runner.run()
    finally:
        sys.argv = old_argv
        CITYFLOW_CONFIG.write_text(cityflow_original, encoding="utf-8")


if __name__ == "__main__":
    main()
