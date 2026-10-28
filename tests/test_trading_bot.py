import importlib.util
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("trading_bot", Path(__file__).resolve().parents[1] / "trading_bot.py")
bot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bot)


class TradingBotTests(unittest.TestCase):
    def test_ema_has_warmup_and_values(self):
        values = list(range(1, 61))
        result = bot.ema(values, 20)
        self.assertIsNone(result[18])
        self.assertIsNotNone(result[19])
        self.assertAlmostEqual(result[-1], 50.5 + (60 - 50.5) * 0.9, delta=10)

    def test_rsi_stays_bounded(self):
        values = [100 + i for i in range(80)]
        result = bot.rsi(values, 14)
        self.assertTrue(all(v is None or 0 <= v <= 100 for v in result))
        self.assertEqual(result[-1], 100.0)

    def test_position_size_includes_both_sides_of_fees_in_risk(self):
        balance, entry, fee = 1000.0, 100.0, 0.008
        stop = entry * (1 - bot.STOP_FRACTION)
        qty = bot.calculate_position_qty(balance, entry, stop, fee)
        modeled_stop_loss = qty * ((entry - stop) + entry * fee + stop * fee)
        self.assertLessEqual(modeled_stop_loss, balance * bot.RISK_FRACTION + 1e-9)
        self.assertLessEqual(qty * entry * (1 + fee), balance + 1e-9)

    def test_backtest_returns_metrics_and_never_negative_fees(self):
        # Deterministic synthetic candles; this is a mechanics test, not a profitability claim.
        rows = []
        price = 100.0
        for i in range(180):
            if i < 80:
                price += 0.15
            elif i < 100:
                price -= 0.35
            else:
                price += 0.22
            rows.append({"time": str(i), "open": price, "high": price * 1.004,
                         "low": price * 0.996, "close": price, "volume": 1.0})
        report, trades = bot.backtest(rows, 1000.0, 0.008, 0.0)
        self.assertEqual(report["mode"], "BACKTEST_ONLY")
        self.assertEqual(report["candles"], len(rows))
        self.assertGreaterEqual(report["fees_total"], 0)
        self.assertGreaterEqual(report["max_drawdown_pct"], 0)
        self.assertIsInstance(trades, list)
        self.assertAlmostEqual(report["final_balance"], 1000.0 + sum(t["net_pnl"] for t in trades), delta=0.02)
        self.assertFalse(report.get("real_orders_enabled", False))


if __name__ == "__main__":
    unittest.main()
