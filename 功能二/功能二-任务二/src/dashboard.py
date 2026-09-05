"""Create a portable HTML dashboard from platform metrics and traces."""
from __future__ import annotations
import argparse, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = """<!doctype html><meta charset='utf-8'><title>Xiong'an 20-junction dashboard</title><style>body{font:14px Arial;margin:24px;color:#17212b}canvas{border:1px solid #cbd5df}pre{background:#f6f8fa;padding:12px}</style><h1>Xiong'an Rongdong: 20-junction simulation</h1><canvas id='c' width='1000' height='360'></canvas><pre id='summary'></pre><script>const rows=__DATA__;let c=document.querySelector('#c'),x=c.getContext('2d'),m=Math.max(1,...rows.map(r=>r.queue_proxy));x.strokeStyle='#0b6';x.beginPath();rows.forEach((r,i)=>{let px=i*1000/Math.max(1,rows.length-1),py=340-r.queue_proxy/m*310;i?x.lineTo(px,py):x.moveTo(px,py)});x.stroke();document.querySelector('#summary').textContent=JSON.stringify(rows.at(-1)||{},null,2)</script>"""
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("trace", type=Path); ap.add_argument("--out", type=Path, default=ROOT/"outputs"/"dashboard.html"); a=ap.parse_args()
    a.out.parent.mkdir(parents=True,exist_ok=True); a.out.write_text(HTML.replace("__DATA__", json.dumps(json.loads(a.trace.read_text(encoding='utf-8')))),encoding="utf-8")
    print(a.out)
if __name__ == "__main__": main()
