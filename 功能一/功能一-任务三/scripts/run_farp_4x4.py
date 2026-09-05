import argparse, os, sys, csv, json, threading, shutil
from pathlib import Path
from datetime import datetime
sys.path.insert(0,'/DaRL/UGAT_Docker'); sys.path.insert(0,'/workspace/final')
import task, trainer, dataset, agent, torch
from agent.dqn import DQNAgent as BaseDQN
from common.registry import Registry
from ugat_farp_4x4_model import UGATFARP4x4
import trainer.tsc_trainer as tsc

def safe_log(traj,lanes,fix_time=30):
    from copy import deepcopy
    from collections import defaultdict
    max_i=max((int((r[0][1]+r[0][2]-1)//fix_time) for r in traj.values() if r),default=119)
    rec={i:defaultdict(int,{l:0 for l in lanes}) for i in range(max(120,max_i+1))}
    for r in traj.values():
        if r:
            i=int((r[0][1]+r[0][2]-1)//fix_time); rec[i].setdefault(r[0][0],0); rec[i][r[0][0]]+=1
    return rec
tsc.log_passing_lane_actinon=safe_log
orig_test=tsc.TSCTrainer.test
def test_with_artifacts(self,drop_load=True):
    done=threading.Event()
    def heartbeat():
        elapsed=0
        while not done.wait(30):
            elapsed+=30
            try: sim_time=self.world.eng.get_current_time()
            except Exception: sim_time='unavailable'
            print(f'progress_heartbeat: wall_seconds={elapsed}, simulator_time={sim_time}',flush=True)
    threading.Thread(target=heartbeat,daemon=True).start()
    try: result=orig_test(self,drop_load=drop_load)
    finally: done.set()
    m=self.metric
    row={'timestamp':datetime.now().isoformat(timespec='seconds'),'max_frap_weight':float(self.agents[0].model.max_frap_weight),'travel_time':float(m.real_average_travel_time()),'throughput':float(m.throughput()),'queue':float(m.queue()),'delay_ratio_apx':float(m.delay()),'rewards':float(m.rewards())}
    out=Path('/workspace/final/logs'); out.mkdir(parents=True,exist_ok=True); path=out/'4x4_simulation_metrics.csv'; exists=path.exists()
    with path.open('a',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(row));
        if not exists:w.writeheader()
        w.writerow(row)
    (out/'4x4_latest_metrics.json').write_text(json.dumps(row,indent=2),encoding='utf-8')
    try:
        import matplotlib.pyplot as plt
        rows=list(csv.DictReader(path.open(encoding='utf-8'))); x=list(range(1,len(rows)+1)); fig,ax=plt.subplots(2,2,figsize=(10,7))
        for a,k,l in zip(ax.flat,['travel_time','throughput','queue','delay_ratio_apx'],['Travel Time (s)','Throughput','Queue','Approx. delay ratio']): a.plot(x,[float(r[k]) for r in rows],marker='o'); a.set_xlabel('run'); a.set_ylabel(l); a.grid(alpha=.3)
        fig.tight_layout(); fig.savefig(out/'4x4_simulation_metrics.png',dpi=160); plt.close(fig)
    except Exception as e: print('plot_warning='+str(e))
    return result
tsc.TSCTrainer.test=test_with_artifacts

@Registry.register_model('farp4x4')
class FARP4x4Agent(BaseDQN):
    def __init__(self,world,rank):
        super().__init__(world,rank); self.model=UGATFARP4x4('/workspace/final/model/best_4x4_model_0.pt', max_frap_weight=Registry.mapping['model_mapping']['setting'].param.get('max_frap_weight', 1.00)); self.target_model=self.model
        state='/workspace/final/logs/4x4_farp_adapter.pt'
        if os.path.exists(state):
            s=torch.load(state,map_location='cpu',weights_only=True); self.model.frap.load_state_dict(s['frap']); self.model.fusion.data.copy_(s['fusion']); print('loaded_4x4_adapter='+state)
    def load_model(self,e,customized_path=''): print('skip_legacy_4x4_dqn_load=true')

def main():
    a=argparse.ArgumentParser(); a.add_argument('--thread_num',type=int,default=4); a.add_argument('--seed',type=int,default=4444); a.add_argument('--prefix',default='4x4_farp_eval'); a.add_argument('--test_steps',type=int,default=3600); a.add_argument('--delay_type',default='apx',choices=['apx','real']); a.add_argument('--max_frap_weight',type=float,default=1.00); a=a.parse_args()
    # The official config loader only searches /DaRL/UGAT_Docker/configs.
    shutil.copyfile('/workspace/final/configs/farp4x4.yml', '/DaRL/UGAT_Docker/configs/tsc/farp4x4.yml')
    old=sys.argv; sys.argv=['run_farp_4x4.py','-t','tsc','-a','farp4x4','-w','cityflow','-n','cityflow4x4','-d','onfly','--thread_num',str(a.thread_num),'--seed',str(a.seed),'--prefix',a.prefix,'--interface','libsumo','--delay_type',a.delay_type]
    try:
        from run import Runner
        ns=argparse.Namespace(thread_num=a.thread_num,ngpu='-1',prefix=a.prefix,seed=a.seed,debug=False,interface='libsumo',delay_type=a.delay_type,task='tsc',agent='farp4x4',world='cityflow',network='cityflow4x4',dataset='onfly')
        runner=Runner(ns)
        Registry.mapping['model_mapping']['setting'].param['max_frap_weight']=a.max_frap_weight
        Registry.mapping['trainer_mapping']['setting'].param['test_steps']=a.test_steps
        runner.run()
    finally: sys.argv=old
if __name__=='__main__': main()
