#!/usr/bin/env python3
"""Research-only BTC 5-minute day-trading strategy comparison. Never places orders."""
import csv, json, math, sys
from datetime import datetime, timezone
import numpy as np

def load(path):
    rows = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.reader(f):
            if len(row) < 6: continue
            try:
                t = int(float(row[0]))
                if t > 10_000_000_000: t //= 1000
                o,h,l,c,v = map(float,row[1:6])
                if t > 0 and min(o,h,l,c) > 0 and v >= 0:
                    rows[t] = (t,o,h,l,c,v)
            except (ValueError, TypeError):
                continue
    data = [rows[t] for t in sorted(rows)]
    if len(data) < 100_000:
        raise SystemExit(f"Not enough 5-minute candles: {len(data)}")
    return np.asarray(data, dtype=float)

def ema(x, span):
    out = np.empty(len(x), dtype=float)
    alpha = 2.0/(span+1.0)
    out[0] = x[0]
    for i in range(1,len(x)):
        out[i] = alpha*x[i] + (1-alpha)*out[i-1]
    return out

def rsi(close, period=14):
    delta = np.diff(close, prepend=close[0])
    gains = np.maximum(delta,0.0)
    losses = np.maximum(-delta,0.0)
    avg_g = np.full(len(close), np.nan); avg_l = np.full(len(close), np.nan)
    if len(close) <= period: return avg_g
    avg_g[period] = gains[1:period+1].mean()
    avg_l[period] = losses[1:period+1].mean()
    for i in range(period+1,len(close)):
        avg_g[i] = (avg_g[i-1]*(period-1)+gains[i])/period
        avg_l[i] = (avg_l[i-1]*(period-1)+losses[i])/period
    rs = avg_g/(avg_l+1e-12)
    return 100-100/(1+rs)

def make_signals(close):
    n=len(close)
    e48=ema(close,48); e144=ema(close,144)
    r=rsi(close,14)
    # Use persistent position states to avoid entering/exiting every candle.
    trend=np.zeros(n,dtype=int)
    active=False
    for i in range(1,n):
        if not active and e48[i]>e144[i] and e48[i-1]<=e144[i-1]:
            active=True
        elif active and (e48[i]<e144[i] or close[i]<e144[i]*0.985):
            active=False
        trend[i]=int(active)

    # 24-hour breakout, hold until price falls below a prior 8-hour low or trend filter.
    breakout=np.zeros(n,dtype=int)
    prior_high=np.full(n,np.nan); prior_low=np.full(n,np.nan)
    for i in range(288,n):
        prior_high[i]=np.max(close[i-288:i])
    for i in range(96,n):
        prior_low[i]=np.min(close[i-96:i])
    active=False
    for i in range(288,n):
        if not active and close[i]>prior_high[i] and e48[i]>e144[i]:
            active=True
        elif active and (close[i]<prior_low[i] or e48[i]<e144[i]):
            active=False
        breakout[i]=int(active)

    # Mean reversion with a cooldown: enter oversold only in a broad uptrend,
    # exit at RSI recovery, a 12-bar time stop, or trend invalidation.
    mr=np.zeros(n,dtype=int); active=False; held=0; cooldown=0
    for i in range(144,n):
        if cooldown>0: cooldown-=1
        if not active and cooldown==0 and r[i]<25 and close[i]>e144[i]:
            active=True; held=0
        elif active:
            held+=1
            if r[i]>50 or held>=12 or close[i]<e144[i]*0.985:
                active=False; cooldown=12
        mr[i]=int(active)
    return {
        "EMA 48/144 cross with 1.5% trend stop":trend,
        "24h breakout / 8h low exit":breakout,
        "RSI oversold, uptrend-only, cooldown":mr,
    }

