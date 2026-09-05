import argparse
import copy
import csv
import json
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import torch
from torch import optim
import torch.nn.functional as F
from torch.nn.utils import clip_grad_norm_

sys.path.insert(0, "/DaRL/UGAT_Docker")
sys.path.insert(0, "/workspace/final")
import task, trainer, dataset, agent  # noqa: F401,E402
from agent.dqn import DQNAgent as BaseDQN  # noqa: E402
from agent import utils  # noqa: E402
from common.registry import Registry  # noqa: E402
from ugat_cmp_1x5 import CMPController, TrainableUGATResidual  # noqa: E402
import trainer.tsc_trainer as tsc  # noqa: E402

CITYFLOW_CONFIG = Path("/DaRL/UGAT_Docker/configs/sim/cityflow_atlanta1x5.cfg")
ORIGINAL_TRAIN_TEST = tsc.TSCTrainer.train_test
BASELINE_TRAVEL_TIME = 1019.0248733302626
BASELINE_QUEUE = 8.264222145080566
BASELINE_DELAY = 0.14652371406555176
CANDIDATE_QUEUE_LIMIT = 1.05
CANDIDATE_DELAY_LIMIT = 1.05
LOSS_PLOT_MAX = 1_000_000.0
LOSS_PLOT_SAMPLE_LIMIT = 5_000


def adapter_candidate_score(travel_time, queue, delay):
    """Score an exploratory continuation candidate without relaxing formal gates."""
    return (
        0.60 * travel_time / BASELINE_TRAVEL_TIME
        + 0.25 * queue / BASELINE_QUEUE
        + 0.15 * delay / BASELINE_DELAY
    )


def read_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_training_loss_plot():
    """Plot the actual Huber optimization loss on a fixed, comparable scale."""
    loss_path = Path("/workspace/final/logs/cmp_training_loss.csv")
    if not loss_path.exists():
        return
    try:
        import matplotlib.pyplot as plt
        by_rank = {}
        raw_values = []
        with loss_path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if not row.get("loss") or not row.get("rank"):
                    continue
                loss = float(row["loss"])
                if not np.isfinite(loss) or loss < 0:
                    continue
                rank = int(row["rank"])
                by_rank.setdefault(rank, []).append(loss)
                raw_values.append(loss)
        if not raw_values:
            return
        fig, axis = plt.subplots(figsize=(9, 4.8))
        for rank, values in sorted(by_rank.items()):
            stride = max(1, int(np.ceil(len(values) / LOSS_PLOT_SAMPLE_LIMIT)))
            indices = np.arange(0, len(values), stride)
            axis.plot(indices, np.asarray(values)[indices], linewidth=0.8, label=f"rank {rank}")
        axis.set_yscale("symlog", linthresh=1.0, linscale=1.0)
        axis.set_ylim(0.0, LOSS_PLOT_MAX)
        axis.set_xlabel("optimizer update within rank (uniformly sampled)")
        axis.set_ylabel("Actual adapter Huber loss\n(fixed symlog scale: 0 to 1e6)")
        axis.grid(alpha=0.3, which="both")
        axis.legend(ncol=5, fontsize=8)
        above_limit = sum(value > LOSS_PLOT_MAX for value in raw_values)
        if above_limit:
            axis.text(0.01, 0.02, f"{above_limit} raw losses exceed 1e6 and are clipped by the fixed display limit", transform=axis.transAxes, fontsize=8)
        fig.tight_layout()
        output = Path("/workspace/final/logs/1x5_cmp_adapter_huber_loss.png")
        fig.savefig(output, dpi=160)
        plt.close(fig)
        summary = {
            "loss_name": "smooth_l1_loss (Huber)",
            "raw_min": float(min(raw_values)), "raw_max": float(max(raw_values)),
            "valid_updates": len(raw_values), "display_scale": "symlog", "display_ymin": 0.0,
            "display_ymax": LOSS_PLOT_MAX, "values_above_display_limit": above_limit,
        }
        Path("/workspace/final/logs/1x5_cmp_adapter_huber_loss_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    except Exception as exc:
        print(f"training_loss_plot_warning={exc}", flush=True)


def independently_validate_adapter(episode):
    """Run a fresh CityFlow process before allowing a checkpoint to become formal best."""
    setting = Registry.mapping["model_mapping"]["setting"].param
    checkpoint_dir = Path("/workspace/final/logs/legacy_cmp_adapter_train")
    cmd = [
        sys.executable, "/workspace/final/scripts/run_cmp_1x5.py",
        "--thread_num", str(setting.get("validation_thread_num", 4)),
        "--test_steps", str(setting["independent_validation_steps"]),
        "--seed", str(setting["seed"]),
        "--policy", "cmp_legacy_adapter",
        "--adapter_dir", str(checkpoint_dir),
        "--adapter_episode", str(episode),
        "--cmp_uncertainty_margin", str(setting["cmp_uncertainty_margin"]),
        "--override_advantage", str(setting["override_advantage"]),
        "--prefix", f"1x5_cmp_independent_episode_{episode}",
    ]
    print(f"independent_validation_start episode={episode}", flush=True)
    result = subprocess.run(cmd, cwd="/DaRL/UGAT_Docker", check=False)
    if result.returncode != 0:
        print(f"independent_validation_failed episode={episode}, exit_code={result.returncode}", flush=True)
        return None
    metrics = read_json(Path("/workspace/final/logs/1x5_cmp_latest_metrics.json"), {})
    required = {"travel_time", "queue", "delay_ratio_apx", "throughput", "adapter_overrides"}
    if not isinstance(metrics, dict) or not required.issubset(metrics):
        print(f"independent_validation_failed episode={episode}, reason=incomplete_metrics", flush=True)
        return None
    record = Path("/workspace/final/logs/cmp_independent_validation.csv")
    exists = record.exists()
    with record.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["episode", *sorted(required)])
        if not exists:
            writer.writeheader()
        writer.writerow({"episode": episode, **{key: metrics[key] for key in required}})
    print(
        f"independent_validation_complete episode={episode}, travel_time={float(metrics['travel_time']):.4f}, "
        f"queue={float(metrics['queue']):.4f}, delay={float(metrics['delay_ratio_apx']):.4f}, "
        f"overrides={int(metrics['adapter_overrides'])}",
        flush=True,
    )
    return metrics


