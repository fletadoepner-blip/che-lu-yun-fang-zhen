import csv
from pathlib import Path
import matplotlib.pyplot as plt
logs=Path('/workspace/final/logs') if Path('/workspace/final/logs').exists() else Path(r'C:\Users\lauri\Desktop\4x4ugat+frap\logs')
rows=list(csv.DictReader((logs/'4x4_training_metrics.csv').open(encoding='utf-8')))
fig,ax=plt.subplots(1,2,figsize=(10,4))
ax[0].plot([r['epoch'] for r in rows],[r['raw_mse'] for r in rows],marker='o',label='raw MSE')
ax[0].set_xlabel('epoch'); ax[0].set_ylabel('raw MSE'); ax[0].grid(alpha=.3); ax[0].legend()
ax[1].plot([r['epoch'] for r in rows],[r['log10_raw_mse'] for r in rows],marker='o',color='tab:orange',label='log10(raw MSE)')
ax[1].set_xlabel('epoch'); ax[1].set_ylabel('log10(raw MSE)'); ax[1].grid(alpha=.3); ax[1].legend()
fig.suptitle('4x4 UGAT + FRAP adapter training diagnostics'); fig.tight_layout(); fig.savefig(logs/'4x4_training_loss.png',dpi=160)
