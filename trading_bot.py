#!/usr/bin/env python3
"""AI Capital Lab BTC/USDT research bot. BACKTEST and PAPER only; never places orders."""
import argparse
import csv
import json
import math
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PAIR = "XBTUSDT"
INTERVAL_MINUTES = 5
STARTING_BALANCE = 1000.0
RISK_FRACTION = 0.01
STOP_FRACTION = 0.01
TAKE_PROFIT_FRACTION = 0.02
FEE_PER_SIDE = 0.008  # configurable; 0.8% per side is a conservative test assumption
SLIPPAGE = 0.0
EMA_FAST = 20
EMA_SLOW = 50
RSI_PERIOD = 14


def ema(values, period):
    out = [None] * len(values)
    if len(values) < period:
        return out
    alpha = 2.0 / (period + 1)
    current = sum(values[:period]) / period
    out[period - 1] = current
    for i in range(period, len(values)):
        current = values[i] * alpha + current * (1 - alpha)
        out[i] = current
    return out


def rsi(values, period=RSI_PERIOD):
    out = [None] * len(values)
    if len(values) <= period:
        return out
    gains = [max(values[i] - values[i - 1], 0.0) for i in range(1, len(values))]
    losses = [max(values[i - 1] - values[i], 0.0) for i in range(1, len(values))]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    out[period] = 100.0 if avg_loss == 0 and avg_gain else (0.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss))
    for i in range(period + 1, len(values)):
        avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        out[i] = 100.0 if avg_loss == 0 and avg_gain else (0.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss))
    return out


def read_csv(path):
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("CSV saknar rubrikrad.")
        names = {name.strip().lower(): name for name in reader.fieldnames}
        def field(*options):
            for option in options:
                if option in names:
                    return names[option]
            return None
        fields = {
            "time": field("time", "timestamp", "date", "datetime"),
            "open": field("open", "o"),
            "high": field("high", "h"),
            "low": field("low", "l"),
            "close": field("close", "c"),
            "volume": field("volume", "vol", "v"),
        }
        if any(fields[k] is None for k in ("open", "high", "low", "close")):
            raise ValueError("CSV måste innehålla open, high, low och close-kolumner.")
        for row in reader:
            try:
                candle = {k: float(row[v]) for k, v in fields.items() if k != "time" and v}
                candle["time"] = row[fields["time"]] if fields["time"] else str(len(rows))
                if all(math.isfinite(candle[k]) for k in ("open", "high", "low", "close")) and min(candle["open"], candle["high"], candle["low"], candle["close"]) > 0:
                    rows.append(candle)
            except (ValueError, TypeError):
                continue
    if len(rows) < EMA_SLOW + RSI_PERIOD + 2:
        raise ValueError(f"För få giltiga candles ({len(rows)}). Minst {EMA_SLOW + RSI_PERIOD + 2} behövs.")
    return rows


def backtest(rows, starting_balance, fee, slippage):
    closes = [r["close"] for r in rows]
    fast, slow, rsis = ema(closes, EMA_FAST), ema(closes, EMA_SLOW), rsi(closes)
    balance = starting_balance
    equity_peak = balance
    max_dd = 0.0
    fees_total = 0.0
    trades = []
    position = None
    for i in range(1, len(rows)):
        row = rows[i]
        # Manage an open position using only this candle's OHLC. If both levels hit,
        # assume the stop was hit first (conservative; candle order is unknown).
        if position:
            stop, target = position["stop"], position["target"]
            exit_price, reason = None, None
            if row["low"] <= stop:
                exit_price, reason = stop * (1 - slippage), "stop"
            elif row["high"] >= target:
                exit_price, reason = target * (1 - slippage), "take-profit"
            elif i == len(rows) - 1:
                exit_price, reason = row["close"] * (1 - slippage), "end-of-data"
            if exit_price is not None:
                gross = (exit_price - position["entry"]) * position["qty"]
                exit_fee = exit_price * position["qty"] * fee
                net = gross - exit_fee - position["entry_fee"]
                balance += gross - exit_fee
                fees_total += exit_fee
                trades.append({"entry_time": position["time"], "exit_time": row["time"], "entry": round(position["entry"], 8),
                               "exit": round(exit_price, 8), "net_pnl": round(net, 4), "reason": reason})
                position = None
        # Signal from the just-closed candle i-1; enter at current candle open.
        signal_i = i - 1
        if position is None and fast[signal_i] is not None and slow[signal_i] is not None and rsis[signal_i] is not None:
            prev = signal_i - 1
            crossed_up = prev >= 0 and fast[prev] is not None and slow[prev] is not None and fast[prev] <= slow[prev] and fast[signal_i] > slow[signal_i]
            if crossed_up and rsis[signal_i] > 50:
                entry = row["open"] * (1 + slippage)
                stop = entry * (1 - STOP_FRACTION)
                target = entry * (1 + TAKE_PROFIT_FRACTION)
                risk_cash = balance * RISK_FRACTION
                qty = risk_cash / max(entry - stop, 1e-12)
                # Account for entry fee and available cash; no leverage is used.
                qty = min(qty, balance / (entry * (1 + fee)))
                entry_fee = entry * qty * fee
                if qty > 0 and entry * qty + entry_fee <= balance:
                    balance -= entry_fee
                    fees_total += entry_fee
                    position = {"entry": entry, "stop": stop, "target": target, "qty": qty,
                                "entry_fee": entry_fee, "time": row["time"]}
        if position:
            equity = balance + position["qty"] * row["close"]
        else:
            equity = balance
        equity_peak = max(equity_peak, equity)
        if equity_peak > 0:
            max_dd = max(max_dd, (equity_peak - equity) / equity_peak)
    if position:
        row = rows[-1]
        exit_price = row["close"] * (1 - slippage)
        gross = (exit_price - position["entry"]) * position["qty"]
        exit_fee = exit_price * position["qty"] * fee
        net = gross - exit_fee - position["entry_fee"]
        balance += gross - exit_fee
        fees_total += exit_fee
        trades.append({"entry_time": position["time"], "exit_time": row["time"], "entry": round(position["entry"], 8),
                       "exit": round(exit_price, 8), "net_pnl": round(net, 4), "reason": "end-of-data"})
    wins = sum(t["net_pnl"] > 0 for t in trades)
    losses = sum(t["net_pnl"] <= 0 for t in trades)
    gross_profit = sum(t["net_pnl"] for t in trades if t["net_pnl"] > 0)
    gross_loss = -sum(t["net_pnl"] for t in trades if t["net_pnl"] < 0)
    report = {
        "mode": "BACKTEST_ONLY", "pair": PAIR, "timeframe": "5m", "candles": len(rows),
        "starting_balance": round(starting_balance, 2), "final_balance": round(balance, 2),
        "total_return_pct": round((balance / starting_balance - 1) * 100, 2),
        "trades": len(trades), "wins": wins, "losses": losses,
        "win_rate_pct": round(wins / len(trades) * 100, 2) if trades else 0.0,
        "fees_total": round(fees_total, 4), "max_drawdown_pct": round(max_dd * 100, 2),
        "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss else (None if not gross_profit else "infinity"),
        "avg_net_pnl": round(sum(t["net_pnl"] for t in trades) / len(trades), 4) if trades else 0.0,
        "fee_per_side_pct": round(fee * 100, 3), "slippage_pct": round(slippage * 100, 3),
        "strategy": "Long only; EMA20/EMA50 bullish cross, RSI14 > 50; 1% stop, 2% target; 1% balance risk; one position at a time.",
        "caveat": "Historical simulation is not a prediction. OHLC candles cannot reveal exact intrabar order; stop is assumed first if stop and target both hit."
    }
    return report, trades


