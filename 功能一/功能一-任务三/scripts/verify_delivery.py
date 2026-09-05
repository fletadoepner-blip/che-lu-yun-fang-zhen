"""功能一·任务三 交付包静态校验：不依赖 torch、cityflow、Docker。

检查内容：
1. 必需目录与文件齐全；
2. contracts/ 下 JSON 可解析且为合法对象；
3. model/ 下 .pt 为合法的 torch zip 存档（torch.save 格式）；
4. data/xiong_an_20 数据可访问（junction 或真实文件）；
5. 关键文档与报告存在。
"""
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
errors = []


def require(rel: str) -> Path:
    p = ROOT / rel
    if not p.exists():
        errors.append(f"missing: {rel}")
    return p


def require_json(rel: str):
    p = require(rel)
    if p.exists():
        try:
            json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"invalid JSON {rel}: {exc}")


def require_pt(rel: str):
    p = require(rel)
    if p.exists():
        try:
            with zipfile.ZipFile(p) as z:
                names = z.namelist()
                if not any(n.endswith("data.pkl") for n in names):
                    errors.append(f"not a torch archive {rel}: no data.pkl")
        except zipfile.BadZipFile:
            errors.append(f"not a zip/torch archive {rel}")


def check_data():
    # 数据目录（junction 或真实目录）
    data = ROOT / "data" / "xiong_an_20"
    if not data.is_dir():
        errors.append("missing dir: data/xiong_an_20 (见 data/README_数据引用说明.md)")
        return
    for f in ("roadnet.json", "flow_morning.json", "flow_midday.json", "flow_evening.json",
              "source_signal_plans.json", "topology.json", "cityflow.config.json"):
        if not (data / f).is_file():
            errors.append(f"missing data file: data/xiong_an_20/{f}")


# --- 文档与根文件 ---
require("README.md")
require("requirements.txt")
require("Dockerfile")
require("docker-compose.yml")

# --- 配置 ---
for f in ("xiong_an_20.yaml", "farp_xiong_an_20.yml", "cmp1x3.yml", "cmp1x5.yml", "cmptrain1x5.yml", "farp4x4.yml"):
    p = require(f"configs/{f}")
    if p.exists() and p.stat().st_size == 0:
        errors.append(f"empty config: configs/{f}")

# --- 契约 ---
require_json("contracts/model_registry.json")
require_json("contracts/observation.schema.json")
require_json("contracts/control_action.schema.json")

# --- 模型权重 ---
require_pt("model/frozen_ugat_4x4.pt")
require_pt("model/frap_adapter.pt")
require_pt("model/ugat1x5_best.pt")
require_pt("model/official_ugat_best.pt")
require_pt("model/ugat_best_1.pt")
require_pt("outputs/4x4_frap/4x4_farp_adapter.pt")
require("model/模型版本说明.md")

# --- 数据 ---
check_data()

# --- 源码与脚本 ---
for f in ("src/ugat_frap.py", "src/algorithms.py", "src/run_cityflow.py", "src/train_adapter.py",
          "src/validate_scenario.py", "scripts/run_farp_xiong_an_20.py",
          "scripts/run_cmp_1x5.py", "scripts/run_farp_4x4.py", "scripts/verify_delivery.py"):
    require(f)

# --- 文档 ---
for f in ("docs/API.md", "docs/ARCHITECTURE.md", "docs/MODEL_DESIGN.md", "docs/TRAINING.md",
          "docs/ABLATION.md", "docs/INTERFACE_PROTOCOL.md", "docs/DELIVERY_CHECKLIST.md",
          "docs/RUN_CMP_1X3.md", "docs/RUN_XIONG_AN_20.md", "docs/RUN_4X4.md", "docs/RUN_CMP_1X5.md",
          "docs/CITYFLOW_INSTALL.md", "data/README_数据引用说明.md", "outputs/1x3_cmp/README_结果预留说明.md"):
    require(f)

# --- 实验输出 ---
for f in ("outputs/xiong_an_20/metrics.csv", "outputs/xiong_an_20/trace_ugat_frap_morning.json",
          "outputs/1x5_cmp/1x5_cmp_simulation_metrics.csv", "outputs/1x5_cmp/1x5_cmp_latest_metrics.json",
          "outputs/1x5_cmp/legacy_cmp_adapter_best/best_metrics.json",
          "outputs/4x4_frap/4x4_simulation_metrics.csv", "outputs/4x4_frap/4x4_latest_metrics.json"):
    require(f)

# --- 报告 ---
for f in ("reports/雄安新区20路口高保真仿真验证平台报告.docx",
          "reports/1x5_Frozen_UGAT_CMP_FRAP_CityFlow_Report.docx",
          "reports/4x4_UGAT_FRAP_cityflow_report.docx"):
    require(f)

# --- third_party ---
require("third_party/CityFlow/src/cityflow.cpp")
require("third_party/CityFlow/setup.py")

if errors:
    print("FAIL: 功能一·任务三 交付校验未通过：")
    for e in errors:
        print("  -", e)
    sys.exit(1)

print("PASS: F1-T3 delivery structure, JSON contracts, torch archives and data reference are complete.")
