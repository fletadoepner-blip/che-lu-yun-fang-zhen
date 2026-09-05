import torch
from ugat_farp_4x4_model import UGATFARP4x4
m=UGATFARP4x4('/workspace/final/model/best_4x4_model_0.pt')
x=torch.randn(4,20); x[:,12:]=0; x[range(4),12+torch.tensor([0,1,2,3])]=1
y=m(x); print(tuple(y.shape), bool(torch.isfinite(y).all()), m.report())
