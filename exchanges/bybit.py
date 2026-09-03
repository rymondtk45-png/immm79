# -*- coding: utf-8 -*-
from .base import ExchangeAdapter

BASE = "https://api.bybit.com"

# Bybit v5 kline interval dùng số phút, không phải "5m"
_INTERVAL_MAP = {"1m": "1", "3m": "3", "5m": "5", "15m": "15", "30m": "30",
                  "1h": "60", "4h": "240", "1d": "D"}


class BybitAdapter(ExchangeAdapter):
    name = "bybit"

    def to_exchange_symbol(self, symbol: str) -> str:
        base, quote = symbol.split("/")
        return f"{base}{quote}"

    def get_klines(self, symbol: str, interval: str = "5m", limit: int = 100) -> list[dict]:
        sym = self.to_exchange_symbol(symbol)
        iv = _INTERVAL_MAP.get(interval, "5")
        data = self._get(f"{BASE}/v5/market/kline",
                          {"category": "spot", "symbol": sym, "interval": iv, "limit": limit})
        if not data or data.get("retCode") != 0:
            return []
        rows = data.get("result", {}).get("list", [])
        # Bybit trả mới nhất trước -> đảo lại cho tăng dần theo thời gian
        rows = list(reversed(rows))
        return [
            {"ts": int(r[0]), "open": float(r[1]), "high": float(r[2]),
             "low": float(r[3]), "close": float(r[4]), "volume": float(r[5])}
            for r in rows
        ]

    def get_orderbook(self, symbol: str, depth: int = 50) -> dict:
        sym = self.to_exchange_symbol(symbol)
        data = self._get(f"{BASE}/v5/market/orderbook",
                          {"category": "spot", "symbol": sym, "limit": min(depth, 50)})
        if not data or data.get("retCode") != 0:
            return {"bids": [], "asks": []}
        result = data.get("result", {})
        return {
            "bids": [[float(p), float(q)] for p, q in result.get("b", [])],
            "asks": [[float(p), float(q)] for p, q in result.get("a", [])],
        }

    def get_ticker(self, symbol: str) -> dict:
        sym = self.to_exchange_symbol(symbol)
        data = self._get(f"{BASE}/v5/market/tickers", {"category": "spot", "symbol": sym})
        if not data or data.get("retCode") != 0:
            return {"last": 0.0, "quote_volume_24h": 0.0, "price_change_pct_24h": 0.0}
        rows = data.get("result", {}).get("list", [])
        if not rows:
            return {"last": 0.0, "quote_volume_24h": 0.0, "price_change_pct_24h": 0.0}
        r = rows[0]
        return {
            "last": float(r.get("lastPrice", 0)),
            "quote_volume_24h": float(r.get("turnover24h", 0)),
            "price_change_pct_24h": float(r.get("price24hPcnt", 0)) * 100,
        }

    def get_funding_rate(self, symbol: str) -> dict | None:
        sym = self.to_exchange_symbol(symbol)
        data = self._get(f"{BASE}/v5/market/tickers", {"category": "linear", "symbol": sym})
        if not data or data.get("retCode") != 0:
            return None
        rows = data.get("result", {}).get("list", [])
        if not rows:
            return None
        r = rows[0]
        return {
            "funding_rate": float(r.get("fundingRate", 0)),
            "next_funding_ts": int(r.get("nextFundingTime", 0)) or None,
        }

    def get_open_interest(self, symbol: str) -> dict | None:
        sym = self.to_exchange_symbol(symbol)
        data = self._get(f"{BASE}/v5/market/open-interest",
                          {"category": "linear", "symbol": sym,
                           "intervalTime": "5min", "limit": 1})
        if not data or data.get("retCode") != 0:
            return None
        rows = data.get("result", {}).get("list", [])
        if not rows:
            return None
        return {"oi": float(rows[0].get("openInterest", 0)), "oi_in_usdt": None}

    def get_long_short_ratio(self, symbol: str) -> dict | None:
        sym = self.to_exchange_symbol(symbol)
        data = self._get(f"{BASE}/v5/market/account-ratio",
                          {"category": "linear", "symbol": sym, "period": "5min", "limit": 1})
        if not data or data.get("retCode") != 0:
            return None
        rows = data.get("result", {}).get("list", [])
        if not rows:
            return None
        r = rows[0]
        return {"long_ratio": float(r.get("buyRatio", 0)), "short_ratio": float(r.get("sellRatio", 0))}
