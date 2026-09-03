# -*- coding: utf-8 -*-
from .base import ExchangeAdapter

SPOT_BASE = "https://api.mexc.com"
FUT_BASE = "https://contract.mexc.com"


class MXCAdapter(ExchangeAdapter):
    name = "mxc"

    def to_exchange_symbol(self, symbol: str) -> str:
        base, quote = symbol.split("/")
        return f"{base}{quote}"

    def _futures_symbol(self, symbol: str) -> str:
        base, quote = symbol.split("/")
        return f"{base}_{quote}"

    def get_klines(self, symbol: str, interval: str = "5m", limit: int = 100) -> list[dict]:
        sym = self.to_exchange_symbol(symbol)
        data = self._get(f"{SPOT_BASE}/api/v3/klines",
                          {"symbol": sym, "interval": interval, "limit": limit})
        if not data:
            return []
        return [
            {"ts": int(k[0]), "open": float(k[1]), "high": float(k[2]),
             "low": float(k[3]), "close": float(k[4]), "volume": float(k[5])}
            for k in data
        ]

    def get_orderbook(self, symbol: str, depth: int = 50) -> dict:
        sym = self.to_exchange_symbol(symbol)
        data = self._get(f"{SPOT_BASE}/api/v3/depth", {"symbol": sym, "limit": depth})
        if not data:
            return {"bids": [], "asks": []}
        return {
            "bids": [[float(p), float(q)] for p, q in data.get("bids", [])],
            "asks": [[float(p), float(q)] for p, q in data.get("asks", [])],
        }

    def get_ticker(self, symbol: str) -> dict:
        sym = self.to_exchange_symbol(symbol)
        data = self._get(f"{SPOT_BASE}/api/v3/ticker/24hr", {"symbol": sym})
        if not data:
            return {"last": 0.0, "quote_volume_24h": 0.0, "price_change_pct_24h": 0.0}
        return {
            "last": float(data.get("lastPrice", 0)),
            "quote_volume_24h": float(data.get("quoteVolume", 0)),
            "price_change_pct_24h": float(data.get("priceChangePercent", 0)),
        }

    def get_funding_rate(self, symbol: str) -> dict | None:
        sym = self._futures_symbol(symbol)
        data = self._get(f"{FUT_BASE}/api/v1/contract/funding_rate/{sym}")
        if not data or not data.get("success") or not data.get("data"):
            return None
        r = data["data"]
        return {"funding_rate": float(r.get("fundingRate", 0)),
                "next_funding_ts": int(r.get("nextSettleTime", 0)) or None}

    def get_open_interest(self, symbol: str) -> dict | None:
        sym = self._futures_symbol(symbol)
        data = self._get(f"{FUT_BASE}/api/v1/contract/open_interest/{sym}")
        if not data or not data.get("success") or not data.get("data"):
            return None
        r = data["data"]
        return {"oi": float(r.get("holdVol", 0) or 0), "oi_in_usdt": None}
