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
from ugat_cmp_1x5 import CMPController, FRAPResidualAdapter, cmp_frap_phase_fusion, pressure_trust_region  # noqa: E402
import trainer.tsc_trainer as tsc  # noqa: E402

CITYFLOW_CONFIG = Path("/DaRL/UGAT_Docker/configs/sim/cityflow_atlanta1x5.cfg")
ORIGINAL_TRAIN_TEST = tsc.TSCTrainer.train_test
BASELINE_TRAVEL_TIME = 1019.0248733302626
BASELINE_QUEUE = 8.264222145080566
BASELINE_DELAY = 0.14652371406555176
CANDIDATE_QUEUE_LIMIT = 1.05
CANDIDATE_DELAY_LIMIT = 1.05
FORMAL_MAX_SINGLE_REGRESSION = 0.02
FORMAL_REQUIRED_SCORE_IMPROVEMENT = 0.01
LOSS_PLOT_MAX = 1_000_000.0
LOSS_PLOT_SAMPLE_LIMIT = 5_000


def adapter_candidate_score(travel_time, queue, delay):
    """Score an exploratory continuation candidate without relaxing formal gates."""
    return (
        0.60 * travel_time / BASELINE_TRAVEL_TIME
        + 0.25 * queue / BASELINE_QUEUE
        + 0.15 * delay / BASELINE_DELAY
    )


def formally_qualifies(travel_time, queue, delay):
    """Balanced formal gate: one small auxiliary regression is permitted.

    Travel Time remains the primary competition measure. Queue and delay are
    guard metrics: no more than one may regress, and its regression is capped.
    The fixed weighted score prevents accepting a negligible travel improvement
    obtained by trading away an important auxiliary metric.
    """
    score = adapter_candidate_score(travel_time, queue, delay)
    regressions = int(queue > BASELINE_QUEUE) + int(delay > BASELINE_DELAY)
    within_auxiliary_cap = (
        queue <= BASELINE_QUEUE * (1.0 + FORMAL_MAX_SINGLE_REGRESSION)
        and delay <= BASELINE_DELAY * (1.0 + FORMAL_MAX_SINGLE_REGRESSION)
    )
    qualified = (
        travel_time < BASELINE_TRAVEL_TIME
        and regressions <= 1
        and within_auxiliary_cap
        and score <= 1.0 - FORMAL_REQUIRED_SCORE_IMPROVEMENT
    )
    return qualified, score, regressions


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


def snapshot_cityflow_world(world):
    """Capture CityFlow plus wrapper state for an exact counterfactual branch."""
    intersection_state = [
        (item.current_phase, item._current_phase, item.current_phase_time, item.action_before_yellow, item.action_executed)
        for item in world.intersections
    ]
    world_state = {
        name: copy.deepcopy(getattr(world, name))
        for name in (
            "info", "vehicle_waiting_time", "vehicle_trajectory", "history_vehicles",
            "dic_lane_vehicle_previous_step", "dic_lane_vehicle_current_step",
            "dic_vehicle_arrive_leave_time",
        )
    }
    return world.eng.snapshot(), intersection_state, world_state


def restore_cityflow_world(world, snapshot):
    archive, intersection_state, world_state = snapshot
    world.eng.load(archive)
    for item, values in zip(world.intersections, intersection_state):
        item.current_phase, item._current_phase, item.current_phase_time, item.action_before_yellow, item.action_executed = values
    for name, value in world_state.items():
        setattr(world, name, copy.deepcopy(value))
    world._update_infos()


def rollout_branch(env, agents, actions, horizon):
    """Evaluate one fixed joint signal action from the current simulator state."""
    rewards, queues, delays = [], [], []
    for _ in range(horizon):
        _, step_rewards, _, _ = env.step(actions.flatten())
        rewards.append(float(np.mean(step_rewards)))
        queues.append(float(np.mean([np.mean(agent.queue.generate()) for agent in agents])))
        delays.append(float(np.mean([np.mean(agent.delay.generate()) for agent in agents])))
    travel = float(env.eng.get_average_travel_time())
    return {
        "reward": float(np.mean(rewards)),
        "queue": float(np.mean(queues)),
        "delay": float(np.mean(delays)),
        "travel_time": travel if np.isfinite(travel) and travel >= 0 else 0.0,
    }


def paired_counterfactual(env, agents, teacher_actions, candidate_actions, horizon, queue_penalty, delay_penalty, travel_weight):
    """Compare C-MP and candidate actions from the exact same CityFlow state."""
    snapshot = snapshot_cityflow_world(env.world)
    teacher = rollout_branch(env, agents, teacher_actions, horizon)
    restore_cityflow_world(env.world, snapshot)
    candidate = rollout_branch(env, agents, candidate_actions, horizon)
    restore_cityflow_world(env.world, snapshot)
    advantage = (
        candidate["reward"] - teacher["reward"]
        - float(queue_penalty) * max(0.0, candidate["queue"] - teacher["queue"])
        - float(delay_penalty) * max(0.0, candidate["delay"] - teacher["delay"])
        + float(travel_weight) * (teacher["travel_time"] - candidate["travel_time"]) / max(teacher["travel_time"], 1.0)
    )
    return teacher, candidate, float(advantage)


