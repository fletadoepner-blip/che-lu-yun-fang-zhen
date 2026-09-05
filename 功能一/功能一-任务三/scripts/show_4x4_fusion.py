import torch
s=torch.load('/workspace/final/logs/4x4_farp_adapter.pt',map_location='cpu',weights_only=True)
print('fusion_raw=',float(s['fusion']))
print('fusion_sigmoid=',float(torch.sigmoid(s['fusion'])))
