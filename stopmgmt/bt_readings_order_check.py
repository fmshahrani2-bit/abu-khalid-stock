import sys, random, numpy as np
sys.argv=["x","us"]
src=open("bt_readings.py").read().split("out = {\"market\"")[0]
exec(src)
res={}
for v in ("R0","A"):
    minc,pm,sm=VARS[v]; sigs=signals_for(minc,pm,sm)
    nets=[];pfs=[]
    for k in range(300):
        rng=random.Random(k); s2=sorted(sigs,key=lambda x:(x["day"],rng.random()))
        st=stats(portfolio(s2)); nets.append(st["net"]); pfs.append(st["pf"] or 0)
    base=stats(portfolio(sigs))
    res[v]=nets
    print(v,"alphabetical net",base["net"],"| random same-day order: median",int(np.median(nets)),"P5",int(np.percentile(nets,5)),"P95",int(np.percentile(nets,95)),"share>0",round(np.mean(np.array(nets)>0),2),"medPF",round(float(np.median(pfs)),2))
d=np.array(res["A"])-np.array(res["R0"]); print("A-R0 paired by seed: median",int(np.median(d)),"share A>R0",round(np.mean(d>0),2))
