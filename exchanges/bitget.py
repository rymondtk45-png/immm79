# -*- coding: utf-8 -*-
from .base import ExchangeAdapter

BASE = "https://api.bitget.com"

_GRANULARITY_MAP = {"1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min",
                     "1h": "1h", "4h": "4h", "1d": "1day"}


class BitgetAdapter(ExchangeAdapter):
    name = "bitget"

    def to_exchange_symbol(self, symbol: str) -> str:
        base, quote = symbol.split("/")
        return f"{base}{quote}"

    def get_klines(self, symbol: str, interval: str = "5m", limit: int = 100) -> list[dict]:
        sym = self.to_exchange_symbol(symbol)
        gran = _GRANULARITY_MAP.get(interval, "5min")
        data = self._get(f"{BASE}/api/v2/spot/market/candles",
                          {"symbol": sym, "granularity": gran, "limit": limit})
        if not data or str(data.get("code")) != "00000":
            return []
        rows = data.get("data", [])  # Bitget trả cũ -> mới
        return [
            {"ts": int(r[0]), "open": float(r[1]), "high": float(r[2]),
             "low": float(r[3]), "close": float(r[4]), "volume": float(r[5])}
            for r in rows
        ]

    def get_orderbook(self, symbol: str, depth: int = 50) -> dict:
        sym = self.to_exchange_symbol(symbol)
        data = self._get(f"{BASE}/api/v2/spot/market/orderbook",
                          {"symbol": sym, "limit": min(depth, 150), "type": "step0"})
        if not data or str(data.get("code")) != "00000":
            return {"bids": [], "asks": []}
        r = data.get("data", {})
        return {
            "bids": [[float(p), float(q)] for p, q in r.get("bids", [])],
            "asks": [[float(p), float(q)] for p, q in r.get("asks", [])],
        }

    def get_ticker(self, symbol: str) -> dict:
        sym = self.to_exchange_symbol(symbol)
        data = self._get(f"{BASE}/api/v2/spot/market/tickers", {"symbol": sym})
        if not data or str(data.get("code")) != "00000" or not data.get("data"):
            return {"last": 0.0, "quote_volume_24h": 0.0, "price_change_pct_24h": 0.0}
        r = data["data"][0]
        return {
            "last": float(r.get("lastPr", 0)),
            "quote_volume_24h": float(r.get("quoteVolume", 0)),
            "price_change_pct_24h": float(r.get("change24h", 0)) * 100,
        }

    def get_funding_rate(self, symbol: str) -> dict | None:
        sym = self.to_exchange_symbol(symbol)
        data = self._get(f"{BASE}/api/v2/mix/market/current-fund-rate",
                          {"symbol": sym, "productType": "usdt-futures"})
        if not data or str(data.get("code")) != "00000" or not data.get("data"):
            return None
        r = data["data"][0]
        return {"funding_rate": float(r.get("fundingRate", 0)), "next_funding_ts": None}

    def get_open_interest(self, symbol: str) -> dict | None:
        sym = self.to_exchange_symbol(symbol)
        data = self._get(f"{BASE}/api/v2/mix/market/open-interest",
                          {"symbol": sym, "productType": "usdt-futures"})
        if not data or str(data.get("code")) != "00000" or not data.get("data"):
            return None
        r = data["data"]
        oi_list = r.get("openInterestList", []) if isinstance(r, dict) else []
        if not oi_list:
            return None
        return {"oi": float(oi_list[0].get("size", 0)), "oi_in_usdt": None}