def metrics(pos, returns, times, initial_balance, start_idx, end_idx, fee, slip, label):
    p=np.asarray(pos[start_idx:end_idx],dtype=int)
    r=np.asarray(returns[start_idx:end_idx],dtype=float)
    ts=np.asarray(times[start_idx:end_idx],dtype=np.int64)
    if len(p)==0: return {}
    # Each signal is delayed one candle: position decided at close i applies to return i -> i+1.
    equity=float(initial_balance); peak=equity; maxdd=0.; changes=0; entries=0; exits=0
    exposure=0; held_wins=0; prev=0; equity_curve=[]
    cost=fee+slip
    for target,ret in zip(p,r):
        if target != prev:
            equity *= max(0.,1.-cost)
            changes += 1
            if target == 1: entries += 1
            else: exits += 1
            prev=target
        if target:
            exposure += 1
            if ret>0: held_wins += 1
            equity *= max(0.,1.+ret)
        peak=max(peak,equity)
        maxdd=max(maxdd,(peak-equity)/peak if peak else 0.)
        equity_curve.append(equity)
    if prev: 
        equity *= max(0.,1.-cost)
        exits += 1
        changes += 1
    elapsed_days=max(1.,(ts[-1]-ts[0])/86400.)
    years=elapsed_days/365.25
    cagr=((equity/initial_balance)**(1/years)-1)*100 if equity>0 and years>0 else -100.
    return {"strategy":label,"final_balance":round(equity,2),
        "return_pct":round((equity/initial_balance-1)*100,2),"annualized_return_pct":round(cagr,2),
        "max_drawdown_pct":round(maxdd*100,2),"entries":entries,"exits":exits,
        "position_changes":changes,"time_in_market_pct":round(exposure/max(1,len(p))*100,2),
        "profitable_held_candles_pct":round(held_wins/max(1,exposure)*100,2)}

def main():
    path=sys.argv[1] if len(sys.argv)>1 else "kraken_btc_5m.csv"
    a=load(path); t=a[:,0].astype(np.int64); close=a[:,4]
    n=len(close)
    # Close-to-close returns. Signal at close i is shifted one candle before use.
    rets=np.zeros(n); rets[:-1]=close[1:]/close[:-1]-1
    signals=make_signals(close)
    split=int(n*.70)
    reports=[]
    # Fixed, realistic cost scenarios; no parameter tuning on the held-out period.
    for fee in (.001,.002,.004):
        slip=.0002
        for name,signal in signals.items():
            # First signal is only applied on the next candle; the final signal cannot create a future return.
            delayed=np.roll(signal,1); delayed[0]=0; delayed[-1]=0
            oos=metrics(delayed,rets,t,1000.,split,n-1,fee,slip,name)
            bh=np.ones(n,dtype=int); bh[-1]=0
            bhm=metrics(bh,rets,t,1000.,split,n-1,fee,slip,"BTC buy-and-hold")
            cash={"strategy":"Cash","final_balance":1000.0,"return_pct":0.0,"annualized_return_pct":0.0,"max_drawdown_pct":0.0,"entries":0,"exits":0,"position_changes":0,"time_in_market_pct":0.0}
            reports.append({"fee_per_side_pct":fee*100,"slippage_per_side_pct":slip*100,
                "oos_strategy":oos,"buy_hold":bhm,"cash":cash,
                "beats_buy_hold":bool(oos["return_pct"]>bhm["return_pct"]),
                "beats_cash":bool(oos["return_pct"]>0)})
    # Report the exact held-out period and all candidates; promotion requires every tested cost case to beat both benchmarks.
    passed=all(x["beats_buy_hold"] and x["beats_cash"] for x in reports)
    print(json.dumps({"pair":"XBT/USD","timeframe":"5m","candles":n,
        "start_utc":datetime.fromtimestamp(int(t[0]),timezone.utc).isoformat(),
        "end_utc":datetime.fromtimestamp(int(t[-1]),timezone.utc).isoformat(),
        "holdout_start_utc":datetime.fromtimestamp(int(t[split]),timezone.utc).isoformat(),
        "holdout_end_utc":datetime.fromtimestamp(int(t[-2]),timezone.utc).isoformat(),
        "training_fraction":0.70,"strategies_tested":len(signals),"results":reports,
        "promotion_passed":passed,
        "methodology":"Fixed, selective position-state rules; first 70% historical candles used as warm-up/training period; final 30% held out; completed-candle signals applied to next candle; fees and slippage charged on every position change; long/flat only; research only, no orders."},indent=2))
if __name__=="__main__": main()
