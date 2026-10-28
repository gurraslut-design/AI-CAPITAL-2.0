#!/usr/bin/env python3
"""Regime-aware BTC strategy research. Offline only; never places orders."""
import csv, json, math, sys
from datetime import datetime, timezone


def load(path):
    raw = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            try:
                t = int(float(r["time"]))
                if t > 10_000_000_000: t //= 1000
                o,h,l,c = (float(r[k]) for k in ("open","high","low","close"))
                v = float(r.get("volume",0) or 0)
                if t > 0 and min(o,h,l,c) > 0 and v >= 0:
                    raw.append({"time":t,"open":o,"high":h,"low":l,"close":c,"volume":v})
            except (ValueError, KeyError, TypeError): pass
    raw = sorted({r["time"]:r for r in raw}.values(), key=lambda r:r["time"])
    if len(raw) < 20000 or (raw[-1]["time"]-raw[0]["time"])/86400 < 90:
        raise SystemExit("Refusing research: need at least 20,000 5m candles spanning 90+ days.")
    return raw


def aggregate(rows, seconds):
    buckets={}
    for r in rows: buckets.setdefault(r["time"]//seconds, []).append(r)
    out=[]
    for b, chunk in sorted(buckets.items()):
        chunk.sort(key=lambda r:r["time"]); expected=seconds//300
        if len(chunk)==expected and all(chunk[i+1]["time"]-chunk[i]["time"]==300 for i in range(expected-1)):
            out.append({"time":b*seconds,"open":chunk[0]["open"],"high":max(x["high"] for x in chunk),
                        "low":min(x["low"] for x in chunk),"close":chunk[-1]["close"],
                        "volume":sum(x["volume"] for x in chunk)})
    return out


def signals(rows, kind, fast, slow, extra):
    c=[r["close"] for r in rows]; out=[0]*len(rows)
    for i in range(slow, len(rows)):
        ma_fast=sum(c[i-fast+1:i+1])/fast
        ma_slow=sum(c[i-slow+1:i+1])/slow
        if kind=="ma": out[i]=int(ma_fast>ma_slow)
        elif kind=="breakout": out[i]=int(c[i]>max(c[i-slow:i]) and ma_fast>ma_slow)
        elif kind=="pullback":
            recent_low=min(c[i-fast+1:i+1])
            out[i]=int(ma_fast>ma_slow and c[i]>recent_low and c[i]>c[i-1] and c[i]<ma_fast*1.02)
        elif kind=="vol_breakout":
            prior=max(c[i-slow:i]); ret=c[i]/c[i-1]-1
            vol=[abs(c[j]/c[j-1]-1) for j in range(max(1,i-20),i)]
            vol_now=sum(vol)/len(vol) if vol else 0
            out[i]=int(c[i]>prior and ma_fast>ma_slow and ret>max(0.002,vol_now*extra))
    return out


def simulate(rows, sig, start, end, fee, slip, initial=1000.0):
    end=min(end,len(rows)); start=max(start,1)
    cash=initial; pos=0; peak=initial; maxdd=0.; trades=0; entry_equity=None; wins=0; gp=0.; gl=0.
    # Signal from the prior completed candle; execution is conservatively approximated at next candle open.
    prev_close=rows[start-1]["close"]
    for i in range(start,end):
        px=rows[i]["open"]
        target=sig[i-1]
        if target != pos:
            if pos:
                equity=cash*(px/prev_close)*(1-fee-slip)
                pnl=equity-(entry_equity or initial)
                trades+=1
                if pnl>0: wins+=1; gp+=pnl
                elif pnl<0: gl+=-pnl
                cash=equity; pos=0; entry_equity=None
            if target:
                cash*=max(1e-9,1-fee-slip)
                entry_equity=cash; pos=1
        if pos:
            cash*=max(1e-9, rows[i]["close"]/px)
        equity=cash
        peak=max(peak,equity); maxdd=max(maxdd,(peak-equity)/peak if peak else 0)
        prev_close=rows[i]["close"]
    if pos:
        cash*=max(1e-9,1-fee-slip)
        pnl=cash-(entry_equity or initial); trades+=1
        if pnl>0: wins+=1; gp+=pnl
        elif pnl<0: gl+=-pnl
    return {"return_pct":round((cash/initial-1)*100,2),"final_balance":round(cash,2),"trades":trades,
            "win_rate_pct":round(wins/trades*100,2) if trades else 0,
            "profit_factor":round(gp/gl,3) if gl else ("infinity" if gp else 0),
            "max_drawdown_pct":round(maxdd*100,2)}


def main():
    raw=load(sys.argv[1] if len(sys.argv)>1 else "kraken_multi_month.csv")
    frames={"1h":aggregate(raw,3600),"4h":aggregate(raw,14400),"1d":aggregate(raw,86400)}
    all_results=[]
    fee_cases=(0.008,0.004,0.002,0.001)
    for tf, rows in frames.items():
        if len(rows)<250: continue
        n=len(rows); a=int(n*.6); b=int(n*.8)
        candidates=[]
        for kind in ("ma","breakout","pullback","vol_breakout"):
            for fast,slow in ((5,20),(10,30),(20,50),(20,100)):
                if fast>=slow: continue
                for extra in (1.0,1.5,2.0):
                    sig=signals(rows,kind,fast,slow,extra)
                    # Select using training only, with conservative costs and slippage.
                    train=simulate(rows,sig,0,a,0.008,0.001)
                    candidates.append({"kind":kind,"fast":fast,"slow":slow,"extra":extra,
                                       "train":train,"signals":sig})
        # Avoid selecting a strategy with too few training trades or zero activity.
        eligible=[x for x in candidates if x["train"]["trades"]>=5]
        best=max(eligible or candidates,key=lambda x:x["train"]["return_pct"])
        fee_reports=[]
        for fee in fee_cases:
            val=simulate(rows,best["signals"],a,b,fee,0.001)
            test=simulate(rows,best["signals"],b,n,fee,0.001)
            fee_reports.append({"fee_per_side_pct":fee*100,"validation":val,"final_test":test})
        # Buy-and-hold benchmark with the same execution-cost assumptions.
        bh=[0]*n
        for i in range(1,n): bh[i]=1
        benchmark=[]
        for fee in fee_cases:
            benchmark.append({"fee_per_side_pct":fee*100,
                "validation":simulate(rows,bh,a,b,fee,0.001),
                "final_test":simulate(rows,bh,b,n,fee,0.001)})
        promoted=all(r["validation"]["return_pct"]>0 and r["final_test"]["return_pct"]>0
                     and r["validation"]["profit_factor"] not in (0,"infinity")
                     and r["final_test"]["profit_factor"] not in (0,"infinity")
                     and r["validation"]["profit_factor"]>1 and r["final_test"]["profit_factor"]>1
                     and r["validation"]["trades"]>=5 and r["final_test"]["trades"]>=5 for r in fee_reports)
        all_results.append({"timeframe":tf,"candles":n,"split":{"train":a,"validation":b-a,"final_test":n-b},
          "selected_on_training_only":{"kind":best["kind"],"fast":best["fast"],"slow":best["slow"],"extra":best["extra"]},
          "training":best["train"],"strategy_fee_sensitivity":fee_reports,"buy_and_hold_benchmark":benchmark,
          "promotion_passed":promoted})
    print(json.dumps({"dataset_start_utc":datetime.fromtimestamp(raw[0]["time"],timezone.utc).isoformat(),
      "dataset_end_utc":datetime.fromtimestamp(raw[-1]["time"],timezone.utc).isoformat(),"source_5m_candles":len(raw),
      "method":"1h/4h/daily regime-aware moving average, breakout, pullback and volatility breakout; chronological 60/20/20; 0.1% adverse slippage per side; benchmark against buy-and-hold.",
      "note":"Exploratory research only. Costs are stressed at 0.8%, 0.4%, 0.2%, and 0.1% per side. No live orders. Passing this test alone is not proof of future profitability.",
      "results":all_results},indent=2))


if __name__=="__main__": main()
