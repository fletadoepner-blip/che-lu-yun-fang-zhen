"""Run a selected signal-control adapter against the integrated CityFlow network."""
from __future__ import annotations

import argparse, bisect, csv, json, sys, time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "src"))
from algorithms import FixedTimeAlgorithm, MaxPressureAlgorithm

CONTROL_GROUP = {"W": "W", "E": "E", "N": "N", "S": "S", "NW": "N", "NE": "N", "SW": "S", "SE": "S"}


def lane_count(engine, road_id: str, lane: int) -> int:
    return int(engine.get_lane_vehicle_count().get(f"{road_id}_{lane}", 0))


def collect_state(engine, roadnet: dict) -> np.ndarray:
    """Aggregate feeder and upstream connector counts into 12 fixed movement slots."""
    rows = []
    for node in range(1, 21):
        inter = next(i for i in roadnet["intersections"] if i["id"] == f"j_{node:02d}")
        groups = {d: [] for d in "WENS"}
        for rid in inter["roads"]:
            road = next(r for r in roadnet["roads"] if r["id"] == rid)
            if road["endIntersection"] != f"j_{node:02d}": continue
            if rid.startswith("feed_"): groups[CONTROL_GROUP[rid.rsplit("_", 1)[1]]].append(rid)
            elif rid.startswith("link_"):
                # The frozen 4x4 controller accepts cardinal features only.
                # Folded diagonal links are retained by CityFlow and aggregate
                # into their nearest cardinal arrival group for inference.
                departure = rid.split("_")[2]; groups[CONTROL_GROUP[{"W":"E", "E":"W", "N":"S", "S":"N", "NW":"SE", "NE":"SW", "SW":"NE", "SE":"NW"}[departure]]].append(rid)
        values = []
        for d in "WENS":
            left = sum(lane_count(engine, rid, 0) for rid in groups[d]); straight_right = sum(lane_count(engine, rid, 1) for rid in groups[d])
            values += [left, straight_right, straight_right]
        rows.append(values)
    return np.asarray(rows, dtype=np.float32)


def vehicle_snapshot(engine, roadnet: dict, limit: int = 1000) -> list[dict[str, float | str]]:
    """Compact vehicle positions for the host-side live monitor."""
    road_length = {}
    for road in roadnet["roads"]:
        points = road["points"]
        road_length[road["id"]] = sum(((b["x"] - a["x"]) ** 2 + (b["y"] - a["y"]) ** 2) ** 0.5 for a, b in zip(points, points[1:]))
    result = []
    for vehicle_id in sorted(engine.get_vehicles())[:limit]:
        info = engine.get_vehicle_info(vehicle_id)
        road = info.get("road", "")
        if road:
            route = info.get("route", "").split(); index = route.index(road) if road in route else 0
            local_distance = float(info.get("distance", 0.0)) - sum(road_length.get(item, 0.0) for item in route[:index])
            result.append({"id": vehicle_id, "road": road, "distance": max(0.0, local_distance), "speed": float(info.get("speed", 0.0))})
    return result


