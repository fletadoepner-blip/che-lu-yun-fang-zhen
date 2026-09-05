# -*- coding: utf-8 -*-
"""契约一致性测试：模型注册表 vs 实际权重文件（不依赖 torch/cityflow）。"""
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_registry_files_exist():
    reg = json.loads((ROOT / "contracts" / "model_registry.json").read_text(encoding="utf-8"))
    for m in reg["models"]:
        f = ROOT / m["file"]
        assert f.is_file(), f"model file missing: {m['file']}"
        if m["sha256_prefix"]:
            import hashlib
            actual = hashlib.sha256(f.read_bytes()).hexdigest()
            assert actual.startswith(m["sha256_prefix"].lower()), f"SHA mismatch for {m['file']}"


def test_pt_are_torch_archives():
    for rel in ("model/frozen_ugat_4x4.pt", "model/frap_adapter.pt", "model/ugat1x5_best.pt",
                "model/official_ugat_best.pt", "model/ugat_best_1.pt"):
        with zipfile.ZipFile(ROOT / rel) as z:
            assert any(n.endswith("data.pkl") for n in z.namelist()), f"not torch archive: {rel}"


def test_schema_dimensions():
    obs = json.loads((ROOT / "contracts" / "observation.schema.json").read_text(encoding="utf-8"))
    act = json.loads((ROOT / "contracts" / "control_action.schema.json").read_text(encoding="utf-8"))
    assert obs["properties"]["dim"]["const"] == 20
    assert act["properties"]["dim"]["const"] == 8


def test_data_reference():
    data = ROOT / "data" / "xiong_an_20"
    assert data.is_dir(), "data/xiong_an_20 not accessible"
    for f in ("roadnet.json", "flow_morning.json", "cityflow.config.json"):
        assert (data / f).is_file(), f"missing {f}"
