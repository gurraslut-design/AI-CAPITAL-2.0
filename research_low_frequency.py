#!/usr/bin/env python3
"""Low-frequency BTC technical-rule research. Research only; never places orders."""
import csv, json, sys
from datetime import datetime, timezone


def load_5m(path):
    rows=[]
    with open(path,newline="",encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            try:
                t=int(float(r["time"]))
                if t>10_000_000_000: t//=1000
                close=float(r["close"]); volume=float(r.get("volume",0) or 0)
                if t>0 and close>0: rows.append((t,close,volume))
            except (ValueError,KeyError,TypeError): pass
    rows=sorted({t:(t,c,v) for t,c,v in rows}.values())
    if len(rows)<20000: raise SystemExit(f"Only {len(rows)} valid 5m candles.")
    if (rows[-1][0]-rows[0][0])/86400<90: raise SystemExit("Dataset spans less than 90 days.")
    return rows


def aggregate(rows, seconds):
    buckets={}
    for t,c,v in rows:
        bucket=t//seconds
        buckets.setdefault(bucket,[]).append((t,c,v))
    out=[]
    for bucket,chunk in sorted(buckets.items()):
        chunk.sort()
        # A full interval must have expected 5m candles and regular spacing.
        expected=seconds//300
        if len(chunk)==expected and all(chunk[i+1][0]-chunk[i][0]==300 for i in range(expected-1)):
            out.append({"time":bucket*seconds,"close":chunk[-1][1],"volume":sum(x[2] for x in chunk)})
    return out


def signal(rows,i,kind,fast,slow):
    closes=[r["close"] for r in rows]
    if kind=="ma":
        if i+1<slow: return 0
        return int(sum(closes[i-fast+1:i+1])/fast > sum(closes[i-slow+1:i+1])/slow)
    if kind=="breakout":
        if i<slow: return 0
        return int(closes[i] > max(closes[i-slow:i]))
    if kind=="channel_filter":
        if i<slow or i+1<fast: return 0
        return int(closes[i] > max(closes[i-slow:i]) and sum(closes[i-fast+1:i+1])/fast > sum(closes[i-slow+1:i+1])/slow)
    return 0


def run(rows, kind, fast, slow, fee, slip, start, end):
    # Signals use the prior candle only; returns start on the next candle.
    end=min(end,len(rows))
    pos=0; balance=1000.; peak=balance; maxdd=0.; trades=0; wins=0; gross_profit=0.; gross_loss=0.
    prev_close=None
    for i in range(max(start,slow),end):
        close=rows[i]["close"]
        if prev_close is not None and pos:
            market_ret=close/prev_close-1
            balance *= max(0.000001,1+market_ret-2*slip)
            peak=max(peak,balance); maxdd=max(maxdd,(peak-balance)/peak)
        target=signal(rows,i-1,kind,fast,slow) if i>0 else 0
        if target!=pos:
            # One entry/exit side per position change. Fee and slippage applied on each side.
            balance *= max(0.000001,1-fee-slip)
            if pos==1 and target==0:
                balance *= max(0.000001,1-fee-slip)
                trades+=1
                # Approximate closed-trade classification by balance movement since last entry.
                if entry_balance is not None:
                    pnl=balance-entry_balance
                    if pnl>0: wins+=1; gross_profit+=pnl
                    elif pnl<0: gross_loss+=-pnl
            if target==1: entry_balance=balance
            pos=target
            peak=max(peak,balance); maxdd=max(maxdd,(peak-balance)/peak)
        prev_close=close
    # Force close at the end of the segment; include exit costs.
    if pos:
        balance*=max(0.000001,1-fee-slip)
        trades+=1
        if entry_balance is not None:
            pnl=balance-entry_balance
            if pnl>0: wins+=1; gross_profit+=pnl
            elif pnl<0: gross_loss+=-pnl
    return {"return_pct":round((balance/1000-1)*100,2),"final_balance":round(balance,2),
            "trades":trades,"win_rate_pct":round(wins/trades*100,2) if trades else 0,
            "profit_factor":round(gross_profit/gross_loss,3) if gross_loss else ("infinity" if gross_profit else 0),
            "max_drawdown_pct":round(maxdd*100,2)}


def main():
    raw=load_5m(sys.argv[1] if len(sys.argv)>1 else "kraken_multi_month.csv")
    frames={"4h":aggregate(raw,14400),"1d":aggregate(raw,86400)}
    results=[]
    for tf,rows in frames.items():
        if len(rows)<250: continue
        n=len(rows); a=int(n*.6); b=int(n*.8)
        candidates=[]
        for kind in ("ma","breakout","channel_filter"):
            for fast,slow in ((5,20),(10,30),(20,50),(20,100)):
                if fast>=slow: continue
                report=run(rows,kind,fast,slow,0.001,0.001,0,a)
                candidates.append({"kind":kind,"fast":fast,"slow":slow,"train":report})
        # Select using training data only; validation and final test are not used for selection.
        best=max(candidates,key=lambda x:x["train"]["return_pct"])
        fee_reports=[]
        for fee in (0.008,0.004,0.002,0.001):
            fee_reports.append({"fee_per_side_pct":fee*100,
                "validation":run(rows,best["kind"],best["fast"],best["slow"],fee,0.001,a,b),
                "final_test":run(rows,best["kind"],best["fast"],best["slow"],fee,0.001,b,n)})
        results.append({"timeframe":tf,"candles":n,"train_candles":a,"validation_candles":b-a,"final_test_candles":n-b,
            "selected_on_training_only":{k:v for k,v in best.items() if k!="train"},
            "training_result":best["train"],"fee_sensitivity":fee_reports,
            "promotion_passed":all(x["validation"]["return_pct"]>0 and x["final_test"]["return_pct"]>0 and x["validation"]["trades"]>=10 and x["final_test"]["trades"]>=10 for x in fee_reports)})
    print(json.dumps({"dataset_start_utc":datetime.fromtimestamp(raw[0][0],timezone.utc).isoformat(),
      "dataset_end_utc":datetime.fromtimestamp(raw[-1][0],timezone.utc).isoformat(),"source_5m_candles":len(raw),
      "method":"4h and daily MA, channel breakout, and trend-filtered breakout; 60/20/20 chronological split; select rule on train only; fee and 0.1% adverse slippage per side.",
      "note":"Exploratory paper research. Strategy chosen only on training data. No live orders. A positive result on this single period is not a guarantee.",
      "results":results},indent=2))


if __name__=="__main__": main()
