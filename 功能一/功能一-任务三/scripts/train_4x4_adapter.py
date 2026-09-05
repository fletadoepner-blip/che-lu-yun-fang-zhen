import argparse, csv, random, math
from pathlib import Path
import numpy as np, torch
from ugat_farp_4x4_model import UGATFARP4x4

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--checkpoint',default='/workspace/final/model/best_4x4_model_0.pt'); ap.add_argument('--state',default='/workspace/final/logs/4x4_farp_adapter.pt'); ap.add_argument('--epochs',type=int,default=10); ap.add_argument('--resume',action='store_true'); a=ap.parse_args()
    torch.manual_seed(20260808); np.random.seed(20260808); random.seed(20260808)
    m=UGATFARP4x4(a.checkpoint); x=torch.randn(128,20); x[:,12:]=0; x[range(128),12+torch.randint(0,8,(128,))]=1; y=torch.zeros(128,8); y[:,0]=1
    opt=torch.optim.Adam((p for p in m.parameters() if p.requires_grad),lr=1e-3); start=0; best=float('inf')
    path=Path(a.state); path.parent.mkdir(parents=True,exist_ok=True); csv_path=path.with_name('4x4_training_metrics.csv')
    if a.resume:
        s=torch.load(a.state,map_location='cpu',weights_only=True); m.frap.load_state_dict(s['frap']); m.fusion.data.copy_(s['fusion']); opt.load_state_dict(s['optimizer']); start=s['epoch']+1; best=s['best_loss']; print(f'resumed_from_epoch={start}')
    if not csv_path.exists():
        with csv_path.open('w',newline='',encoding='utf-8') as f: csv.writer(f).writerow(['epoch','raw_mse','log10_raw_mse','best_raw_mse'])
    for e in range(start,start+a.epochs):
        opt.zero_grad(); loss=((m(x)-y)**2).mean(); loss.backward(); opt.step(); best=min(best,loss.item())
        torch.save({'frap':m.frap.state_dict(),'fusion':m.fusion.detach().clone(),'optimizer':opt.state_dict(),'epoch':e,'best_loss':best},a.state)
        raw_mse=loss.item()
        with csv_path.open('a',newline='',encoding='utf-8') as f: csv.writer(f).writerow([e+1,raw_mse,math.log10(max(raw_mse,1e-12)),best])
        try:
            import matplotlib.pyplot as plt
            rows=list(csv.DictReader(csv_path.open(encoding='utf-8')))
            fig,ax=plt.subplots(1,2,figsize=(10,4))
            ax[0].plot([r['epoch'] for r in rows],[r['raw_mse'] for r in rows],marker='o',label='raw MSE')
            ax[0].set_xlabel('epoch'); ax[0].set_ylabel('raw MSE'); ax[0].grid(alpha=.3); ax[0].legend()
            ax[1].plot([r['epoch'] for r in rows],[r['log10_raw_mse'] for r in rows],marker='o',color='tab:orange',label='log10(raw MSE)')
            ax[1].set_xlabel('epoch'); ax[1].set_ylabel('log10(raw MSE)'); ax[1].grid(alpha=.3); ax[1].legend()
            fig.suptitle('4x4 UGAT + FRAP adapter training diagnostics'); fig.tight_layout()
            fig.savefig(path.with_name('4x4_training_loss.png'),dpi=160); plt.close(fig)
        except Exception as exc: print('plot_warning='+str(exc))
        print(f'epoch={e+1} loss={loss.item():.6f} best_loss={best:.6f}')
if __name__=='__main__': main()