def build_algorithm(name: str, count: int, checkpoint: Path):
    if name == "fixed": return FixedTimeAlgorithm(count)
    if name == "max_pressure": return MaxPressureAlgorithm()
    if name == "ugat_frap":
        import torch
        from ugat_frap import UGATFRAPController
        model = UGATFRAPController(checkpoint); adapter = ROOT / "model" / "frap_adapter.pt"
        if adapter.exists(): model.load_adapter(adapter)
        model.assert_frozen(); model.eval()
        class TorchAdapter:
            name = "ugat_frap"
            def choose(self, state):
                # The frozen 4x4 network expects 12 lane values followed by 8 phase flags.
                phase = np.zeros((len(state), 8), dtype=np.float32); phase[:, 0] = 1
                return model.choose_actions(torch.from_numpy(np.concatenate((state, phase), axis=1))).cpu().numpy()
        return TorchAdapter()
    raise ValueError(f"Unsupported algorithm {name}")


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--period", choices=("morning", "midday", "evening"), default="morning")
    ap.add_argument("--algorithm", choices=("fixed", "max_pressure", "ugat_frap"), default="ugat_frap")
    ap.add_argument("--steps", type=int, default=7500); ap.add_argument("--decision-interval", type=int, default=10); ap.add_argument("--threads", type=int, default=1)
    ap.add_argument("--out-dir", type=Path, default=ROOT / "outputs"); ap.add_argument("--live-trace", type=Path, default=None); ap.add_argument("--visual-delay-ms", type=int, default=0); ap.add_argument("--live-interval", type=int, default=10); args = ap.parse_args()
    try: import cityflow
    except ImportError as exc: raise SystemExit("CityFlow is required for runtime. Use Docker or install cityflow in Linux.") from exc
    data = ROOT / "data" / "xiong_an_20"; config = json.loads((data / "cityflow.config.json").read_text(encoding="utf-8")); config["flowFile"] = f"flow_{args.period}.json"; config["dir"] = str(data.resolve()).replace("\\", "/") + "/"
    args.out_dir.mkdir(parents=True, exist_ok=True); runtime_config = args.out_dir / f"cityflow_{args.period}.json"; runtime_config.write_text(json.dumps(config, indent=2), encoding="utf-8")
    engine = cityflow.Engine(str(runtime_config), thread_num=args.threads); roadnet = json.loads((data / "roadnet.json").read_text(encoding="utf-8")); departures = sorted(item["startTime"] for item in json.loads((data / config["flowFile"]).read_text(encoding="utf-8")))
    controller = build_algorithm(args.algorithm, 20, ROOT / "model" / "frozen_ugat_4x4.pt"); trace = []; started = time.perf_counter()
    live_path = args.live_trace or args.out_dir / f"live_{args.algorithm}_{args.period}.jsonl"; live_path.parent.mkdir(parents=True, exist_ok=True)
    with live_path.open("w", encoding="utf-8") as live:
        actions = np.zeros(20, dtype=np.int64)
        for tick in range(args.steps):
            if tick % args.decision_interval == 0:
                state = collect_state(engine, roadnet); actions = controller.choose(state)
                for node, action in enumerate(actions, start=1): engine.set_tl_phase(f"j_{node:02d}", int(action) + 1)
            if tick % args.live_interval == 0:
                display_state = collect_state(engine, roadnet)
                record = {"time_s": tick, "active_vehicles": int(engine.get_vehicle_count()), "scheduled_vehicles": bisect.bisect_right(departures, tick), "total_demand": len(departures), "queue_proxy": int(display_state.sum()), "node_queue_proxy": display_state.sum(axis=1).astype(int).tolist(), "actions": actions.tolist(), "vehicles": vehicle_snapshot(engine, roadnet)}
                trace.append(record); live.write(json.dumps(record, ensure_ascii=False) + "\n"); live.flush()
            if tick % args.decision_interval == 0:
                if args.visual_delay_ms > 0: time.sleep(args.visual_delay_ms / 1000.0)
            engine.next_step()
    elapsed = time.perf_counter() - started; final = trace[-1] if trace else {"active_vehicles": 0, "queue_proxy": 0}
    metrics = {"algorithm": controller.name, "period": args.period, "steps": args.steps, "wall_seconds": round(elapsed, 3), "steps_per_second": round(args.steps / max(elapsed, 1e-9), 2), "final_active_vehicles": final["active_vehicles"], "final_queue_proxy": final["queue_proxy"]}
    with live_path.open("a", encoding="utf-8") as live: live.write(json.dumps({"status": "complete", "metrics": metrics}, ensure_ascii=False) + "\n")
    (args.out_dir / f"trace_{args.algorithm}_{args.period}.json").write_text(json.dumps(trace, ensure_ascii=False), encoding="utf-8")
    path = args.out_dir / "metrics.csv"; exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(metrics));
        if not exists: writer.writeheader()
        writer.writerow(metrics)
    print(json.dumps(metrics, ensure_ascii=False))


if __name__ == "__main__": main()
