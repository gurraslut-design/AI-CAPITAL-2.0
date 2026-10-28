#!/usr/bin/env python3
"""Long-history BTC allocation research from Kraken daily OHLCVT; research only."""
import csv, json, math, sys
from datetime import datetime, timezone

def load_daily(path):
    out=[]
    with open(path,newline="",encoding="utf-8-sig") as f:
        for row in csv.reader(f):
            if len(row)<5: continue
            try:
                t=int(float(row[0])); close=float(row[4])
                if t>10_000_000_000: t//=1000
                if t>0 and close>0: out.append({"time":t,"close":close})
            except (ValueError,TypeError): continue
    out.sort(key=lambda x:x["time"])
    dedup={x["time"]:x for x in out}
    out=[dedup[t] for t in sorted(dedup)]
    if len(out)<1000: raise SystemExit(f"Not enough daily history: {len(out)}")
    return out

def signal(b,kind,ma,mom,th):
    c=[x["close"] for x in b]; s=[0]*len(b)
    for i in range(max(ma,mom)+1,len(b)):
        trend=c[i]>sum(c[i-ma:i])/ma
        momentum=c[i]/c[i-mom]-1
        if kind=="trend": s[i]=int(trend)
        elif kind=="momentum": s[i]=int(momentum>th)
        elif kind=="combined": s[i]=int(trend and momentum>th)
        else: s[i]=int(trend and momentum>-th)
    return s

def sim(b,s,start,end,fee,slip,hold=False):
    equity=1000.0; pos=0; peak=equity; dd=0.; changes=0; daily=[]
    for i in range(max(1,start),min(end,len(b))):
        target=1 if hold else s[i-1]
        if target!=pos:
            equity*=max(0,1-fee-slip); pos=target; changes+=1
        old=equity
        if pos: equity*=b[i]["close"]/b[i-1]["close"]
        daily.append(equity/old-1 if old else 0)
        peak=max(peak,equity); dd=max(dd,(peak-equity)/peak if peak else 0)
    mean=sum(daily)/len(daily) if daily else 0
    var=sum((x-mean)**2 for x in daily)/len(daily) if daily else 0
    return {"return_pct":round((equity/1000-1)*100,2),"final_balance":round(equity,2),
            "position_changes":changes,"max_drawdown_pct":round(dd*100,2),
            "sharpe_est":round(mean/math.sqrt(var)*math.sqrt(365),3) if var else 0}

def main():
    path=sys.argv[1] if len(sys.argv)>1 else "kraken_btc_daily.csv"
    b=load_daily(path); n=len(b); a=int(n*.6); z=int(n*.8); candidates=[]
    for kind in ("trend","momentum","combined","defensive"):
        for ma in (20,50,100,150,200):
            for mom in (20,40,60,90,180):
                for th in (0,.03,.06,.10):
                    s=signal(b,kind,ma,mom,th)
                    train=sim(b,s,1,a,.008,.001)
                    candidates.append({"kind":kind,"ma_days":ma,"momentum_days":mom,
                        "threshold_pct":th*100,"train":train,"signal":s})
    best=max(candidates,key=lambda x:(x["train"]["sharpe_est"],x["train"]["return_pct"]))
    reports=[]
    for fee in (.008,.004,.002,.001):
        val=sim(b,best["signal"],a,z,fee,.001)
        test=sim(b,best["signal"],z,n,fee,.001)
        bv=sim(b,[],a,z,fee,.001,True); bt=sim(b,[],z,n,fee,.001,True)
        reports.append({"fee_per_side_pct":fee*100,"validation":val,"final_test":test,
            "buy_hold_validation":bv,"buy_hold_final_test":bt,
            "beats_buy_hold_both":val["return_pct"]>bv["return_pct"] and test["return_pct"]>bt["return_pct"]})
    passed=all(x["validation"]["return_pct"]>0 and x["final_test"]["return_pct"]>0 and x["beats_buy_hold_both"] for x in reports)
    print(json.dumps({"pair":"XBT/USD","start_utc":datetime.fromtimestamp(b[0]["time"],timezone.utc).isoformat(),
        "end_utc":datetime.fromtimestamp(b[-1]["time"],timezone.utc).isoformat(),"daily_candles":n,
        "split":{"train":a,"validation":z-a,"final_test":n-z},
        "candidate_count":len(candidates),"selected_on_training_only":{k:v for k,v in best.items() if k!="signal"},
        "results":reports,"promotion_passed":passed,
        "note":"Long-history paper research only; next-day signal execution, fees plus 0.1% adverse slippage per side. No live orders."},indent=2))
if __name__=="__main__": main()
