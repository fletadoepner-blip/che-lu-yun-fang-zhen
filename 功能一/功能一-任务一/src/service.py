"""SUMO 场景生成与运行时数据接口。"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE: dict[str, Any] = {"running": False, "intersection_ids": [], "current_time_s": 0.0}


def _json_error(message: str, status: int):
    from flask import jsonify
    return jsonify({"error": message}), status


def create_app():
    from flask import Flask, jsonify, request, send_file
    try:
        from flask_cors import CORS
    except ImportError:
        CORS = None

    app = Flask(__name__)
    if CORS:
        CORS(app)

    @app.get("/health")
    def health():
        return jsonify({"service": "f1-t1-sumo-api", "status": "ok", "simulation_running": STATE["running"]})

    @app.get("/v1/scenario/metadata")
    def scenario_metadata():
        return send_file(ROOT / "configs" / "default_scenario.json", mimetype="application/json")

    @app.post("/v1/scenario/generate")
    def generate_scenario():
        payload = request.get_json(silent=True) or {}
        try:
            lat, lon = float(payload["latitude"]), float(payload["longitude"])
            radius, duration = int(payload.get("radius_m", 300)), int(payload.get("duration_s", 3600))
        except (KeyError, TypeError, ValueError):
            return _json_error("latitude and longitude are required numeric fields", 400)
        if not (-90 <= lat <= 90 and -180 <= lon <= 180 and 50 <= radius <= 5000 and 60 <= duration <= 86400):
            return _json_error("coordinates, radius_m or duration_s outside contract range", 400)
        try:
            archive = _build_scenario(lat, lon, radius, duration)
            return send_file(archive, as_attachment=True, download_name="sumo_scenario.zip", mimetype="application/zip")
        except RuntimeError as exc:
            return _json_error(str(exc), 503)
        except Exception as exc:  # external OSM/SUMO errors must reach caller clearly
            return _json_error(f"scenario generation failed: {exc}", 500)

    @app.post("/v1/simulation/start")
    def simulation_start():
        payload = request.get_json(silent=True) or {}
        config_path = payload.get("config_path")
        if not isinstance(config_path, str):
            return _json_error("config_path is required", 400)
        path = (ROOT / config_path).resolve() if not Path(config_path).is_absolute() else Path(config_path)
        if not path.is_file():
            return _json_error("config_path not found", 404)
        try:
            import traci
            traci.start(["sumo", "-c", str(path), "--start", "--quit-on-end", "--time-to-teleport", "-1"])
            STATE.update(running=True, intersection_ids=list(traci.trafficlight.getIDList()), current_time_s=0.0)
            return jsonify({"status": "started", "intersection_ids": STATE["intersection_ids"]})
        except ImportError:
            return _json_error("traci is not installed; install requirements.txt", 503)
        except Exception as exc:
            return _json_error(f"SUMO start failed: {exc}", 500)

    @app.get("/v1/simulation/state")
    def simulation_state():
        if not STATE["running"]:
            return _json_error("no simulation is running", 409)
        try:
            import traci
            requested = request.args.get("intersection_id")
            targets = [requested] if requested else STATE["intersection_ids"]
            if requested and requested not in STATE["intersection_ids"]:
                return _json_error("unknown intersection_id", 404)
            observations = {}
            for junction in targets:
                lanes = {}
                for group in traci.trafficlight.getControlledLinks(junction):
                    for link in group:
                        lane = link[0]
                        lanes[lane] = {"vehicle_count": traci.lane.getLastStepVehicleNumber(lane), "queue_count": traci.lane.getLastStepHaltingNumber(lane), "speed_mps": traci.lane.getLastStepMeanSpeed(lane), "occupancy_pct": traci.lane.getLastStepOccupancy(lane)}
                observations[junction] = {"phase": traci.trafficlight.getPhase(junction), "phase_duration_s": traci.trafficlight.getPhaseDuration(junction), "queue_length": sum(item["queue_count"] for item in lanes.values()), "lanes": lanes}
            return jsonify({"time_s": traci.simulation.getCurrentTime() / 1000.0, "intersections": observations})
        except Exception as exc:
            return _json_error(f"state query failed: {exc}", 500)

    @app.post("/v1/simulation/action")
    def simulation_action():
        if not STATE["running"]:
            return _json_error("no simulation is running", 409)
        payload = request.get_json(silent=True) or {}
        junction, phase = payload.get("intersection_id"), payload.get("phase")
        if not isinstance(junction, str) or not isinstance(phase, int):
            return _json_error("intersection_id (string) and phase (integer) are required", 400)
        if junction not in STATE["intersection_ids"] or phase < 0:
            return _json_error("unknown intersection_id or invalid phase", 400)
        try:
            import traci
            traci.trafficlight.setPhase(junction, phase)
            if "duration_s" in payload:
                traci.trafficlight.setPhaseDuration(junction, float(payload["duration_s"]))
            return jsonify({"status": "accepted", "intersection_id": junction, "phase": traci.trafficlight.getPhase(junction)})
        except Exception as exc:
            return _json_error(f"action failed: {exc}", 500)

    @app.post("/v1/simulation/step")
    def simulation_step():
        if not STATE["running"]:
            return _json_error("no simulation is running", 409)
        payload = request.get_json(silent=True) or {}
        steps = payload.get("steps", 1)
        if not isinstance(steps, int) or not 1 <= steps <= 3600:
            return _json_error("steps must be an integer from 1 to 3600", 400)
        try:
            import traci
            for _ in range(steps): traci.simulationStep()
            STATE["current_time_s"] = traci.simulation.getCurrentTime() / 1000.0
            return jsonify({"status": "stepped", "time_s": STATE["current_time_s"]})
        except Exception as exc:
            return _json_error(f"step failed: {exc}", 500)

    @app.post("/v1/simulation/close")
    def simulation_close():
        try:
            if STATE["running"]:
                import traci
                traci.close()
        finally:
            STATE.update(running=False, intersection_ids=[], current_time_s=0.0)
        return jsonify({"status": "closed"})

    return app


def _build_scenario(lat: float, lon: float, radius: int, duration: int) -> Path:
    """Download OSM and package a self-contained SUMO scenario."""
    import subprocess, tempfile, zipfile
    try:
        import osmnx as ox
    except ImportError as exc:
        raise RuntimeError("osmnx is not installed; install requirements.txt") from exc
    sumo_home = os.getenv("SUMO_HOME")
    if not sumo_home:
        raise RuntimeError("SUMO_HOME is not set")
    temp = Path(tempfile.mkdtemp(prefix="sumo_scenario_"))
    osm, net, routes, cfg, archive = (temp / name for name in ("network.osm", "network.net.xml", "traffic.rou.xml", "scenario.sumocfg", "sumo_scenario.zip"))
    graph = ox.graph_from_point((lat, lon), dist=radius, network_type="drive", simplify=False)
    ox.save_graph_xml(graph, filepath=osm)
    subprocess.run([str(Path(sumo_home) / "bin" / "netconvert"), "--osm-files", str(osm), "-o", str(net), "--geometry.remove", "--roundabouts.guess", "--ramps.guess", "--junctions.join", "--tls.guess", "--tls.guess.threshold", "0", "--tls.join"], check=True, capture_output=True, text=True)
    subprocess.run([sys.executable, str(Path(sumo_home) / "tools" / "randomTrips.py"), "-n", str(net), "-r", str(routes), "-o", str(temp / "trips.trips.xml"), "-e", str(duration), "--period", "1", "--flows", "10"], check=True, capture_output=True, text=True)
    cfg.write_text(f'<?xml version="1.0" encoding="UTF-8"?>\n<configuration><input><net-file value="network.net.xml"/><route-files value="traffic.rou.xml"/></input><time><begin value="0"/><end value="{duration}"/></time></configuration>\n', encoding="utf-8")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in (net, routes, cfg): zf.write(file, file.name)
    return archive

