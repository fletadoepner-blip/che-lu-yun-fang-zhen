"""Run FRAP training over several CityFlow demand realizations.

Each invocation of the base trainer creates a fresh CityFlow world with one
training seed.  Checkpoint selection always uses a separate fixed evaluation
seed, so training diversity cannot change the competition comparison protocol.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


BASE_TRAINER = "/workspace/final/scripts/train_cmp_adapter_1x5.py"
CHECKPOINT_DIR = Path("/workspace/final/logs/cmp_frap_checkpoints")


def has_current_candidate() -> bool:
    """Return true only for a resumable candidate of the current policy."""
    metrics_path = CHECKPOINT_DIR / "candidate_metrics.json"
    try:
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    ranks_exist = all((CHECKPOINT_DIR / f"candidate_rank_{rank}.pt").exists() for rank in range(5))
    return ranks_exist and metrics.get("policy_schema") == "joint_cmp_frap_v2"


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-scenario CityFlow training for the phase-aware FRAP adapter")
    parser.add_argument("--train_seeds", default="4101,4102,4103", help="comma-separated CityFlow seeds used for training worlds")
    parser.add_argument("--formal_eval_seed", type=int, default=4444, help="fixed independent evaluation seed; use 4444 for the established baseline")
    parser.add_argument("--reset_candidate", action="store_true", help="discard prior exploratory candidate before the first scenario")
    args, forwarded = parser.parse_known_args()
    try:
        train_seeds = [int(value.strip()) for value in args.train_seeds.split(",") if value.strip()]
    except ValueError as exc:
        parser.error(f"--train_seeds must be comma-separated integers: {exc}")
    if not train_seeds:
        parser.error("--train_seeds must contain at least one seed")

    # Do not forward controls that are managed per scenario here, including
    # their values.  All other base-trainer arguments remain available.
    managed_with_value = {"--seed", "--formal_eval_seed", "--exploration_seed"}
    forwarded_clean = []
    iterator = iter(forwarded)
    for value in iterator:
        if value in {"--reset_candidate", "--resume_candidate"}:
            continue
        if value in managed_with_value:
            next(iterator, None)
            continue
        forwarded_clean.append(value)
    forwarded = forwarded_clean
    for index, train_seed in enumerate(train_seeds):
        command = [sys.executable, BASE_TRAINER, *forwarded, "--seed", str(train_seed), "--formal_eval_seed", str(args.formal_eval_seed), "--exploration_seed", str(train_seed + 100_000)]
        if index == 0:
            if args.reset_candidate:
                command.append("--reset_candidate")
            elif has_current_candidate():
                command.append("--resume_candidate")
                print("multi_scenario_resume=global_best_safe_candidate", flush=True)
            else:
                # Clear stale checkpoints from a previous policy schema so
                # their score cannot block a valid current-policy candidate.
                if (CHECKPOINT_DIR / "candidate_metrics.json").exists():
                    command.append("--reset_candidate")
                    print("multi_scenario_reset=obsolete_or_incomplete_candidate", flush=True)
                print("multi_scenario_start=neutral_joint_baseline_no_resumable_candidate", flush=True)
        else:
            if not has_current_candidate():
                # No safe continuation exists, so explore the next demand
                # realization from the neutral policy instead of ending the
                # complete multi-scenario experiment prematurely.
                command.append("--reset_candidate")
                print("multi_scenario_continue=neutral_policy_no_safe_candidate", flush=True)
            else:
                command.append("--resume_candidate")
        print(f"multi_scenario_start index={index + 1}/{len(train_seeds)}, training_seed={train_seed}, formal_eval_seed={args.formal_eval_seed}", flush=True)
        result = subprocess.run(command, cwd="/DaRL/UGAT_Docker", check=False)
        if result.returncode != 0:
            raise SystemExit(result.returncode)
    print("multi_scenario_complete=true", flush=True)


if __name__ == "__main__":
    main()
