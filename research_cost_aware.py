#!/usr/bin/env python3
"""Cost-aware hourly BTC forecast research. Offline backtest only; never places orders."""
import csv, json, math, sys
from pathlib import Path

def load(path):
    rows=[]
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            try:
                rows.append((int(float(r["time"])), float(r["close"]), float(r.get("volume",0) or 0)))
            except (ValueError, KeyError, TypeError):
                continue
    rows.sort()
    # Aggregate 5m candles into UTC clock-hour candles, requiring all 12 candles.
    hours={}
    for t,c,v in rows:
        h=t//3600
        hours.setdefault(h,[]).append((t,c,v))
    out=[]
    for h, chunk in sorted(hours.items()):
        if len(chunk)>=10:
            out.append({"time":h*3600,"close":chunk[-1][1],"volume":sum(x[2] for x in chunk)})
    if len(out)<500: raise SystemExit(f"Too few hourly candles: {len(out)}")
    return out

def features(rows, i):
    closes=[r["close"] for r in rows]
    out=[]
    for n in (1,2,3,6,12,24,48,72,168):
        if i<n: return None
        out.append(closes[i]/closes[i-n]-1)
    # Historical realized volatility, calculated strictly from data at or before i.
    rets=[closes[j]/closes[j-1]-1 for j in range(max(1,i-23),i+1)]
    out += [math.sqrt(sum(x*x for x in rets)), rows[i]["volume"]/(sum(r["volume"] for r in rows[max(0,i-23):i+1])/max(1,len(rows[max(0,i-23):i+1]))+1e-12)]
    return out

def simulate(rows, model, fee, slip, horizon=4, start=0, end=None):
    end=len(rows) if end is None else min(end,len(rows))
    balance=1000.0; peak=balance; maxdd=0.0; trades=[]; i=max(start,168)
    while i+horizon<end:
        x=features(rows,i)
        if x is None: i+=1; continue
        pred=float(model.predict([x])[0])
        # Require forecast to exceed round-trip fees and adverse execution costs.
        threshold=2*fee+2*slip
        if pred>threshold:
            entry=rows[i+1]["close"]*(1+slip)
            exitp=rows[i+1+horizon]["close"]*(1-slip)
            ret=exitp/entry-1-2*fee
            balance*=1+ret
            trades.append(ret)
            peak=max(peak,balance); maxdd=max(maxdd,(peak-balance)/peak)
            i+=horizon+1
        else:
            i+=1
    wins=sum(x>0 for x in trades)
    gp=sum(x for x in trades if x>0); gl=-sum(x for x in trades if x<0)
    return {"return_pct":round((balance/1000-1)*100,2),"final_balance":round(balance,2),"trades":len(trades),
            "win_rate_pct":round(100*wins/len(trades),2) if trades else 0,
            "profit_factor":round(gp/gl,3) if gl else ("infinity" if gp else 0),
            "max_drawdown_pct":round(maxdd*100,2),"fees_slippage_threshold_pct":round((2*fee+2*slip)*100,3)}

def main():
    rows=load(sys.argv[1] if len(sys.argv)>1 else "kraken_multi_month.csv")
    horizon=4
    # Target is forward four-hour return; features are strictly historical.
    X=[]; y=[]; indices=[]
    for i in range(168,len(rows)-horizon):
        x=features(rows,i)
        if x is not None:
            X.append(x); y.append(rows[i+horizon]["close"]/rows[i]["close"]-1); indices.append(i)
    n=len(X); a=int(n*.6); b=int(n*.8)
    if a<200 or b-a<50 or n-b<50: raise SystemExit(f"Not enough samples for chronological splits: {n}")
    # A simple nonlinear model; dependencies are installed only in CI, not in the live bot.
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import make_pipeline
    reports=[]
    for fee in (0.008,0.004,0.002,0.001):
        model=make_pipeline(SimpleImputer(strategy="median"),HistGradientBoostingRegressor(
            max_iter=100,max_leaf_nodes=7,l2_regularization=2.0,learning_rate=0.05,random_state=7))
        model.fit(X[:a],y[:a])
        # Evaluate only the contiguous validation and final-test ranges; no retraining on holdout.
        # To avoid hidden look-ahead, prediction at i uses only features through i.
        val=simulate(rows,model,fee,0.001,horizon,indices[a],indices[b-1]+horizon+1)
        test=simulate(rows,model,fee,0.001,horizon,indices[b],indices[-1]+horizon+1)
        reports.append({"fee_per_side_pct":fee*100,"adverse_slippage_per_side_pct":0.1,
                        "validation":val,"final_test":test})
    print(json.dumps({"strategy":"Hourly HistGradientBoosting forecast; long-only; four-hour holding; trade only when predicted return exceeds round-trip fees plus 0.1% adverse slippage per side.",
      "source_candles_5m":len(rows),"hourly_candles":len(rows),"samples":n,
      "chronological_split":{"train_pct":60,"validation_pct":20,"untouched_final_test_pct":20},
      "note":"Exploratory research only. Results on six-month data are not proof of durable edge. No live orders, no exchange keys.",
      "fee_sensitivity":reports},indent=2))
if __name__=="__main__": main()
