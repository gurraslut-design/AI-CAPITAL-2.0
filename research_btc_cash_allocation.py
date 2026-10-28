#!/usr/bin/env python3
"""Daily BTC-or-cash allocation research; paper-only."""
import csv,json,math,sys
from datetime import datetime,timezone

def load(path):
 d={}
 with open(path,newline="",encoding="utf-8-sig") as f:
  for r in csv.DictReader(f):
   try:
    t=int(float(r["time"])); o=float(r["open"]); c=float(r["close"])
    if t>0 and o>0 and c>0:d[t]={"time":t,"open":o,"close":c}
   except (ValueError,KeyError,TypeError):pass
 a=[d[t] for t in sorted(d)]
 if len(a)<20000 or (a[-1]["time"]-a[0]["time"])/86400<90:raise SystemExit("Insufficient historical data")
 return a

def daily(rows):
 g={}
 for r in rows:g.setdefault(r["time"]//86400,[]).append(r)
 out=[]
 for day,x in sorted(g.items()):
  x.sort(key=lambda z:z["time"])
  if len(x)==288 and all(x[i+1]["time"]-x[i]["time"]==300 for i in range(287)):
   out.append({"time":day*86400,"close":x[-1]["close"]})
 return out

def signal(b,kind,ma,mom,th):
 c=[x["close"] for x in b]; s=[0]*len(b)
 for i in range(max(ma,mom)+1,len(b)):
  trend=c[i]>sum(c[i-ma:i])/ma; ret=c[i]/c[i-mom]-1
  if kind=="trend":s[i]=int(trend)
  elif kind=="momentum":s[i]=int(ret>th)
  elif kind=="combined":s[i]=int(trend and ret>th)
  else:s[i]=int(trend and ret>-th)
 return s

def sim(b,s,start,end,fee,slip,hold=False):
 e=1000.; p=0; peak=e; dd=0.; changes=0; rets=[]
 for i in range(max(1,start),min(end,len(b))):
  target=1 if hold else s[i-1]
  if target!=p:e*=1-fee-slip;p=target;changes+=1
  old=e
  if p:e*=b[i]["close"]/b[i-1]["close"]
  rets.append(e/old-1 if old else 0)
  peak=max(peak,e);dd=max(dd,(peak-e)/peak if peak else 0)
 m=sum(rets)/len(rets) if rets else 0
 v=sum((x-m)**2 for x in rets)/len(rets) if rets else 0
 return {"return_pct":round((e/1000-1)*100,2),"final_balance":round(e,2),"changes":changes,"max_drawdown_pct":round(dd*100,2),"sharpe_est":round(m/math.sqrt(v)*math.sqrt(365),3) if v else 0}

def main():
 raw=load(sys.argv[1] if len(sys.argv)>1 else "kraken_multi_month.csv"); b=daily(raw)
 if len(b)<100:raise SystemExit("Too few complete daily bars")
 n=len(b); a=int(n*.6); z=int(n*.8); candidates=[]
 for kind in ("trend","momentum","combined","defensive"):
  for ma in (20,50,100,150):
   for mom in (20,40,60,90):
    for th in (0,.03,.06,.10):
     s=signal(b,kind,ma,mom,th); r=sim(b,s,1,a,.008,.001)
     candidates.append({"kind":kind,"ma":ma,"momentum":mom,"threshold_pct":th*100,"train":r,"signal":s})
 best=max(candidates,key=lambda x:(x["train"]["sharpe_est"],x["train"]["return_pct"]))
 reports=[]
 for fee in (.008,.004,.002,.001):
  val=sim(b,best["signal"],a,z,fee,.001); test=sim(b,best["signal"],z,n,fee,.001)
  bv=sim(b,[],a,z,fee,.001,True); bt=sim(b,[],z,n,fee,.001,True)
  reports.append({"fee_per_side_pct":fee*100,"validation":val,"final_test":test,"buy_hold_validation":bv,"buy_hold_final_test":bt})
 passed=all(x["validation"]["return_pct"]>0 and x["final_test"]["return_pct"]>0 and x["validation"]["return_pct"]>x["buy_hold_validation"]["return_pct"] and x["final_test"]["return_pct"]>x["buy_hold_final_test"]["return_pct"] for x in reports)
 print(json.dumps({"start_utc":datetime.fromtimestamp(b[0]["time"],timezone.utc).isoformat(),"end_utc":datetime.fromtimestamp(b[-1]["time"],timezone.utc).isoformat(),"source_5m_candles":len(raw),"daily_bars":n,"split":{"train":a,"validation":z-a,"final_test":n-z},"selected_on_training_only":{k:v for k,v in best.items() if k!="signal"},"results":reports,"promotion_passed":passed,"note":"Research only, fees and 0.1% slippage per side, no live trading."},indent=2))
if __name__=="__main__":main()