def train_test_and_select(self, episode):
    """Evaluate, retain a safe training candidate, and separately select formal models."""
    travel_time = float(ORIGINAL_TRAIN_TEST(self, episode))
    out = Path("/workspace/final/logs")
    record = out / "cmp_training_eval.csv"
    exists = record.exists()
    with record.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if not exists:
            writer.writerow(["episode", "travel_time", "queue", "delay_ratio_apx", "throughput"])
        writer.writerow([episode, travel_time, float(self.metric.queue()), float(self.metric.delay()), float(self.metric.throughput())])
    independent = independently_validate_adapter(episode)
    if independent is None:
        for agent in self.agents:
            agent.restore_safe_adapter()
        return travel_time
    travel_time = float(independent["travel_time"])
    queue = float(independent["queue"])
    delay = float(independent["delay_ratio_apx"])
    throughput = float(independent["throughput"])
    checkpoint_dir = Path("/workspace/final/logs/legacy_cmp_adapter_train")
    adapter_active = int(independent["adapter_overrides"]) > 0
    qualifies = adapter_active and travel_time < BASELINE_TRAVEL_TIME and queue <= BASELINE_QUEUE and delay <= BASELINE_DELAY
    candidate_is_safe = adapter_active and queue <= BASELINE_QUEUE * CANDIDATE_QUEUE_LIMIT and delay <= BASELINE_DELAY * CANDIDATE_DELAY_LIMIT
    candidate_score = adapter_candidate_score(travel_time, queue, delay)
    candidate_path = checkpoint_dir / "candidate_metrics.json"
    previous_candidate = read_json(candidate_path, {"score": 1.0, "source": "C-MP baseline"})
    is_better_candidate = candidate_is_safe and candidate_score < float(previous_candidate.get("score", float("inf")))
    if is_better_candidate:
        for rank in range(len(self.agents)):
            src = checkpoint_dir / f"episode_{episode}_rank_{rank}.pt"
            dst = checkpoint_dir / f"candidate_rank_{rank}.pt"
            if src.exists():
                shutil.copyfile(src, dst)
        candidate_path.write_text(json.dumps({
            "episode": episode, "travel_time": travel_time, "queue": queue, "delay": delay,
            "score": candidate_score, "source": "training_candidate",
        }, indent=2), encoding="utf-8")
        for agent in self.agents:
            agent.accept_safe_adapter()
        print(f"new_training_candidate episode={episode}, score={candidate_score:.6f}, travel_time={travel_time:.4f}", flush=True)

    best_path = checkpoint_dir / "best_metrics.json"
    previous_best = read_json(best_path, {"travel_time": float("inf")})
    best = float(previous_best.get("travel_time", float("inf")))
    if qualifies and travel_time < best:
        for rank in range(len(self.agents)):
            src = checkpoint_dir / f"episode_{episode}_rank_{rank}.pt"
            dst = checkpoint_dir / f"best_rank_{rank}.pt"
            if src.exists():
                shutil.copyfile(src, dst)
        (checkpoint_dir / "best_episode.txt").write_text(str(episode), encoding="utf-8")
        best_path.write_text(json.dumps({
            "episode": episode, "travel_time": travel_time, "queue": queue, "delay": delay,
            "throughput": throughput,
        }, indent=2), encoding="utf-8")
        for agent in self.agents:
            agent.accept_safe_adapter()
        print(f"new_best_adapter_episode={episode}, travel_time={travel_time:.4f}", flush=True)
    elif not is_better_candidate:
        for agent in self.agents:
            agent.restore_safe_adapter()
        print(f"adapter_rejected episode={episode}, travel_time={travel_time:.4f}, queue={queue:.4f}, delay={delay:.4f}, overrides={int(independent['adapter_overrides'])}, candidate_score={candidate_score:.6f}", flush=True)
    return travel_time


