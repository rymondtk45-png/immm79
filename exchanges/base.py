# -*- coding: utf-8 -*-
"""
Interface chung cho mọi exchange adapter.

Mọi adapter phải trả về data ở format CHUẨN HOÁ (normalized) sau đây,
để core/signals.py không cần biết gì về từng sàn cụ thể:

Kline (list[dict]):
    {"ts": int(ms), "open": float, "high": float, "low": float,
     "close": float, "volume": float}

Orderbook (dict):
    {"bids": [[price, qty], ...], "asks": [[price, qty], ...]}

Ticker (dict):
    {"last": float, "quote_volume_24h": float, "price_change_pct_24h": float}

Funding (dict | None):
    {"funding_rate": float, "next_funding_ts": int | None}

OpenInterest (dict | None):
    {"oi": float, "oi_in_usdt": float | None}

LongShortRatio (dict | None):
    {"long_ratio": float, "short_ratio": float}
"""

from abc import ABC, abstractmethod
import time
import requests

import config


class ExchangeAdapter(ABC):
    name: str = "base"
    session: requests.Session

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "mvp-crypto-signals/1.0"})

    # ---------- HTTP helper dùng chung, có retry ----------
    def _get(self, url: str, params: dict | None = None) -> dict | list | None:
        last_err = None
        for attempt in range(config.HTTP_RETRY + 1):
            try:
                resp = self.session.get(
                    url, params=params, timeout=config.HTTP_TIMEOUT_SEC
                )
                if resp.status_code == 200:
                    return resp.json()
                last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
            except Exception as e:  # noqa: BLE001
                last_err = str(e)
            time.sleep(0.3 * (attempt + 1))
        # Không raise để 1 sàn lỗi không làm chết cả pipeline; caller tự check None
        print(f"[{self.name}] request lỗi: {url} -> {last_err}")
        return None

    # ---------- Symbol mapping: BASE/QUOTE chuẩn -> format riêng của sàn ----------
    @abstractmethod
    def to_exchange_symbol(self, symbol: str) -> str:
        ...

    # ---------- Bắt buộc mọi sàn phải có (spot) ----------
    @abstractmethod
    def get_klines(self, symbol: str, interval: str, limit: int) -> list[dict]:
        ...

    @abstractmethod
    def get_orderbook(self, symbol: str, depth: int) -> dict:
        ...

    @abstractmethod
    def get_ticker(self, symbol: str) -> dict:
        ...

    # ---------- Futures, best-effort, mặc định trả None nếu sàn không hỗ trợ/lỗi ----------
    def get_funding_rate(self, symbol: str) -> dict | None:
        return None

    def get_open_interest(self, symbol: str) -> dict | None:
        return None

    def get_long_short_ratio(self, symbol: str) -> dict | None:
        return None
