#!/usr/bin/env python3
"""Cost-aware hourly BTC ML walk-forward research. Research only; never places orders."""
import csv, json, math, sys
from datetime import datetime, timezone
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

FEATURES = ["ret_1", "ret_3", "ret_6", "ret_12", "ret_24", "ret_72",
            "vol_24", "vol_72", "ma_gap_24", "ma_gap_168", "rsi_14",
            "range_pct", "volume_change", "hour_sin", "hour_cos", "dow_sin", "dow_cos"]

def load_hourly(path):
    rows = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.reader(f):
            if len(row) < 6: continue
            try:
                t = int(float(row[0])); o,h,l,c,v = map(float,row[1:6])
                if t > 10_000_000_000: t //= 1000
                if t > 0 and min(o,h,l,c) > 0 and v >= 0:
                    rows[t] = (t,o,h,l,c,v)
            except (ValueError, TypeError): continue
    data = [rows[t] for t in sorted(rows)]
    if len(data) < 25000: raise SystemExit(f"Not enough hourly candles: {len(data)}")
    return data

def build(data):
    a = np.asarray(data, dtype=float)
    t,o,h,l,c,v = a.T
    r = np.zeros(len(c))
    r[1:] = c[1:] / c[:-1] - 1
    feats = []
    for i in range(len(c)):
        if i < 200: 
            feats.append(None); continue
        def ret(n): return c[i] / c[i-n] - 1
        def vol(n): return float(np.std(r[i-n+1:i+1], ddof=0))
        changes = np.diff(c[i-13:i+1])
        gains = np.maximum(changes,0).mean(); losses = np.maximum(-changes,0).mean()
        rsi = 50.0 if gains + losses == 0 else 100 - 100/(1 + gains/(losses + 1e-12))
        hour = (int(t[i]//3600)%24) * 2*math.pi/24
        dow = (datetime.fromtimestamp(t[i],timezone.utc).weekday()) * 2*math.pi/7
        feats.append([ret(1),ret(3),ret(6),ret(12),ret(24),ret(72),
            vol(24),vol(72), c[i]/np.mean(c[i-23:i+1])-1,
            c[i]/np.mean(c[i-167:i+1])-1, rsi, (h[i]-l[i])/c[i],
            v[i]/(np.mean(v[i-23:i+1])+1e-12)-1,
            math.sin(hour),math.cos(hour),math.sin(dow),math.cos(dow)])
    X = np.asarray([x if x is not None else [np.nan]*len(FEATURES) for x in feats])
    # Prediction made after candle i close; target is next candle's return.
    y = np.full(len(c), np.nan)
    y[:-1] = c[1:] / c[:-1] - 1
    return X, y

def simulate(pred, actual, timestamps, start_equity=1000., fee=.001, slip=.001, threshold=.002):
    equity=start_equity; peak=equity; maxdd=0.; pos=0; changes=0; trades=0
    wins=0; gross=0.; daily=[]; last_day=None; day_start=equity
    for p,r,t in zip(pred,actual,timestamps):
        target = 1 if p > threshold else 0
        if target != pos:
            equity *= max(0.,1.-fee-slip)
            if pos == 1: trades += 1
            pos=target; changes += 1
        before=equity
        if pos: equity *= max(0.,1.+r)
        if pos and r > 0: wins += 1
        gross += r if pos else 0.
        peak=max(peak,equity)
        maxdd=max(maxdd,(peak-equity)/peak if peak else 0.)
        day=int(t//86400)
        if last_day is not None and day != last_day:
            daily.append(equity/day_start-1); day_start=equity
        last_day=day
    if pos: trades += 1
    return {"final_balance":round(equity,2),"return_pct":round((equity/start_equity-1)*100,2),
            "max_drawdown_pct":round(maxdd*100,2),"position_changes":changes,
            "completed_or_open_exits":trades,"profitable_held_hours_pct":round(wins/max(1,sum(1 for p in pred if p>threshold))*100,2)}

def main():
    path=sys.argv[1] if len(sys.argv)>1 else "kraken_btc_hourly.csv"
    data=load_hourly(path); X,y=build(data); n=len(data)
    # Reserve the earliest 60% for initial training; evaluate only later data in sequential 30-day folds.
    first=max(24*365*2, int(n*.60))
    fold_hours=24*30
    predictions=[]; actual=[]; times=[]; fold_meta=[]
    for start in range(first, n-1, fold_hours):
        end=min(n-1,start+fold_hours)
        train_end=start
        train_idx=np.arange(200,train_end)
        train_idx=train_idx[np.isfinite(y[train_idx]) & np.isfinite(X[train_idx]).all(axis=1)]
        test_idx=np.arange(start,end)
        test_idx=test_idx[np.isfinite(y[test_idx]) & np.isfinite(X[test_idx]).all(axis=1)]
        if len(train_idx)<24*365 or len(test_idx)==0: continue
        # Fit only on past data; no shuffled splits or future feature values.
        model=HistGradientBoostingRegressor(max_iter=100,max_leaf_nodes=15,learning_rate=.06,
            l2_regularization=2.0,random_state=7)
        model.fit(X[train_idx],y[train_idx])
        p=model.predict(X[test_idx])
        predictions.extend(p.tolist()); actual.extend(y[test_idx].tolist()); times.extend(data[i][0] for i in test_idx)
        fold_meta.append({"train_rows":int(len(train_idx)),"test_rows":int(len(test_idx)),
            "test_start":datetime.fromtimestamp(data[test_idx[0]][0],timezone.utc).isoformat(),
            "test_end":datetime.fromtimestamp(data[test_idx[-1]][0],timezone.utc).isoformat()})
    if len(actual)<1000: raise SystemExit(f"Insufficient out-of-sample predictions: {len(actual)}")
    preds=np.asarray(predictions); rets=np.asarray(actual); ts=np.asarray(times)
    reports=[]
    # Fixed forecast thresholds avoid selecting a threshold on the final test period.
    for fee in (.008,.004,.002,.001):
        cost=fee+.001
        for multiplier in (1.0,1.5,2.0):
            threshold=2*cost*multiplier
            strat=simulate(preds,rets,ts,fee=fee,slip=.001,threshold=threshold)
            # Buy-and-hold on exactly the same out-of-sample hourly returns, with entry/exit costs.
            bh=simulate(np.ones(len(preds)),rets,ts,fee=fee,slip=.001,threshold=-1.)
            cash={"final_balance":1000.0,"return_pct":0.0,"max_drawdown_pct":0.0,"position_changes":0}
            reports.append({"fee_per_side_pct":fee*100,"slippage_per_side_pct":.1,
                "threshold_round_trip_cost_multiple":multiplier,"forecast_threshold_pct":round(threshold*100,3),
                "strategy":strat,"buy_hold":bh,"cash":cash,
                "beats_buy_hold":bool(strat["return_pct"]>bh["return_pct"]),
                "beats_cash":bool(strat["return_pct"]>0)})
    passed=all(x["beats_buy_hold"] and x["beats_cash"] for x in reports)
    print(json.dumps({"pair":"XBT/USD","candles":n,
        "start_utc":datetime.fromtimestamp(data[0][0],timezone.utc).isoformat(),
        "end_utc":datetime.fromtimestamp(data[-1][0],timezone.utc).isoformat(),
        "model":"HistGradientBoostingRegressor","feature_count":len(FEATURES),
        "out_of_sample_predictions":len(actual),"fold_count":len(fold_meta),
        "walk_forward_folds":fold_meta,"results":reports,"promotion_passed":passed,
        "methodology":"Sequential 30-day test folds; each model trains only on earlier rows; next-hour close-to-close target; position decision after current close; costs charged on every position change; fixed cost-aware thresholds; research only, no orders."},indent=2))
if __name__=="__main__": main()
