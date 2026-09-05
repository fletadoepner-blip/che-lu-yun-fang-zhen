"""Frozen 4x4 UGAT/DQN base plus a trainable FRAP action adapter."""
import torch
from torch import nn
import torch.nn.functional as F

PHASE_PAIRS = [(4,10),(1,7),(5,11),(2,8),(10,11),(4,5),(7,8),(1,2)]

class FrozenUGAT4x4(nn.Module):
    def __init__(self, checkpoint):
        super().__init__()
        self.dense_1=nn.Linear(20,20); self.dense_2=nn.Linear(20,20); self.dense_3=nn.Linear(20,8)
        state=torch.load(checkpoint,map_location='cpu',weights_only=True)
        if set(state)!=set(self.state_dict()): raise RuntimeError('4x4 checkpoint keys mismatch')
        self.load_state_dict(state)
        for p in self.parameters(): p.requires_grad=False
    def forward(self,x,train=True):
        with torch.no_grad(): return self.dense_3(F.relu(self.dense_2(F.relu(self.dense_1(x)))))

class FRAP4x4(nn.Module):
    def __init__(self):
        super().__init__(); self.oshape=8; self.num_movements=12
        self.comp_mask=self._relation_mask()
        self.p=nn.Embedding(2,4); self.d=nn.Linear(1,4)
        self.lane_embedding=nn.Linear(8,16); self.lane_conv=nn.Conv2d(32,20,1)
        self.relation_embedding=nn.Embedding(2,4); self.relation_conv=nn.Conv2d(4,20,1)
        self.hidden_layer=nn.Conv2d(20,20,1); self.before_merge=nn.Conv2d(20,1,1)
    def _relation_mask(self):
        rows=[]
        for i,a in enumerate(PHASE_PAIRS):
            rows.append([1 if len(set(a+PHASE_PAIRS[j]))==3 else 0 for j in range(8) if i!=j])
        return torch.tensor(rows,dtype=torch.long)
    def forward(self, x):
        if x.ndim!=2 or x.shape[1]!=20: raise ValueError('FRAP4x4 input must be [batch,20]')
        phase=x[:,:8].float(); lanes=x[:,8:].float().reshape(-1,12,1)
        movement_phase=torch.zeros(x.size(0),12,dtype=torch.long,device=x.device)
        for i,(a,b) in enumerate(PHASE_PAIRS):
            active=(phase[:,i] > 0.5).long(); movement_phase[:,a]=torch.maximum(movement_phase[:,a],active); movement_phase[:,b]=torch.maximum(movement_phase[:,b],active)
        phase_emb=torch.sigmoid(self.p(movement_phase)); demand=torch.sigmoid(self.d(lanes))
        lane=F.relu(self.lane_embedding(torch.cat([phase_emb,demand],-1)))
        pairs=torch.stack([lane[:,a]+lane[:,b] for a,b in PHASE_PAIRS],1)
        rotated=torch.stack([torch.cat([pairs[:,i],pairs[:,j]],-1) for i in range(8) for j in range(8) if i!=j],1)
        rotated=rotated.reshape(-1,8,7,32).permute(0,3,1,2)
        rotated=F.relu(self.lane_conv(rotated))
        rel=F.relu(self.relation_conv(self.relation_embedding(self.comp_mask).permute(2,0,1).unsqueeze(0).expand(x.size(0),-1,-1,-1)))
        out=F.relu(self.hidden_layer(rotated)*rel); out=self.before_merge(out).reshape(-1,8,7).sum(2)
        return out

class UGATFARP4x4(nn.Module):
    def __init__(self, checkpoint, max_frap_weight=1.00):
        super().__init__(); self.ugat=FrozenUGAT4x4(checkpoint); self.frap=FRAP4x4(); self.fusion=nn.Parameter(torch.tensor(0.0)); self.max_frap_weight=float(max_frap_weight)
    def forward(self,x,train=True):
        # CityFlow DQN order is [12 lane counts, 8 phase one-hot]. FRAP uses the reverse order.
        frap_input=torch.cat([x[:,12:20],x[:,:12]],1)
        with torch.no_grad(): base=self.ugat(x)
        return base+(self.max_frap_weight*torch.sigmoid(self.fusion))*self.frap(frap_input)
    def report(self):
        return sum(p.numel() for p in self.frap.parameters())+1, sum(p.numel() for p in self.ugat.parameters())
