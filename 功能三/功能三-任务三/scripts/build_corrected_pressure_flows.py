from __future__ import annotations
import json, random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(r"C:\Users\lauri\Desktop\提交程序汇总\03_功能三_赛道B经典交通管控算法场景适配与优化\任务2_协同优化算法实现\UGAT_FRAP_TRANSYT协同_雄安20路口工程\data\xiong_an_20")
BASE = json.loads((SOURCE / "flow_midday.json").read_text(encoding="utf-8"))
random.seed(20260816)
for level in (10, 20, 30):
    extra_count = round(len(BASE) * level / 100)
    extras = [dict(BASE[index]) for index in random.sample(range(len(BASE)), extra_count)]
    output = BASE + extras
    path = ROOT / "平峰压力扰动试验" / f"flow_midday_pressure{level}_ordered.json"
    path.write_text(json.dumps(output, ensure_ascii=False), encoding="utf-8")
    print(level, len(output), path)
