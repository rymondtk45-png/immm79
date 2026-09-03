# -*- coding: utf-8 -*-
from .base import ExchangeAdapter

SPOT_BASE = "https://api.kucoin.com"
FUT_BASE = "https://api-futures.kucoin.com"

_TYPE_MAP = {"1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min",
             "1h": "1hour", "4h": "4hour", "1d": "1day"}

# KuCoin Futures dùng mã hợp đồng riêng, ví dụ BTC -> XBTUSDTM. Map thủ công vài coin phổ biến,
# coin nào không có trong map sẽ bỏ qua phần futures (spot vẫn chạy bình thường).
_FUTURES_SYMBOL_MAP = {
    "BTC": "XBTUSDTM", "ETH": "ETHUSDTM", "SOL": "SOLUSDTM", "BNB": "BNBUSDTM",
    "XRP": "XRPUSDTM", "DOGE": "DOGEUSDTM", "ADA": "ADAUSDTM", "AVAX": "AVAXUSDTM",
    "LINK": "LINKUSDTM", "SUI": "SUIUSDTM", "TON": "TONUSDTM", "TRX": "TRXUSDTM",
    "APT": "APTUSDTM", "ARB": "ARBUSDTM", "OP": "OPUSDTM", "NEAR": "NEARUSDTM",
    "INJ": "INJUSDTM", "SEI": "SEIUSDTM", "TIA": "TIAUSDTM", "WIF": "WIFUSDTM",
}


class KuCoinAdapter(ExchangeAdapter):
    name = "kucoin"

    def to_exchange_symbol(self, symbol: str) -> str:
        base, quote = symbol.split("/")
        return f"{base}-{quote}"

    def get_klines(self, symbol: str, interval: str = "5m", limit: int = 100) -> list[dict]:
        sym = self.to_exchange_symbol(symbol)
        typ = _TYPE_MAP.get(interval, "5min")
        data = self._get(f"{SPOT_BASE}/api/v1/market/candles", {"symbol": sym, "type": typ})
        if not data or data.get("code") != "200000":
            return []
        rows = list(reversed(data.get("data", [])))[-limit:]
        # KuCoin format: [time, open, close, high, low, volume, turnover]
        return [
            {"ts": int(r[0]) * 1000, "open": float(r[1]), "high": float(r[3]),
             "low": float(r[4]), "close": float(r[2]), "volume": float(r[5])}
            for r in rows
        ]

    def get_orderbook(self, symbol: str, depth: int = 50) -> dict:
        sym = self.to_exchange_symbol(symbol)
        data = self._get(f"{SPOT_BASE}/api/v1/market/orderbook/level2_20", {"symbol": sym})
        if not data or data.get("code") != "200000":
            return {"bids": [], "asks": []}
        r = data.get("data", {})
        return {
            "bids": [[float(p), float(q)] for p, q in r.get("bids", [])][:depth],
            "asks": [[float(p), float(q)] for p, q in r.get("asks", [])][:depth],
        }

    def get_ticker(self, symbol: str) -> dict:
        sym = self.to_exchange_symbol(symbol)
        data = self._get(f"{SPOT_BASE}/api/v1/market/stats", {"symbol": sym})
        if not data or data.get("code") != "200000":
            return {"last": 0.0, "quote_volume_24h": 0.0, "price_change_pct_24h": 0.0}
        r = data.get("data", {})
        return {
            "last": float(r.get("last", 0) or 0),
            "quote_volume_24h": float(r.get("volValue", 0) or 0),
            "price_change_pct_24h": float(r.get("changeRate", 0) or 0) * 100,
        }

    def get_funding_rate(self, symbol: str) -> dict | None:
        base = symbol.split("/")[0]
        contract = _FUTURES_SYMBOL_MAP.get(base)
        if not contract:
            return None
        data = self._get(f"{FUT_BASE}/api/v1/funding-rate/{contract}/current")
        if not data or data.get("code") != "200000" or not data.get("data"):
            return None
        r = data["data"]
        return {"funding_rate": float(r.get("value", 0)), "next_funding_ts": None}

    def get_open_interest(self, symbol: str) -> dict | None:
        base = symbol.split("/")[0]
        contract = _FUTURES_SYMBOL_MAP.get(base)
        if not contract:
            return None
        data = self._get(f"{FUT_BASE}/api/v1/contracts/{contract}")
        if not data or data.get("code") != "200000" or not data.get("data"):
            return None
        r = data["data"]
        return {"oi": float(r.get("openInterest", 0) or 0), "oi_in_usdt": None}
