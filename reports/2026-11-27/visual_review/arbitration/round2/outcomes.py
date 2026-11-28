"""نتائج وصفية بعد الكشف. التعريفات ثُبّتت قبل التشغيل:
- الأمر: شراء عند نقطة الدخول التي كتبها كل طرف. التنفيذ = max(الافتتاح، نقطة الدخول) إذا بلغ أعلى السعر نقطة الدخول.
- الصلاحية: A = الجلسة التالية فقط (S13 51:46 "صلاحية يوم واحد")، B = حتى 10 جلسات (وصفي).
- بعد التنفيذ: الوقف كما كتبه الطرف، ولا يُحرّك. التنفيذ = min(الافتتاح، الوقف) إذا بلغ أدنى السعر الوقف. يوم التنفيذ نفسه: إذا لمس الدخول والوقف معاً، تُحتسب خسارة.
- الأفق: 60 جلسة أو حتى آخر البيانات. يُسجَّل: هل ضُرب الوقف، وأقصى ربح بالـR قبل الوقف أو نهاية الأفق، والـR في النهاية.
- لكل حالة أيضاً، بلا أي حكم: أقصى صعود وأقصى هبوط خلال 60 جلسة من إغلاق يوم القرار."""
import json, csv, pandas as pd, os
R="/home/claude/verify/bt"; M=json.load(open("round2_map_SEALED.json"))["map"]
C={r[0]:r for r in list(csv.reader(open("sealed/claude_round2_rulings_30.csv")))[1:]}
G={r[0]:r for r in list(csv.reader(open("/mnt/user-data/uploads/f294ffae-chatgpt_round2_blind_rulings_30.csv")))[1:]}
def num(x):
    try: return float(x)
    except: return None
def sim(d,i,e,s,valid):
    if e is None or s is None or s>=e: return None
    fut=d.iloc[i+1:i+61]
    for k in range(min(valid,len(fut))):
        r=fut.iloc[k]
        if r.high>=e:
            fill=max(r.open,e); risk=fill-s
            if r.low<=s: return dict(fill=round(fill,4),stopped=True,day=k+1,maxR=0.0,endR=round((s-fill)/risk,2))
            mx=r.high; 
            for j in range(k+1,len(fut)):
                q=fut.iloc[j]
                if q.low<=s:
                    ex=min(q.open,s); return dict(fill=round(fill,4),stopped=True,day=j+1,maxR=round((mx-fill)/risk,2),endR=round((ex-fill)/risk,2))
                mx=max(mx,q.high)
            return dict(fill=round(fill,4),stopped=False,day=None,maxR=round((mx-fill)/risk,2),endR=round((fut.close.iloc[-1]-fill)/risk,2),bars=len(fut))
    return dict(fill=None)
rows=[]
for cid in sorted(M):
    m=M[cid]; H=os.path.join(R,"hist" if m["market"]=="SA" else "hist_us")
    d=pd.read_csv(os.path.join(H,m["sym"]+".csv"),index_col=0,parse_dates=True); d=d[~d.index.duplicated()]
    i=d.index.get_loc(pd.Timestamp(m["decision_day"])); c0=d.close.iloc[i]; fut=d.iloc[i+1:i+61]
    row=dict(cid=cid,market=m["market"],stratum=m["stratum"],sym=m["sym"],day=m["decision_day"],close=round(c0,4),bars=len(fut),
             up60=round((fut.high.max()/c0-1)*100,1),dn60=round((fut.low.min()/c0-1)*100,1),C=C[cid][1],G=G[cid][1])
    for who,X in (("C",C),("G",G)):
        if X[cid][1]=="دخول":
            for v,n in (("A",1),("B",10)):
                row[f"{who}{v}"]=sim(d,i,num(X[cid][2]),num(X[cid][3]),n)
    rows.append(row)
json.dump(rows,open("outcomes_round2.json","w"),ensure_ascii=False,indent=1,default=str)
for r in rows:
    print(r["cid"],r["market"],r["stratum"],r["sym"],r["day"],r["C"],"|",r["G"],f"up {r['up60']} dn {r['dn60']} bars {r['bars']}",
          {k:v for k,v in r.items() if k in("CA","CB","GA","GB")})
