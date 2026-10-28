#!/usr/bin/env python3
"""Cost-aware hourly BTC forecast research. Offline backtest only; never places orders."""
import csv, json, math, sys
from datetime import datetime, timezone


def load(path):
    raw_rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            try:
                t = int(float(r["time"]))
                # Normalize millisecond Unix timestamps if a source ever supplies them.
                if t > 10_000_000_000:
                    t //= 1000
                c = float(r["close"])
                v = float(r.get("volume", 0) or 0)
                if t > 0 and c > 0 and v >= 0:
                    raw_rows.append((t, c, v))
            except (ValueError, KeyError, TypeError):
                continue
    raw_rows.sort()
    # Deduplicate timestamps before aggregating.
    by_time = {t: (c, v) for t, c, v in raw_rows}
    raw_rows = [(t, *by_time[t]) for t in sorted(by_time)]
    if len(raw_rows) < 20_000:
        raise SystemExit(f"Only {len(raw_rows)} valid 5-minute candles; expected a multi-month dataset (at least 20,000).")
    span_days = (raw_rows[-1][0] - raw_rows[0][0]) / 86400
    if span_days < 90:
        raise SystemExit(f"Dataset spans only {span_days:.1f} days; refusing to treat it as multi-month research.")
    # Aggregate into UTC clock hours; only keep complete 12-candle hours.
    hours = {}
    for t, c, v in raw_rows:
        h = t // 3600
        hours.setdefault(h, []).append((t, c, v))
    out = []
    for h, chunk in sorted(hours.items()):
        chunk.sort()
        if len(chunk) == 12 and all(chunk[i+1][0] - chunk[i][0] == 300 for i in range(11)):
            out.append({"time": h * 3600, "close": chunk[-1][1], "volume": sum(x[2] for x in chunk)})
    if len(out) < 500:
        raise SystemExit(f"Too few complete hourly candles after aggregation: {len(out)}")
    return raw_rows, out


def features(rows, i):
    closes = [r["close"] for r in rows]
    out = []
    for n in (1, 2, 3, 6, 12, 24, 48, 72, 168):
        if i < n:
            return None
        out.append(closes[i] / closes[i-n] - 1)
    rets = [closes[j] / closes[j-1] - 1 for j in range(max(1, i-23), i+1)]
    recent = rows[max(0, i-23):i+1]
    out += [math.sqrt(sum(x*x for x in rets)),
            rows[i]["volume"] / (sum(r["volume"] for r in recent) / max(1, len(recent)) + 1e-12)]
    return out


def simulate(rows, model, fee, slip, horizon=4, start=0, end=None):
    end = len(rows) if end is None else min(end, len(rows))
    balance = 1000.0
    peak = balance
    maxdd = 0.0
    trades = []
    i = max(start, 168)
    while i + horizon < end:
        x = features(rows, i)
        if x is None:
            i += 1
            continue
        pred = float(model.predict([x])[0])
        threshold = 2 * fee + 2 * slip
        if pred > threshold:
            entry = rows[i+1]["close"] * (1 + slip)
            exitp = rows[i+1+horizon]["close"] * (1 - slip)
            ret = exitp / entry - 1 - 2 * fee
            balance *= 1 + ret
            trades.append(ret)
            peak = max(peak, balance)
            maxdd = max(maxdd, (peak - balance) / peak)
            i += horizon + 1
        else:
            i += 1
    wins = sum(x > 0 for x in trades)
    gp = sum(x for x in trades if x > 0)
    gl = -sum(x for x in trades if x < 0)
    return {"return_pct": round((balance / 1000 - 1) * 100, 2),
            "final_balance": round(balance, 2), "trades": len(trades),
            "win_rate_pct": round(100 * wins / len(trades), 2) if trades else 0,
            "profit_factor": round(gp / gl, 3) if gl else ("infinity" if gp else 0),
            "max_drawdown_pct": round(maxdd * 100, 2),
            "fees_slippage_threshold_pct": round((2 * fee + 2 * slip) * 100, 3)}


def main():
    raw_rows, rows = load(sys.argv[1] if len(sys.argv) > 1 else "kraken_multi_month.csv")
    horizon = 4
    X, y, indices = [], [], []
    for i in range(168, len(rows) - horizon):
        x = features(rows, i)
        if x is not None:
            X.append(x)
            y.append(rows[i+horizon]["close"] / rows[i]["close"] - 1)
            indices.append(i)
    n = len(X)
    a, b = int(n * .6), int(n * .8)
    if a < 200 or b-a < 50 or n-b < 50:
        raise SystemExit(f"Not enough samples for chronological splits: {n}")
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import make_pipeline
    reports = []
    for fee in (0.008, 0.004, 0.002, 0.001):
        model = make_pipeline(SimpleImputer(strategy="median"),
            HistGradientBoostingRegressor(max_iter=100, max_leaf_nodes=7,
                l2_regularization=2.0, learning_rate=0.05, random_state=7))
        model.fit(X[:a], y[:a])
        val = simulate(rows, model, fee, 0.001, horizon, indices[a], indices[b-1]+horizon+1)
        test = simulate(rows, model, fee, 0.001, horizon, indices[b], indices[-1]+horizon+1)
        reports.append({"fee_per_side_pct": fee*100, "adverse_slippage_per_side_pct": 0.1,
                        "validation": val, "final_test": test})
    fmt = lambda t: datetime.fromtimestamp(t, timezone.utc).isoformat()
    print(json.dumps({
        "strategy": "Hourly HistGradientBoosting forecast; long-only; four-hour holding; trades only when predicted return exceeds round-trip fees plus 0.1% adverse slippage per side.",
        "source_candles_5m": len(raw_rows),
        "hourly_candles_after_strict_aggregation": len(rows),
        "dataset_start_utc": fmt(raw_rows[0][0]),
        "dataset_end_utc": fmt(raw_rows[-1][0]),
        "dataset_span_days": round((raw_rows[-1][0]-raw_rows[0][0])/86400, 2),
        "samples": n,
        "chronological_split": {"train_pct": 60, "validation_pct": 20, "untouched_final_test_pct": 20},
        "note": "Exploratory research only. Results are not proof of durable edge. No live orders, no exchange keys.",
        "fee_sensitivity": reports
    }, indent=2))


if __name__ == "__main__":
    main()