def fetch_kraken():
    # Kraken public OHLC endpoint: no account credentials; limited to recent candles.
    query = urllib.parse.urlencode({"pair": PAIR, "interval": INTERVAL_MINUTES})
    url = "https://api.kraken.com/0/public/OHLC?" + query
    request = urllib.request.Request(url, headers={"User-Agent": "AI-Capital-Lab-paper/1.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        data = json.loads(response.read().decode("utf-8"))
    if data.get("error"):
        raise RuntimeError("; ".join(data["error"]))
    result = data["result"]
    key = next(k for k in result if k != "last")
    rows = []
    for c in result[key]:
        rows.append({"time": datetime.fromtimestamp(int(c[0]), timezone.utc).isoformat(),
                     "open": float(c[1]), "high": float(c[2]), "low": float(c[3]), "close": float(c[4]), "volume": float(c[6])})
    return rows


def paper(rows, fee):
    closes = [r["close"] for r in rows]
    fast, slow, rsis = ema(closes, EMA_FAST), ema(closes, EMA_SLOW), rsi(closes)
    i = len(rows) - 1
    if i < 1 or fast[i - 1] is None or slow[i - 1] is None or rsis[i - 1] is None or fast[i] is None or slow[i] is None or rsis[i] is None:
        raise ValueError("Inte tillräckligt med candles för att beräkna indikatorer.")
    signal = "WATCH / NO ENTRY"
    if fast[i - 1] <= slow[i - 1] and fast[i] > slow[i] and rsis[i] > 50:
        signal = "PAPER LONG SIGNAL"
    return {"mode": "PAPER_ONLY", "pair": PAIR, "timeframe": "5m", "latest_candle_utc": rows[-1]["time"],
            "latest_close": rows[-1]["close"], "ema20": round(fast[i], 4), "ema50": round(slow[i], 4),
            "rsi14": round(rsis[i], 2), "signal": signal, "fee_per_side_pct": round(fee * 100, 3),
            "real_orders_enabled": False, "note": "Uses Kraken public market data only. No account, API keys, orders, or persistent position."}


def main():
    parser = argparse.ArgumentParser(description="AI Capital Lab — Kraken BTC/USDT paper/backtest only")
    parser.add_argument("MODE", choices=["BACKTEST", "PAPER"])
    parser.add_argument("--csv", help="Historical OHLCV CSV for backtest")
    parser.add_argument("--balance", type=float, default=STARTING_BALANCE, help="Starting balance in quote currency (default 1000)")
    parser.add_argument("--fee", type=float, default=FEE_PER_SIDE, help="Fee per side as decimal; default 0.008 = 0.8%%")
    parser.add_argument("--slippage", type=float, default=SLIPPAGE, help="Slippage as decimal; default 0")
    args = parser.parse_args()
    if args.balance <= 0 or not 0 <= args.fee < 0.1 or not 0 <= args.slippage < 0.1:
        parser.error("balance must be >0; fee and slippage must be between 0 and 0.1.")
    try:
        if args.MODE == "BACKTEST":
            if not args.csv:
                parser.error("BACKTEST requires --csv path/to/candles.csv")
            report, trades = backtest(read_csv(Path(args.csv)), args.balance, args.fee, args.slippage)
            print(json.dumps({"report": report, "trades_detail": trades}, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(paper(fetch_kraken(), args.fee), ensure_ascii=False, indent=2))
    except Exception as exc:
        print(json.dumps({"error": str(exc), "real_orders_enabled": False}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