def independently_validate_adapter(episode):
    """Run a fresh CityFlow process before allowing a checkpoint to become formal best."""
    setting = Registry.mapping["model_mapping"]["setting"].param
    checkpoint_dir = Path("/workspace/final/logs/cmp_frap_checkpoints")
    cmd = [
        sys.executable, "/workspace/final/scripts/run_cmp_1x5.py",
        "--thread_num", str(setting.get("validation_thread_num", 4)),
        "--test_steps", str(setting["independent_validation_steps"]),
        "--seed", str(setting["formal_eval_seed"]),
        "--policy", "cmp_frap",
        "--adapter_dir", str(checkpoint_dir),
        "--adapter_episode", str(episode),
        "--cmp_uncertainty_margin", str(setting["cmp_uncertainty_margin"]),
        "--override_advantage", str(setting["override_advantage"]),
        "--pressure_prior_weight", str(setting["pressure_prior_weight"]),
        "--max_pressure_regret", str(setting["max_pressure_regret"]),
        "--max_downstream_mean_increase", str(setting["max_downstream_mean_increase"]),
        "--max_downstream_lane_count", str(setting["max_downstream_lane_count"]),
        "--max_override_rate", str(setting["max_override_rate"]),
        "--pressure_weight", str(setting["pressure_weight"]),
        "--frap_weight", str(setting["frap_weight"]),
        "--downstream_weight", str(setting["downstream_weight"]),
        "--max_normalized_pressure_regret", str(setting["max_normalized_pressure_regret"]),
        "--action_deviation_penalty", str(setting["action_deviation_penalty"]),
        "--prefix", f"1x5_cmp_independent_seed_{setting['formal_eval_seed']}_episode_{episode}",
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
    checkpoint_dir = Path("/workspace/final/logs/cmp_frap_checkpoints")
    adapter_active = int(independent["adapter_overrides"]) > 0
    balanced_qualified, formal_score, regressions = formally_qualifies(travel_time, queue, delay)
    qualifies = adapter_active and balanced_qualified
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
        setting = Registry.mapping["model_mapping"]["setting"].param
        run_label = str(setting.get("run_label") or "unnamed_run")
        safe_label = "".join(char if char.isalnum() or char in "-_" else "_" for char in run_label)
        history_dir = checkpoint_dir / "candidate_history" / safe_label / f"seed_{setting['seed']}_episode_{episode}"
        history_dir.mkdir(parents=True, exist_ok=True)
        for rank in range(len(self.agents)):
            shutil.copyfile(checkpoint_dir / f"candidate_rank_{rank}.pt", history_dir / f"candidate_rank_{rank}.pt")
        candidate_record = {
            "episode": episode, "travel_time": travel_time, "queue": queue, "delay": delay,
            "score": candidate_score, "source": "training_candidate", "training_seed": setting["seed"],
            "run_label": safe_label, "policy_schema": "joint_cmp_frap_v2",
        }
        candidate_path.write_text(json.dumps(candidate_record, indent=2), encoding="utf-8")
        (history_dir / "metrics.json").write_text(json.dumps(candidate_record, indent=2), encoding="utf-8")
        for agent in self.agents:
            agent.accept_safe_adapter()
        print(f"new_training_candidate episode={episode}, score={candidate_score:.6f}, travel_time={travel_time:.4f}", flush=True)

    print(f"formal_gate: qualified={qualifies}, score={formal_score:.6f}, auxiliary_regressions={regressions}, max_single_regression={FORMAL_MAX_SINGLE_REGRESSION:.2%}", flush=True)
    best_path = checkpoint_dir / "best_metrics.json"
    previous_best = read_json(best_path, {"score": float("inf")})
    best = float(previous_best.get("score", float("inf")))
    if qualifies and formal_score < best:
        for rank in range(len(self.agents)):
            src = checkpoint_dir / f"episode_{episode}_rank_{rank}.pt"
            dst = checkpoint_dir / f"best_rank_{rank}.pt"
            if src.exists():
                shutil.copyfile(src, dst)
        (checkpoint_dir / "best_episode.txt").write_text(str(episode), encoding="utf-8")
        best_path.write_text(json.dumps({
            "episode": episode, "travel_time": travel_time, "queue": queue, "delay": delay,
            "throughput": throughput, "score": formal_score,
            "formal_gate": {
                "primary_requirement": "travel_time < baseline",
                "max_auxiliary_regressions": 1,
                "max_single_auxiliary_regression": FORMAL_MAX_SINGLE_REGRESSION,
                "required_weighted_score_improvement": FORMAL_REQUIRED_SCORE_IMPROVEMENT,
            },
        }, indent=2), encoding="utf-8")
        for agent in self.agents:
            agent.accept_safe_adapter()
        print(f"new_best_adapter_episode={episode}, travel_time={travel_time:.4f}", flush=True)
    elif not is_better_candidate:
        for agent in self.agents:
            agent.restore_safe_adapter()
        print(f"adapter_rejected episode={episode}, travel_time={travel_time:.4f}, queue={queue:.4f}, delay={delay:.4f}, overrides={int(independent['adapter_overrides'])}, candidate_score={candidate_score:.6f}", flush=True)
    return travel_time


def counterfactual_train(self):
    """Train with paired CityFlow rollouts from an identical engine snapshot."""
    total_decisions = 0
    setting = Registry.mapping["model_mapping"]["setting"].param
    cf_every = int(setting["counterfactual_every"])
    cf_horizon = int(setting["counterfactual_horizon"])
    cf_min = float(setting["counterfactual_min_advantage"])
    cf_travel_weight = float(setting["counterfactual_travel_weight"])
    for episode in range(self.episodes):
        self.metric.clear()
        last_obs = self.env.reset()
        for agent in self.agents:
            agent.reset()
        losses = []
        counterfactual_checks = 0
        counterfactual_accepts = 0
        counterfactual_log = Path("/workspace/final/logs/counterfactual_rollouts.csv")
        step = 0
        while step < self.steps:
            if step % self.action_interval == 0:
                phases = np.stack([agent.get_phase() for agent in self.agents])
                if total_decisions > self.learning_start:
                    candidate_actions = np.stack([agent.get_action(last_obs[index], phases[index], test=False) for index, agent in enumerate(self.agents)])
                else:
                    candidate_actions = np.stack([agent.sample() for agent in self.agents])
                teacher_actions = np.asarray([
                    [int(getattr(agent, "pending_teacher_action", candidate_actions[index][0]))]
                    for index, agent in enumerate(self.agents)
                ])
                # A neutral adapter has no residual preference yet. Generate a
                # near-pressure alternative only for paired evaluation; it is
                # never executed unless its own counterfactual branch wins.
                if total_decisions > self.learning_start and total_decisions % cf_every == 0:
                    for index, agent in enumerate(self.agents):
                        if candidate_actions[index][0] == teacher_actions[index][0]:
                            probe = agent.counterfactual_probe_action(float(setting["counterfactual_probe_regret"]))
                            if probe is not None:
                                candidate_actions[index][0] = probe
                actions = candidate_actions
                changed = bool(np.any(candidate_actions != teacher_actions))
                checked = total_decisions > self.learning_start and changed and total_decisions % cf_every == 0
                advantage = 0.0
                if checked:
                    teacher_metrics, candidate_metrics, advantage = paired_counterfactual(
                        self.env, self.agents, teacher_actions, candidate_actions, cf_horizon,
                        setting["queue_penalty"], setting["delay_penalty"], cf_travel_weight,
                    )
                    counterfactual_checks += 1
                    if advantage >= cf_min:
                        counterfactual_accepts += 1
                    else:
                        actions = teacher_actions
                    print(
                        f"counterfactual episode={episode}, decision={total_decisions}, advantage={advantage:.6f}, "
                        f"teacher_queue={teacher_metrics['queue']:.4f}, candidate_queue={candidate_metrics['queue']:.4f}, "
                        f"teacher_delay={teacher_metrics['delay']:.4f}, candidate_delay={candidate_metrics['delay']:.4f}, "
                        f"teacher_travel={teacher_metrics['travel_time']:.4f}, candidate_travel={candidate_metrics['travel_time']:.4f}, accepted={advantage >= cf_min}",
                        flush=True,
                    )
                    exists = counterfactual_log.exists()
                    with counterfactual_log.open("a", newline="", encoding="utf-8") as handle:
                        writer = csv.DictWriter(handle, fieldnames=["episode", "decision", "advantage", "accepted", *[f"teacher_{key}" for key in teacher_metrics], *[f"candidate_{key}" for key in candidate_metrics]])
                        if not exists:
                            writer.writeheader()
                        writer.writerow({"episode": episode, "decision": total_decisions, "advantage": advantage, "accepted": advantage >= cf_min, **{f"teacher_{key}": value for key, value in teacher_metrics.items()}, **{f"candidate_{key}": value for key, value in candidate_metrics.items()}})
                for agent in self.agents:
                    agent.pending_counterfactual_checked = checked
                    agent.pending_counterfactual_advantage = advantage if checked and actions is candidate_actions else 0.0
                actions_prob = [agent.get_action_prob(last_obs[index], phases[index]) for index, agent in enumerate(self.agents)]
                rewards_list = []
                for _ in range(self.action_interval):
                    obs, rewards, dones, _ = self.env.step(actions.flatten())
                    step += 1
                    rewards_list.append(np.stack(rewards))
                rewards = np.mean(rewards_list, axis=0)
                self.metric.update(rewards)
                current_phase = np.stack([agent.get_phase() for agent in self.agents])
                for index, agent in enumerate(self.agents):
                    agent.remember(last_obs[index], phases[index], actions[index], actions_prob[index], rewards[index], obs[index], current_phase[index], dones[index], f"cf_{episode}_{total_decisions}_{agent.id}")
                total_decisions += 1
                last_obs = obs
            if total_decisions > self.learning_start and total_decisions % self.update_model_rate == self.update_model_rate - 1:
                losses.append(np.stack([agent.train() for agent in self.agents]))
            if total_decisions > self.learning_start and total_decisions % self.update_target_rate == self.update_target_rate - 1:
                [agent.update_target_network() for agent in self.agents]
            if all(dones):
                break
        mean_loss = float(np.mean(losses)) if losses else 0.0
        self.logger.info(f"counterfactual_train episode={episode}, q_loss={mean_loss}, checks={counterfactual_checks}, accepts={counterfactual_accepts}, queue={self.metric.queue()}, delay={self.metric.delay()}")
        [agent.save_model(e=episode) for agent in self.agents]
        if self.test_when_train:
            self.train_test(episode)
    [agent.save_model(e=self.episodes) for agent in self.agents]


tsc.TSCTrainer.train_test = train_test_and_select
tsc.TSCTrainer.train = counterfactual_train


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
        self.model = FRAPResidualAdapter(
            "/workspace/final/model/ugat1x5_best.pt", rank, self.ob_length, self.action_space.n
        )
        self.target_model = FRAPResidualAdapter(
            "/workspace/final/model/ugat1x5_best.pt", rank, self.ob_length, self.action_space.n
        )
        self.update_target_network()
        self.optimizer = optim.RMSprop(
            [p for p in self.model.parameters() if p.requires_grad],
            lr=float(setting["learning_rate"]), alpha=0.9, centered=False, eps=1e-7
        )
        self.adapter_dir = Path("/workspace/final/logs/cmp_frap_checkpoints")
        self.loss_path = Path("/workspace/final/logs/cmp_training_loss.csv")
        self.loss_history = []
        self.transition_meta = {}
        self.teacher_reward_ema = None
        self.teacher_queue_ema = None
        self.teacher_delay_ema = None
        self.teacher_count = 0
        self.uncertain_count = 0
        self.override_count = 0
        self.multiobjective_safe_count = 0
        self.controlled_lanes = [lane for lane_group in self.ob_generator.lanes for lane in lane_group]
        self.episode_decisions = 0
        self.episode_overrides = 0
        self.adapter_dir.mkdir(parents=True, exist_ok=True)
        initial_path = self.adapter_dir / f"initial_rank_{rank}_frap_state_v1.pt"
        if not initial_path.exists():
            torch.save({"adapter": self.model.adapter.state_dict(), "optimizer_state": self.optimizer.state_dict(), "rank": rank, "state_schema": self.model.state_schema}, initial_path)
        if bool(setting.get("resume_candidate", False)):
            candidate_path = self.adapter_dir / f"candidate_rank_{rank}.pt"
            if not candidate_path.exists():
                raise FileNotFoundError(
                    f"resume candidate missing: {candidate_path}. Run training once without --resume_candidate first."
                )
            payload = torch.load(candidate_path, map_location="cpu", weights_only=True)
            if payload.get("state_schema") != self.model.state_schema:
                raise RuntimeError("candidate checkpoint uses an obsolete FRAP state schema. Start a new multi-scenario run with --reset_candidate.")
            if payload.get("policy_schema") != "joint_cmp_frap_v2":
                raise RuntimeError("candidate checkpoint predates the joint C-MP-FRAP policy. Start a new run with --reset_candidate.")
            self.model.adapter.load_state_dict(payload["adapter"])
            if payload.get("optimizer_state"):
                self.optimizer.load_state_dict(payload["optimizer_state"])
            self.update_target_network()
            print(f"resumed_training_candidate_rank={rank}, path={candidate_path}", flush=True)
        self.safe_adapter_state = copy.deepcopy(self.model.adapter.state_dict())
        self.safe_optimizer_state = copy.deepcopy(self.optimizer.state_dict())
        frozen = sum(p.numel() for p in self.model.ugat.parameters())
        trainable = sum(p.numel() for p in self.model.adapter.parameters())
        print(f"training_enabled=true, rank={rank}, frozen_parameters={frozen}, trainable_parameters={trainable}", flush=True)

    def train(self):
        # Double-DQN target + Huber loss. Rewards are scaled only for numerical
        # stability; action ranking and the CityFlow evaluation metrics remain unchanged.
        adapter_pool = [item for item in self.replay_buffer if self.transition_meta.get(item[0], {}).get("uncertain", False) and not self.transition_meta.get(item[0], {}).get("teacher_action", True) and self.transition_meta.get(item[0], {}).get("multiobjective_safe", False)]
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
            queue_penalty = float(meta.get("queue_excess", 0.0)) * float(Registry.mapping["model_mapping"]["setting"].param["queue_penalty"])
            delay_penalty = float(meta.get("delay_excess", 0.0)) * float(Registry.mapping["model_mapping"]["setting"].param["delay_penalty"])
            if meta.get("counterfactual_checked", False):
                advantages.append(float(meta.get("counterfactual_advantage", 0.0)))
            else:
                advantages.append(0.0 if meta.get("teacher_action", True) else reward - baseline - queue_penalty - delay_penalty)
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

    def local_congestion(self):
        lane_count = self.world.get_info("lane_count")
        lane_vehicles = self.world.get_info("lane_vehicles")
        try:
            vehicle_speeds = self.world.eng.get_vehicle_speed()
        except Exception:
            vehicle_speeds = {}
        counts = [float(lane_count.get(lane, 0.0)) for lane in self.controlled_lanes]
        vehicles = [vehicle for lane in self.controlled_lanes for vehicle in lane_vehicles.get(lane, [])]
        stopped_ratio = (
            sum(float(vehicle_speeds.get(vehicle, 0.0)) <= 0.1 for vehicle in vehicles) / len(vehicles)
            if vehicles else 0.0
        )
        return (float(np.mean(counts)) if counts else 0.0), float(stopped_ratio)

    def remember(self, last_obs, last_phase, actions, actions_prob, rewards, obs, cur_phase, done, key):
        super().remember(last_obs, last_phase, actions, actions_prob, rewards, obs, cur_phase, done, key)
        teacher_action = int(getattr(self, "pending_teacher_action", int(np.asarray(actions).reshape(-1)[0])))
        actual_action = int(np.asarray(actions).reshape(-1)[0])
        uncertain = bool(getattr(self, "pending_uncertain", False))
        counterfactual_advantage = float(getattr(self, "pending_counterfactual_advantage", 0.0))
        counterfactual_checked = bool(getattr(self, "pending_counterfactual_checked", False))
        local_queue, local_delay = self.local_congestion()
        setting = Registry.mapping["model_mapping"]["setting"].param
        is_teacher = actual_action == teacher_action
        queue_excess = 0.0 if self.teacher_queue_ema is None else max(0.0, local_queue - self.teacher_queue_ema)
        delay_excess = 0.0 if self.teacher_delay_ema is None else max(0.0, local_delay - self.teacher_delay_ema)
        multiobjective_safe = not is_teacher and (
            (counterfactual_checked and counterfactual_advantage >= float(setting["counterfactual_min_advantage"]))
            or (
                not counterfactual_checked
                and self.teacher_queue_ema is not None
                and local_queue <= self.teacher_queue_ema + float(setting["queue_tolerance"])
                and local_delay <= self.teacher_delay_ema + float(setting["delay_tolerance"])
            )
        )
        self.transition_meta[key] = {"teacher_action": is_teacher, "uncertain": uncertain, "multiobjective_safe": multiobjective_safe, "queue_excess": queue_excess, "delay_excess": delay_excess, "counterfactual_advantage": counterfactual_advantage, "counterfactual_checked": counterfactual_checked}
        if uncertain:
            self.uncertain_count += 1
        if is_teacher:
            reward = float(np.asarray(rewards).reshape(-1)[0])
            self.teacher_reward_ema = reward if self.teacher_reward_ema is None else 0.95 * self.teacher_reward_ema + 0.05 * reward
            self.teacher_queue_ema = local_queue if self.teacher_queue_ema is None else 0.95 * self.teacher_queue_ema + 0.05 * local_queue
            self.teacher_delay_ema = local_delay if self.teacher_delay_ema is None else 0.95 * self.teacher_delay_ema + 0.05 * local_delay
            self.teacher_count += 1
        elif multiobjective_safe:
            self.multiobjective_safe_count += 1

    def reset(self):
        super().reset()
        self.episode_decisions = 0
        self.episode_overrides = 0

    def accept_safe_adapter(self):
        self.safe_adapter_state = copy.deepcopy(self.model.adapter.state_dict())
        self.safe_optimizer_state = copy.deepcopy(self.optimizer.state_dict())

    def restore_safe_adapter(self):
        self.model.adapter.load_state_dict(self.safe_adapter_state)
        self.target_model.load_state_dict(self.model.state_dict())
        self.optimizer.load_state_dict(self.safe_optimizer_state)
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
        cmp_action, _, can_change = self.cmp.choose_with_details(ugat_q)
        setting = Registry.mapping["model_mapping"]["setting"].param
        if not can_change:
            self.pending_teacher_action = cmp_action
            self.pending_uncertain = False
            return np.asarray([cmp_action])
        self.pending_teacher_action = cmp_action
        self.pending_uncertain = True
        pressures, _, _ = self.cmp.phase_pressures()
        downstream_mean, downstream_max = self.cmp.phase_downstream_loads()
        fused_scores, feasible = cmp_frap_phase_fusion(q, pressures, downstream_mean, downstream_max, float(setting["pressure_weight"]), float(setting["frap_weight"]), float(setting["downstream_weight"]), float(setting["max_downstream_lane_count"]))
        feasible &= pressure_trust_region(pressures, float(setting["max_normalized_pressure_regret"]))
        feasible[cmp_action] = True
        fused_scores = fused_scores.copy()
        fused_scores[np.arange(len(fused_scores)) != cmp_action] -= float(setting["action_deviation_penalty"])
        if not test and np.random.rand() <= self.epsilon:
            action = int(np.random.choice(np.flatnonzero(feasible)))
            changed = int(action != cmp_action)
            self.override_count += changed
            self.episode_overrides += changed
            return np.asarray([action])
        candidate = int(np.argmax(np.where(feasible, fused_scores, -np.inf)))
        changed = int(candidate != cmp_action)
        self.override_count += changed
        self.episode_overrides += changed
        return np.asarray([candidate])

    def counterfactual_probe_action(self, maximum_regret):
        """Return a near-pressure alternative for paired evaluation only."""
        pressures, _, _ = self.cmp.phase_pressures()
        cmp_action = int(np.argmax(pressures))
        alternatives = np.flatnonzero(pressure_trust_region(pressures, maximum_regret))
        alternatives = alternatives[alternatives != cmp_action]
        return int(np.random.choice(alternatives)) if len(alternatives) else None

    def save_model(self, e):
        path = self.adapter_dir / f"episode_{e}_rank_{self.rank}.pt"
        torch.save({"adapter": self.model.adapter.state_dict(), "optimizer_state": self.optimizer.state_dict(), "rank": self.rank, "state_schema": self.model.state_schema, "policy_schema": "joint_cmp_frap_v2"}, path)
        print(f"saved_trainable_adapter={path}", flush=True)
        print(f"teacher_samples={self.teacher_count}, uncertain_samples={self.uncertain_count}, multiobjective_safe_samples={self.multiobjective_safe_count}, adapter_overrides={self.override_count}", flush=True)
        return str(path)


def main():
    parser = argparse.ArgumentParser(description="Reward-aware CityFlow training of a UGAT residual adapter")
    parser.add_argument("--thread_num", type=int, default=4)
    parser.add_argument("--seed", type=int, default=4444)
    parser.add_argument("--formal_eval_seed", type=int, default=4444, help="fixed CityFlow seed used only for independent formal checkpoint selection")
    parser.add_argument("--exploration_seed", type=int, default=None, help="training-only RNG seed; formal CityFlow evaluation remains controlled by --seed")
    parser.add_argument("--episodes", type=int, default=5)
    parser.add_argument("--steps", type=int, default=9000)
    parser.add_argument("--learning_start", type=int, default=1000)
    parser.add_argument("--batch_size", type=int, default=64)
    parser.add_argument("--learning_rate", type=float, default=3e-5)
    parser.add_argument("--eval_steps", type=int, default=9000, help="same-protocol evaluation length after every episode")
    parser.add_argument("--cmp_uncertainty_margin", type=float, default=2.0, help="train adapter only when C-MP top-two pressure gap is at most this value")
    parser.add_argument("--override_advantage", type=float, default=0.15, help="minimum residual advantage required to replace C-MP")
    parser.add_argument("--max_override_rate", type=float, default=0.02, help="maximum fraction of per-episode decisions allowed to replace C-MP")
    parser.add_argument("--pressure_weight", type=float, default=1.00, help="joint score weight for normalized C-MP pressure")
    parser.add_argument("--frap_weight", type=float, default=0.08, help="joint score weight for bounded learned FRAP phase relation")
    parser.add_argument("--downstream_weight", type=float, default=0.00, help="joint score penalty weight for downstream occupancy")
    parser.add_argument("--max_normalized_pressure_regret", type=float, default=0.03, help="joint action may be at most this normalized C-MP pressure below the best phase")
    parser.add_argument("--action_deviation_penalty", type=float, default=0.005, help="joint-score regularizer charged to a phase different from C-MP's pressure optimum")
    parser.add_argument("--counterfactual_every", type=int, default=5, help="evaluate one paired CityFlow branch every N post-warmup decisions")
    parser.add_argument("--counterfactual_horizon", type=int, default=120, help="simulation seconds in each paired counterfactual rollout")
    parser.add_argument("--counterfactual_min_advantage", type=float, default=0.01, help="minimum paired advantage required to execute and train a FRAP candidate")
    parser.add_argument("--counterfactual_probe_regret", type=float, default=0.25, help="normalized C-MP pressure radius used only to create paired-evaluation alternatives")
    parser.add_argument("--counterfactual_travel_weight", type=float, default=1.0, help="weight for normalized paired Travel Time advantage")
    parser.add_argument("--pressure_prior_weight", type=float, default=0.0, help="C-MP normalized pressure contribution in FRAP candidate ranking")
    parser.add_argument("--max_pressure_regret", type=float, default=2.0, help="maximum C-MP pressure loss allowed for a FRAP override")
    parser.add_argument("--max_downstream_mean_increase", type=float, default=0.0, help="maximum candidate downstream mean load above C-MP action")
    parser.add_argument("--max_downstream_lane_count", type=float, default=15.0, help="absolute downstream lane vehicle-count veto threshold")
    parser.add_argument("--queue_penalty", type=float, default=2.0, help="training penalty applied to local queue increase over C-MP teacher EMA")
    parser.add_argument("--delay_penalty", type=float, default=1.0, help="training penalty applied to local stopped-ratio increase over C-MP teacher EMA")
    parser.add_argument("--queue_tolerance", type=float, default=0.0, help="maximum local queue increase permitted in an FRAP training sample")
    parser.add_argument("--delay_tolerance", type=float, default=0.0, help="maximum local stopped-ratio increase permitted in an FRAP training sample")
    parser.add_argument("--independent_validation_steps", type=int, default=9000, help="fresh-process CityFlow steps required before a checkpoint can be selected")
    parser.add_argument("--resume_candidate", action="store_true", help="continue from candidate_rank_<R>.pt retained by an earlier safe training run")
    parser.add_argument("--reset_candidate", action="store_true", help="discard only exploratory candidate_rank files and start subsequent training from the zero adapter")
    parser.add_argument("--run_label", default="", help="label for the immutable best-candidate archive; defaults to --prefix")
    parser.add_argument("--prefix", default="1x5_cmp_train")
    args = parser.parse_args()
    if args.episodes < 1 or args.steps < 1 or args.batch_size < 1 or args.independent_validation_steps < 1 or args.counterfactual_every < 1 or args.counterfactual_horizon < 1 or args.counterfactual_travel_weight < 0 or not 0 <= args.counterfactual_probe_regret <= 1 or args.cmp_uncertainty_margin < 0 or args.override_advantage < 0 or args.pressure_prior_weight < 0 or args.max_pressure_regret < 0 or args.max_downstream_mean_increase < 0 or args.max_downstream_lane_count < 0 or not 0 <= args.max_normalized_pressure_regret <= 1 or args.action_deviation_penalty < 0 or args.pressure_weight < 0 or args.frap_weight < 0 or args.downstream_weight < 0 or args.pressure_weight + args.frap_weight + args.downstream_weight <= 0 or args.queue_penalty < 0 or args.delay_penalty < 0 or args.queue_tolerance < 0 or args.delay_tolerance < 0 or not 0 <= args.max_override_rate <= 1:
        parser.error("episodes, steps and batch_size must be positive")
    checkpoint_dir = Path("/workspace/final/logs/cmp_frap_checkpoints")
    exploration_seed = args.seed if args.exploration_seed is None else args.exploration_seed
    random.seed(exploration_seed)
    np.random.seed(exploration_seed)
    torch.manual_seed(exploration_seed)
    if args.reset_candidate:
        for stale in checkpoint_dir.glob("candidate_rank_*.pt"):
            stale.unlink()
        (checkpoint_dir / "candidate_metrics.json").unlink(missing_ok=True)
    # The trainer reads these values from the local config copied into Docker.
    config = f'''includes:\n  - configs/tsc/base.yml\nmodel:\n  name: cmptrain1x5\n  train_model: true\n  test_model: false\n  load_model: false\n  graphic: false\n  one_hot: true\n  phase: true\n  epsilon: 0.05\n  epsilon_decay: 0.9995\n  epsilon_min: 0.01\n  learning_rate: {args.learning_rate}\n  batch_size: {args.batch_size}\n  gamma: 0.99\ntrainer:\n  episodes: {args.episodes}\n  steps: {args.steps}\n  learning_start: {args.learning_start}\n  buffer_size: 50000\n  action_interval: 10\n  update_model_rate: 1\n  update_target_rate: 200\n  test_when_train: false\n'''
    config = config.replace("  gamma: 0.99\ntrainer:", f"  gamma: 0.99\n  cmp_beta: 0.60\n  cmp_alpha: 0.60\n  cmp_uncertainty_margin: {args.cmp_uncertainty_margin}\n  override_advantage: {args.override_advantage}\n  max_override_rate: {args.max_override_rate}\n  pressure_prior_weight: {args.pressure_prior_weight}\n  max_pressure_regret: {args.max_pressure_regret}\n  max_downstream_mean_increase: {args.max_downstream_mean_increase}\n  max_downstream_lane_count: {args.max_downstream_lane_count}\n  pressure_weight: {args.pressure_weight}\n  frap_weight: {args.frap_weight}\n  downstream_weight: {args.downstream_weight}\n  max_normalized_pressure_regret: {args.max_normalized_pressure_regret}\n  action_deviation_penalty: {args.action_deviation_penalty}\n  counterfactual_every: {args.counterfactual_every}\n  counterfactual_horizon: {args.counterfactual_horizon}\n  counterfactual_min_advantage: {args.counterfactual_min_advantage}\n  queue_penalty: {args.queue_penalty}\n  delay_penalty: {args.delay_penalty}\n  queue_tolerance: {args.queue_tolerance}\n  delay_tolerance: {args.delay_tolerance}\n  t_min: 10\ntrainer:")
    config = config.replace("  epsilon: 0.05", "  epsilon: 0.20")
    config = config.replace(
        f"  counterfactual_min_advantage: {args.counterfactual_min_advantage}\n",
        f"  counterfactual_min_advantage: {args.counterfactual_min_advantage}\n  counterfactual_probe_regret: {args.counterfactual_probe_regret}\n",
    )
    config = config.replace("  test_when_train: false", f"  test_steps: {args.eval_steps}\n  test_when_train: true")
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
        Registry.mapping["model_mapping"]["setting"].param.update({"learning_rate": args.learning_rate, "batch_size": args.batch_size, "gamma": 0.99, "epsilon": 0.20, "epsilon_decay": 0.9995, "epsilon_min": 0.01, "cmp_beta": 0.60, "cmp_alpha": 0.60, "cmp_uncertainty_margin": args.cmp_uncertainty_margin, "override_advantage": args.override_advantage, "max_override_rate": args.max_override_rate, "pressure_prior_weight": args.pressure_prior_weight, "max_pressure_regret": args.max_pressure_regret, "max_downstream_mean_increase": args.max_downstream_mean_increase, "max_downstream_lane_count": args.max_downstream_lane_count, "pressure_weight": args.pressure_weight, "frap_weight": args.frap_weight, "downstream_weight": args.downstream_weight, "max_normalized_pressure_regret": args.max_normalized_pressure_regret, "action_deviation_penalty": args.action_deviation_penalty, "counterfactual_every": args.counterfactual_every, "counterfactual_horizon": args.counterfactual_horizon, "counterfactual_min_advantage": args.counterfactual_min_advantage, "queue_penalty": args.queue_penalty, "delay_penalty": args.delay_penalty, "queue_tolerance": args.queue_tolerance, "delay_tolerance": args.delay_tolerance, "resume_candidate": args.resume_candidate, "independent_validation_steps": args.independent_validation_steps, "validation_thread_num": args.thread_num, "seed": args.seed, "formal_eval_seed": args.formal_eval_seed, "run_label": args.run_label or args.prefix, "t_min": 10})
        Registry.mapping["model_mapping"]["setting"].param.update({"counterfactual_probe_regret": args.counterfactual_probe_regret, "counterfactual_travel_weight": args.counterfactual_travel_weight})
        print(f"training_protocol: episodes={args.episodes}, steps={args.steps}, learning_start={args.learning_start}, batch_size={args.batch_size}, learning_rate={args.learning_rate}, cmp_uncertainty_margin={args.cmp_uncertainty_margin}, override_advantage={args.override_advantage}, max_override_rate={args.max_override_rate}, pressure_prior_weight={args.pressure_prior_weight}, max_pressure_regret={args.max_pressure_regret}, max_downstream_mean_increase={args.max_downstream_mean_increase}, max_downstream_lane_count={args.max_downstream_lane_count}, queue_penalty={args.queue_penalty}, delay_penalty={args.delay_penalty}, queue_tolerance={args.queue_tolerance}, delay_tolerance={args.delay_tolerance}, independent_validation_steps={args.independent_validation_steps}, training_seed={args.seed}, formal_eval_seed={args.formal_eval_seed}, exploration_seed={exploration_seed}, resume_candidate={args.resume_candidate}", flush=True)
        runner.run()
    finally:
        sys.argv = old_argv
        CITYFLOW_CONFIG.write_text(cityflow_original, encoding="utf-8")
        write_training_loss_plot()


if __name__ == "__main__":
    main()
