"""Fixed-time and queue-responsive traffic signal experiments for SUMO."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
SCENARIO = PROJECT / "scenario"
RESULTS = PROJECT / "results"
DEFAULT_GAIN = -44.0


def import_sumo_tools() -> None:
    """Make this script work with the SUMO_HOME packaged by the project conda env."""
    sumo_home = os.environ.get("SUMO_HOME")
    if sumo_home:
        tools_dir = Path(sumo_home) / "tools"
        if tools_dir.exists():
            sys.path.append(str(tools_dir))
    try:
        import traci  # noqa: F401
        from sumolib import checkBinary  # noqa: F401
    except ImportError as error:
        raise SystemExit(
            "TraCI is unavailable. Configure PyCharm to use "
            r"C:\Users\lauri\anaconda3\envs\project1\python.exe"
        ) from error


def phase_incoming_lanes(links, state: str) -> set[str]:
    """Return incoming lanes permitted by a green signal state."""
    lanes: set[str] = set()
    for index, signal in enumerate(state):
        if signal not in "gG" or index >= len(links):
            continue
        for connection in links[index]:
            lanes.add(connection[0])
    return lanes


def collect_metrics(tripinfo_path: Path, queue_samples: list[int]) -> dict[str, float | int]:
    root = ET.parse(tripinfo_path).getroot()
    trips = root.findall("tripinfo")
    if not trips:
        raise RuntimeError(
            "SUMO produced no completed vehicles; metrics would be invalid. "
            "Increase --duration or check the scenario and SUMO log."
        )

    required_trip_fields = ("duration", "waitingTime", "timeLoss")
    missing = [field for field in required_trip_fields if any(field not in trip.attrib for trip in trips)]
    if missing:
        raise RuntimeError(f"SUMO tripinfo is missing required metric fields: {missing}")

    def mean(attribute: str) -> float:
        return sum(float(item.get(attribute, "0")) for item in trips) / len(trips)

    return {
        "completed_vehicles": len(trips),
        "mean_travel_time_s": round(mean("duration"), 2),
        "mean_waiting_time_s": round(mean("waitingTime"), 2),
        "mean_time_loss_s": round(mean("timeLoss"), 2),
        "mean_queue_vehicles": round(sum(queue_samples) / max(1, len(queue_samples)), 2),
    }


def run(mode: str, duration: int, gui: bool, gain: float, seed: int = 42) -> Path:
    import_sumo_tools()
    import traci
    from sumolib import checkBinary
    from prepare_dataset1_scenario import prepare

    RESULTS.mkdir(exist_ok=True)
    config_path = prepare(checkBinary("netconvert"))
    final_tripinfo_path = RESULTS / f"tripinfo_{mode}.xml"
    # A unique output prevents concurrent GUI/CLI runs from corrupting a shared XML file.
    tripinfo_path = RESULTS / f".tripinfo_{mode}_{uuid.uuid4().hex}.xml"
    metrics_path = RESULTS / f"metrics_{mode}.json"
    command = [
        checkBinary("sumo-gui" if gui else "sumo"), "-c", str(config_path),
        "--tripinfo-output", str(tripinfo_path), "--no-step-log", "true",
        "--duration-log.disable", "true", "--no-warnings", "true", "--seed", str(seed), "--quit-on-end", "true",
    ]
    if gui:
        command.extend(["--start", "--delay", "80"])

    traci.start(command)
    traffic_light = traci.trafficlight.getIDList()[0]
    program_id = "dataset_adaptive" if mode == "adaptive" else "dataset_fixed"
    traci.trafficlight.setProgram(traffic_light, program_id)
    links = traci.trafficlight.getControlledLinks(traffic_light)
    logic = next(item for item in traci.trafficlight.getAllProgramLogics(traffic_light)
                 if item.programID == program_id)
    green_lanes = [phase_incoming_lanes(links, phase.state) for phase in logic.phases]
    base_green = [phase.duration if lanes else 0 for phase, lanes in zip(logic.phases, green_lanes)]
    total_base_green = sum(base_green)
    incoming_lanes = sorted(set().union(*green_lanes))
    previous_phase = None
    queue_samples: list[int] = []

    try:
        for _ in range(duration):
            phase = traci.trafficlight.getPhase(traffic_light)
            if mode == "adaptive" and phase != previous_phase:
                state = traci.trafficlight.getRedYellowGreenState(traffic_light)
                if "G" in state or "g" in state:
                    pressures = [sum(traci.lane.getLastStepHaltingNumber(lane) for lane in lanes)
                                 for lanes in green_lanes]
                    current_pressure = pressures[phase]
                    total_pressure = sum(pressures)
                    base_share = base_green[phase] / total_base_green
                    demand_share = current_pressure / total_pressure if total_pressure else base_share
                    current_vehicles = sum(
                        traci.lane.getLastStepVehicleNumber(lane) for lane in green_lanes[phase]
                    )
                    if current_vehicles == 0:
                        target_green = 12
                    else:
                        target_green = round(base_green[phase] + gain * (demand_share - base_share))
                    target_green = max(12, min(55, target_green))
                    if target_green != base_green[phase]:
                        traci.trafficlight.setPhaseDuration(traffic_light, target_green)
            previous_phase = phase
            queue_samples.append(sum(traci.lane.getLastStepHaltingNumber(lane) for lane in incoming_lanes))
            traci.simulationStep()
    finally:
        traci.close()

    metrics = collect_metrics(tripinfo_path, queue_samples)
    tripinfo_path.replace(final_tripinfo_path)
    metrics.update({"strategy": mode, "simulation_seconds": duration,
                    "controller_gain": gain, "random_seed": seed})
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    return metrics_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run fixed or adaptive SUMO signal control.")
    parser.add_argument("--mode", choices=("fixed", "adaptive", "both"), default="both")
    parser.add_argument("--duration", type=int, default=7200)
    parser.add_argument("--gain", type=float, default=DEFAULT_GAIN,
                        help="Queue-pressure green-time redistribution gain.")
    parser.add_argument("--seed", type=int, default=42, help="SUMO random seed.")
    parser.add_argument("--gui", action="store_true", help="Run a single strategy in SUMO-GUI.")
    args = parser.parse_args()
    if args.gui and args.mode == "both":
        parser.error("SUMO-GUI requires --mode fixed or --mode adaptive.")

    modes = ("fixed", "adaptive") if args.mode == "both" else (args.mode,)
    for mode in modes:
        path = run(mode, args.duration, args.gui, args.gain, args.seed)
        print(f"{mode}: {path}")


if __name__ == "__main__":
    main()