tsc.TSCTrainer.train_test = train_test_and_select


def set_cityflow_seed(seed):
    original = CITYFLOW_CONFIG.read_text(encoding="utf-8")
    config = json.loads(original)
    config["seed"] = int(seed)
    CITYFLOW_CONFIG.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return original


@Registry.register_model("cmptrain1x5")
class CMPTrain1x5Agent(BaseDQN):
    """DQN agent with frozen UGAT and a trainable residual adapter."""

    def __init__(self, world, rank):
        super().__init__(world, rank)
        setting = Registry.mapping["model_mapping"]["setting"].param
        self.world.subscribe(["lane_vehicles"])
        self.cmp = CMPController(world, self.inter, float(setting.get("cmp_beta", 0.60)), float(setting.get("cmp_alpha", 0.60)), int(setting.get("t_min", 10)))
        self.model = TrainableUGATResidual(
            "/workspace/final/model/ugat1x5_best.pt", rank, self.ob_length, self.action_space.n
        )
        self.target_model = TrainableUGATResidual(
            "/workspace/final/model/ugat1x5_best.pt", rank, self.ob_length, self.action_space.n
        )
        self.update_target_network()
        self.optimizer = optim.RMSprop(
            [p for p in self.model.parameters() if p.requires_grad],
            lr=float(setting["learning_rate"]), alpha=0.9, centered=False, eps=1e-7
        )
        self.adapter_dir = Path("/workspace/final/logs/legacy_cmp_adapter_train")
        self.loss_path = Path("/workspace/final/logs/cmp_training_loss.csv")
        self.loss_history = []
        self.transition_meta = {}
        self.teacher_reward_ema = None
        self.teacher_count = 0
        self.uncertain_count = 0
        self.override_count = 0
        self.episode_decisions = 0
        self.episode_overrides = 0
        self.adapter_dir.mkdir(parents=True, exist_ok=True)
        initial_path = self.adapter_dir / f"initial_rank_{rank}.pt"
        if not initial_path.exists():
            torch.save({"adapter": self.model.adapter.state_dict(), "rank": rank}, initial_path)
        if bool(setting.get("resume_candidate", False)):
            candidate_path = self.adapter_dir / f"candidate_rank_{rank}.pt"
            if not candidate_path.exists():
                raise FileNotFoundError(
                    f"resume candidate missing: {candidate_path}. Run training once without --resume_candidate first."
                )
            payload = torch.load(candidate_path, map_location="cpu", weights_only=True)
            self.model.adapter.load_state_dict(payload["adapter"])
            self.update_target_network()
            print(f"resumed_training_candidate_rank={rank}, path={candidate_path}", flush=True)
        self.safe_adapter_state = copy.deepcopy(self.model.adapter.state_dict())
        frozen = sum(p.numel() for p in self.model.ugat.parameters())
        trainable = sum(p.numel() for p in self.model.adapter.parameters())
        print(f"training_enabled=true, rank={rank}, frozen_parameters={frozen}, trainable_parameters={trainable}", flush=True)

    def train(self):
        # Double-DQN target + Huber loss. Rewards are scaled only for numerical
        # stability; action ranking and the CityFlow evaluation metrics remain unchanged.
        adapter_pool = [item for item in self.replay_buffer if self.transition_meta.get(item[0], {}).get("uncertain", False) and not self.transition_meta.get(item[0], {}).get("teacher_action", True)]
        if not adapter_pool:
            return 0.0
        samples = random.choices(adapter_pool, k=self.batch_size)
        b_t, b_tp, rewards, actions = self._batchwise(samples)
        q_values = self.model.residual(b_t)
        chosen_q = q_values.gather(1, actions.view(-1, 1)).squeeze(1)
        baseline = float(self.teacher_reward_ema if self.teacher_reward_ema is not None else 0.0)
        advantages = []
        for item in samples:
            meta = self.transition_meta.get(item[0], {})
            reward = float(np.asarray(item[1][3]).reshape(-1)[0])
            advantages.append(0.0 if meta.get("teacher_action", True) else reward - baseline)
        advantage_tensor = torch.tensor(advantages, dtype=torch.float32)
        with torch.no_grad():
            next_residual = self.model.residual(b_tp)
            next_actions = next_residual.argmax(dim=1)
            next_q = self.target_model.residual(b_tp).gather(1, next_actions.view(-1, 1)).squeeze(1)
            target_q = advantage_tensor * 0.1 + self.gamma * next_q
        loss_tensor = F.smooth_l1_loss(chosen_q, target_q)
        self.optimizer.zero_grad()
        loss_tensor.backward()
        clip_grad_norm_([p for p in self.model.parameters() if p.requires_grad], self.grad_clip)
        self.optimizer.step()
        if self.epsilon > self.epsilon_min:
            self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)
        loss = float(loss_tensor.detach().cpu().item())
        self.loss_history.append(loss)
        exists = self.loss_path.exists()
        with self.loss_path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            if not exists:
                writer.writerow(["rank", "update", "loss"])
            writer.writerow([self.rank, len(self.loss_history), loss])
        return loss

    def remember(self, last_obs, last_phase, actions, actions_prob, rewards, obs, cur_phase, done, key):
        super().remember(last_obs, last_phase, actions, actions_prob, rewards, obs, cur_phase, done, key)
        teacher_action = int(getattr(self, "pending_teacher_action", int(np.asarray(actions).reshape(-1)[0])))
        actual_action = int(np.asarray(actions).reshape(-1)[0])
        uncertain = bool(getattr(self, "pending_uncertain", False))
        self.transition_meta[key] = {"teacher_action": actual_action == teacher_action, "uncertain": uncertain}
        if uncertain:
            self.uncertain_count += 1
        if actual_action == teacher_action:
            reward = float(np.asarray(rewards).reshape(-1)[0])
            self.teacher_reward_ema = reward if self.teacher_reward_ema is None else 0.95 * self.teacher_reward_ema + 0.05 * reward
            self.teacher_count += 1

    def reset(self):
        super().reset()
        self.episode_decisions = 0
        self.episode_overrides = 0

    def accept_safe_adapter(self):
        self.safe_adapter_state = copy.deepcopy(self.model.adapter.state_dict())

    def restore_safe_adapter(self):
        self.model.adapter.load_state_dict(self.safe_adapter_state)
        self.target_model.load_state_dict(self.model.state_dict())
        self.optimizer.state.clear()
        print(f"restored_safe_adapter_rank={self.rank}", flush=True)

    def load_model(self, e, customized_path=""):
        print("skip_legacy_dqn_load=true")

    def get_action(self, ob, phase, test=False):
        self.episode_decisions += 1
        if self.phase and self.one_hot:
            feature = np.concatenate([ob, utils.idx2onehot(phase, self.action_space.n)], axis=1)
        elif self.phase:
            feature = np.concatenate([ob, phase], axis=1)
        else:
            feature = ob
        with torch.no_grad():
            feature_tensor = torch.tensor(feature, dtype=torch.float32)
            ugat_q = self.model.ugat(feature_tensor, train=False).numpy()[0]
            q = self.model.residual(feature_tensor).numpy()[0]
        cmp_action, pressure_margin, can_change = self.cmp.choose_with_details(ugat_q)
        setting = Registry.mapping["model_mapping"]["setting"].param
        if not can_change or pressure_margin > float(setting["cmp_uncertainty_margin"]):
            self.pending_teacher_action = cmp_action
            self.pending_uncertain = False
            return np.asarray([cmp_action])
        self.pending_teacher_action = cmp_action
        self.pending_uncertain = True
        max_rate = float(setting["max_override_rate"])
        can_override = self.episode_overrides < max(1, int(max_rate * self.episode_decisions))
        if not can_override:
            return np.asarray([cmp_action])
        if not test and np.random.rand() <= self.epsilon:
            action = int(self.sample()[0])
            changed = int(action != cmp_action)
            self.override_count += changed
            self.episode_overrides += changed
            return np.asarray([action])
        candidate = int(np.argmax(q))
        advantage = float(q[candidate] - q[cmp_action])
        if candidate != cmp_action and advantage >= float(setting["override_advantage"]):
            self.override_count += 1
            self.episode_overrides += 1
            return np.asarray([candidate])
        return np.asarray([cmp_action])

    def save_model(self, e):
        path = self.adapter_dir / f"episode_{e}_rank_{self.rank}.pt"
        torch.save({"adapter": self.model.adapter.state_dict(), "rank": self.rank}, path)
        print(f"saved_trainable_adapter={path}", flush=True)
        print(f"teacher_samples={self.teacher_count}, uncertain_samples={self.uncertain_count}, adapter_overrides={self.override_count}", flush=True)
        return str(path)


