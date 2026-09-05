"""4x4-compatible FRAP adapter training wrapper."""
from pathlib import Path
import argparse, subprocess, sys
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('--epochs',type=int,default=20);a=p.parse_args();raise SystemExit(subprocess.call([sys.executable,str(ROOT/'src'/'train_adapter.py'),'--epochs',str(a.epochs)],cwd=ROOT))
if __name__=='__main__':main()
