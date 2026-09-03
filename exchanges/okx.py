# -*- coding: utf-8 -*-
from .base import ExchangeAdapter

BASE = "https://www.okx.com"


class OKXAdapter(ExchangeAdapter):
    name = "okx"

    def to_exchange_symbol(self, symbol: str) -> str:
        base, quote = symbol.split("/")
        return f"{base}-{quote}"

    def _swap_symbol(self, symbol: str) -> str:
        return f"{self.to_exchange_symbol(symbol)}-SWAP"

    def get_klines(self, symbol: str, interval: str = "5m", limit: int = 100) -> list[dict]:
        sym = self.to_exchange_symbol(symbol)
        data = self._get(f"{BASE}/api/v5/market/candles",
                          {"instId": sym, "bar": interval, "limit": limit})
        if not data or data.get("code") != "0":
            return []
        rows = list(reversed(data.get("data", [])))
        return [
            {"ts": int(r[0]), "open": float(r[1]), "high": float(r[2]),
             "low": float(r[3]), "close": float(r[4]), "volume": float(r[5])}
            for r in rows
        ]

    def get_orderbook(self, symbol: str, depth: int = 50) -> dict:
        sym = self.to_exchange_symbol(symbol)
        data = self._get(f"{BASE}/api/v5/market/books", {"instId": sym, "sz": depth})
        if not data or data.get("code") != "0" or not data.get("data"):
            return {"bids": [], "asks": []}
        r = data["data"][0]
        return {
            "bids": [[float(p), float(q)] for p, q, *_ in r.get("bids", [])],
            "asks": [[float(p), float(q)] for p, q, *_ in r.get("asks", [])],
        }

    def get_ticker(self, symbol: str) -> dict:
        sym = self.to_exchange_symbol(symbol)
        data = self._get(f"{BASE}/api/v5/market/ticker", {"instId": sym})
        if not data or data.get("code") != "0" or not data.get("data"):
            return {"last": 0.0, "quote_volume_24h": 0.0, "price_change_pct_24h": 0.0}
        r = data["data"][0]
        last = float(r.get("last", 0))
        open24h = float(r.get("open24h", 0)) or last
        chg_pct = ((last - open24h) / open24h * 100) if open24h else 0.0
        return {
            "last": last,
            "quote_volume_24h": float(r.get("volCcy24h", 0)),
            "price_change_pct_24h": chg_pct,
        }

    def get_funding_rate(self, symbol: str) -> dict | None:
        sym = self._swap_symbol(symbol)
        data = self._get(f"{BASE}/api/v5/public/funding-rate", {"instId": sym})
        if not data or data.get("code") != "0" or not data.get("data"):
            return None
        r = data["data"][0]
        return {
            "funding_rate": float(r.get("fundingRate", 0)),
            "next_funding_ts": int(r.get("nextFundingTime", 0)) or None,
        }

    def get_open_interest(self, symbol: str) -> dict | None:
        sym = self._swap_symbol(symbol)
        data = self._get(f"{BASE}/api/v5/public/open-interest", {"instId": sym})
        if not data or data.get("code") != "0" or not data.get("data"):
            return None
        r = data["data"][0]
        return {"oi": float(r.get("oi", 0)), "oi_in_usdt": float(r.get("oiCcy", 0)) or None}

    def get_long_short_ratio(self, symbol: str) -> dict | None:
        base = symbol.split("/")[0]
        data = self._get(f"{BASE}/api/v5/rubik-stat/contracts/long-short-account-ratio",
                          {"ccy": base, "period": "5m"})
        if not data or data.get("code") != "0" or not data.get("data"):
            return None
        row = data["data"][-1]
        ratio = float(row[1])  # OKX trả 1 tỷ lệ long/short duy nhất, không tách 2 số
        return {"long_ratio": ratio, "short_ratio": 1 / ratio if ratio else 0}
