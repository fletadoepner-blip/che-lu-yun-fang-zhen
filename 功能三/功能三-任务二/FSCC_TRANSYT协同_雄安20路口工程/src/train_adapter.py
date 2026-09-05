"""Train only the FRAP adapter using a transparent pressure-policy teacher.

This is a lightweight warm-start, not a claim of end-to-end RL optimality.
UGAT remains frozen and CityFlow evaluation is performed separately.
"""
from __future__ import annotations
import argparse, csv, sys
from pathlib import Path
import torch
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "src"))
from ugat_frap import UGATFRAPController

PAIRS = ((1, 4), (7, 10), (0, 3), (6, 9), (0, 1), (3, 4), (9, 10), (6, 7))

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--epochs",type=int,default=20); ap.add_argument("--batch-size",type=int,default=512); ap.add_argument("--seed",type=int,default=20260816); a=ap.parse_args()
    torch.manual_seed(a.seed); checkpoint=ROOT/"model"/"frozen_ugat_4x4.pt"; state_path=ROOT/"model"/"frap_adapter.pt"
    model=UGATFRAPController(checkpoint); model.assert_frozen(); opt=torch.optim.Adam(model.adapter_parameters(),lr=1e-3); log=[]
    for epoch in range(1,a.epochs+1):
        lanes=torch.poisson(torch.full((a.batch_size,12),4.0)); phase=F.one_hot(torch.randint(0,8,(a.batch_size,)),8).float(); state=torch.cat((lanes,phase),1)
        target=torch.stack([lanes[:,list(p)].sum(1) for p in PAIRS],1).argmax(1); loss=F.cross_entropy(model(state),target); opt.zero_grad();loss.backward();opt.step()
        row={"epoch":epoch,"cross_entropy":round(float(loss),6),"frap_weight":round(float(torch.sigmoid(model.fusion)),6)}; log.append(row); print(row)
    torch.save({"frap":model.frap.state_dict(),"fusion":model.fusion.detach().cpu(),"epochs":a.epochs,"teacher":"synthetic max-pressure warm-start"},state_path)
    with (ROOT/"outputs"/"adapter_training.csv").open("w",newline="",encoding="utf-8") as f: w=csv.DictWriter(f,fieldnames=log[0]);w.writeheader();w.writerows(log)
if __name__=="__main__":main()
