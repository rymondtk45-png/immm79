# -*- coding: utf-8 -*-
from .base import ExchangeAdapter

SPOT_BASE = "https://api.binance.com"
FUT_BASE = "https://fapi.binance.com"


class BinanceAdapter(ExchangeAdapter):
    name = "binance"

    def to_exchange_symbol(self, symbol: str) -> str:
        base, quote = symbol.split("/")
        return f"{base}{quote}"

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
        sym = self.to_exchange_symbol(symbol)
        data = self._get(f"{FUT_BASE}/fapi/v1/premiumIndex", {"symbol": sym})
        if not data:
            return None
        return {
            "funding_rate": float(data.get("lastFundingRate", 0)),
            "next_funding_ts": int(data.get("nextFundingTime", 0)) or None,
        }

    def get_open_interest(self, symbol: str) -> dict | None:
        sym = self.to_exchange_symbol(symbol)
        data = self._get(f"{FUT_BASE}/fapi/v1/openInterest", {"symbol": sym})
        if not data:
            return None
        oi = float(data.get("openInterest", 0))
        return {"oi": oi, "oi_in_usdt": None}

    def get_long_short_ratio(self, symbol: str) -> dict | None:
        sym = self.to_exchange_symbol(symbol)
        data = self._get(f"{FUT_BASE}/futures/data/globalLongShortAccountRatio",
                          {"symbol": sym, "period": "5m", "limit": 1})
        if not data:
            return None
        row = data[-1] if isinstance(data, list) and data else None
        if not row:
            return None
        return {"long_ratio": float(row.get("longAccount", 0)),
                "short_ratio": float(row.get("shortAccount", 0))}
