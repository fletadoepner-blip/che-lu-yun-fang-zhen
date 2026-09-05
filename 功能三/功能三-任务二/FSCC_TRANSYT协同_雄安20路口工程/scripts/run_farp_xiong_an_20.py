"""4x4-compatible wrapper around the 20-junction CityFlow runner."""
from pathlib import Path
import argparse, subprocess, sys
ROOT = Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('--period',choices=['morning','midday','evening'],default='morning');p.add_argument('--algorithm',choices=['ugat_frap','ugat_frap_transyt','max_pressure','fixed','transyt','transyt_style'],default='ugat_frap_transyt');p.add_argument('--test_steps',type=int,default=7500);p.add_argument('--thread_num',type=int,default=4);a=p.parse_args()
    cmd=[sys.executable,str(ROOT/'src'/'run_cityflow.py'),'--period',a.period,'--algorithm',a.algorithm,'--steps',str(a.test_steps),'--threads',str(a.thread_num)]
    raise SystemExit(subprocess.call(cmd,cwd=ROOT))
if __name__=='__main__':main()