def main():
    parser = argparse.ArgumentParser(description="Reward-aware CityFlow training of a UGAT residual adapter")
    parser.add_argument("--thread_num", type=int, default=4)
    parser.add_argument("--seed", type=int, default=4444)
    parser.add_argument("--episodes", type=int, default=5)
    parser.add_argument("--steps", type=int, default=9000)
    parser.add_argument("--learning_start", type=int, default=1000)
    parser.add_argument("--batch_size", type=int, default=64)
    parser.add_argument("--learning_rate", type=float, default=3e-5)
    parser.add_argument("--eval_steps", type=int, default=9000, help="same-protocol evaluation length after every episode")
    parser.add_argument("--cmp_uncertainty_margin", type=float, default=2.0, help="train adapter only when C-MP top-two pressure gap is at most this value")
    parser.add_argument("--override_advantage", type=float, default=0.15, help="minimum residual advantage required to replace C-MP")
    parser.add_argument("--max_override_rate", type=float, default=0.02, help="maximum fraction of per-episode decisions allowed to replace C-MP")
    parser.add_argument("--independent_validation_steps", type=int, default=9000, help="fresh-process CityFlow steps required before a checkpoint can be selected")
    parser.add_argument("--resume_candidate", action="store_true", help="continue from candidate_rank_<R>.pt retained by an earlier safe training run")
    parser.add_argument("--reset_candidate", action="store_true", help="discard only exploratory candidate_rank files and start subsequent training from the zero adapter")
    parser.add_argument("--bootstrap_verified_best", action="store_true", help="initialize candidate_rank files from the independently verified legacy best_rank files")
    parser.add_argument("--prefix", default="1x5_cmp_train")
    args = parser.parse_args()
    if args.episodes < 1 or args.steps < 1 or args.batch_size < 1 or args.independent_validation_steps < 1 or args.cmp_uncertainty_margin < 0 or args.override_advantage < 0 or not 0 <= args.max_override_rate <= 1:
        parser.error("episodes, steps and batch_size must be positive")
    checkpoint_dir = Path("/workspace/final/logs/legacy_cmp_adapter_train")
    if args.reset_candidate:
        for stale in checkpoint_dir.glob("candidate_rank_*.pt"):
            stale.unlink()
        (checkpoint_dir / "candidate_metrics.json").unlink(missing_ok=True)
    if args.bootstrap_verified_best:
        verified_dir = Path("/workspace/final/logs/legacy_cmp_adapter_best")
        for rank in range(5):
            source = verified_dir / f"best_rank_{rank}.pt"
            if not source.exists():
                raise FileNotFoundError(f"verified legacy checkpoint missing: {source}")
            shutil.copyfile(source, checkpoint_dir / f"candidate_rank_{rank}.pt")
        (checkpoint_dir / "candidate_metrics.json").write_text(json.dumps({
            "source": "verified_legacy_best", "travel_time": 1008.7885766927683,
            "queue": 8.200666427612305, "delay": 0.1450585126876831,
            "score": 0.9905503072478028,
        }, indent=2), encoding="utf-8")
        args.resume_candidate = True
        print("bootstrapped_verified_legacy_best=true", flush=True)
    # The trainer reads these values from the local config copied into Docker.
    config = f'''includes:\n  - configs/tsc/base.yml\nmodel:\n  name: cmptrain1x5\n  train_model: true\n  test_model: false\n  load_model: false\n  graphic: false\n  one_hot: true\n  phase: true\n  epsilon: 0.05\n  epsilon_decay: 0.9995\n  epsilon_min: 0.01\n  learning_rate: {args.learning_rate}\n  batch_size: {args.batch_size}\n  gamma: 0.99\ntrainer:\n  episodes: {args.episodes}\n  steps: {args.steps}\n  learning_start: {args.learning_start}\n  buffer_size: 50000\n  action_interval: 10\n  update_model_rate: 1\n  update_target_rate: 200\n  test_when_train: false\n'''
    config = config.replace("  gamma: 0.99\ntrainer:", f"  gamma: 0.99\n  cmp_beta: 0.60\n  cmp_alpha: 0.60\n  cmp_uncertainty_margin: {args.cmp_uncertainty_margin}\n  override_advantage: {args.override_advantage}\n  max_override_rate: {args.max_override_rate}\n  t_min: 10\ntrainer:")
    config = config.replace("  epsilon: 0.05", "  epsilon: 0.20")
    config = config.replace("  test_when_train: false", "  test_steps: {args.eval_steps}\n  test_when_train: true")
    Path("/workspace/final/configs/cmptrain1x5.yml").write_text(config, encoding="utf-8")
    shutil.copyfile("/workspace/final/configs/cmptrain1x5.yml", "/DaRL/UGAT_Docker/configs/tsc/cmptrain1x5.yml")
    cityflow_original = set_cityflow_seed(args.seed)
    old_argv = sys.argv
    sys.argv = ["train_cmp_adapter_1x5.py", "-t", "tsc", "-a", "cmptrain1x5", "-w", "cityflow", "-n", "cityflow_atlanta1x5", "-d", "onfly", "--thread_num", str(args.thread_num), "--seed", str(args.seed), "--prefix", args.prefix, "--interface", "libsumo", "--delay_type", "apx"]
    try:
        from run import Runner
        ns = argparse.Namespace(thread_num=args.thread_num, ngpu="-1", prefix=args.prefix, seed=args.seed, debug=False, interface="libsumo", delay_type="apx", task="tsc", agent="cmptrain1x5", world="cityflow", network="cityflow_atlanta1x5", dataset="onfly")
        runner = Runner(ns)
        Registry.mapping["trainer_mapping"]["setting"].param.update({"episodes": args.episodes, "steps": args.steps, "test_steps": args.eval_steps, "learning_start": args.learning_start, "buffer_size": 50000, "action_interval": 10, "update_model_rate": 1, "update_target_rate": 200, "test_when_train": True})
        Registry.mapping["model_mapping"]["setting"].param.update({"learning_rate": args.learning_rate, "batch_size": args.batch_size, "gamma": 0.99, "epsilon": 0.20, "epsilon_decay": 0.9995, "epsilon_min": 0.01, "cmp_beta": 0.60, "cmp_alpha": 0.60, "cmp_uncertainty_margin": args.cmp_uncertainty_margin, "override_advantage": args.override_advantage, "max_override_rate": args.max_override_rate, "resume_candidate": args.resume_candidate, "independent_validation_steps": args.independent_validation_steps, "validation_thread_num": args.thread_num, "seed": args.seed, "t_min": 10})
        print(f"training_protocol: episodes={args.episodes}, steps={args.steps}, learning_start={args.learning_start}, batch_size={args.batch_size}, learning_rate={args.learning_rate}, cmp_uncertainty_margin={args.cmp_uncertainty_margin}, override_advantage={args.override_advantage}, max_override_rate={args.max_override_rate}, independent_validation_steps={args.independent_validation_steps}, resume_candidate={args.resume_candidate}", flush=True)
        runner.run()
    finally:
        sys.argv = old_argv
        CITYFLOW_CONFIG.write_text(cityflow_original, encoding="utf-8")
        write_training_loss_plot()


if __name__ == "__main__":
    main()
