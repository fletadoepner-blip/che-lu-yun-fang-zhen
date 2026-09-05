"""无需 Flask、SUMO 或网络的交付包静态校验。"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
required = ["README.md", "requirements.txt", "sim_api_service.py", "src/service.py", "configs/default_scenario.json", "contracts/scenario_request.schema.json", "contracts/observation.schema.json", "contracts/control_action.schema.json", "docs/API.md", "docs/ARCHITECTURE.md", "docs/INTERFACE_PROTOCOL.md", "docs/DELIVERY_CHECKLIST.md", "data/xiong_an_sample/intersection_registry.json", "data/xiong_an_sample/observation_example.json"]
missing = [p for p in required if not (ROOT / p).is_file()]
for item in required:
    if item.endswith(".json") and (ROOT / item).is_file(): json.loads((ROOT / item).read_text(encoding="utf-8"))
if missing: raise SystemExit("Missing delivery files: " + ", ".join(missing))
print("PASS: F1-T1 delivery structure and JSON contracts are complete.")
