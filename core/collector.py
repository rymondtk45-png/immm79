# -*- coding: utf-8 -*-
"""
Thu thập data song song từ nhiều sàn cho danh sách coin.
Lỗi ở 1 sàn/1 coin không làm sập cả pipeline — chỉ log và bỏ qua sàn đó cho coin đó.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed

import config
from exchanges import ADAPTER_REGISTRY
from core.ws_collector import collect_ws_all_sync


def _fetch_one(exchange_name: str, adapter, symbol: str) -> dict:
    """Lấy toàn bộ data cần thiết từ 1 sàn cho 1 symbol."""
    out = {
        "klines": [], "orderbook": {"bids": [], "asks": []},
        "ticker": {"last": 0.0, "quote_volume_24h": 0.0, "price_change_pct_24h": 0.0},
        "funding": None, "oi": None, "long_short": None, "ok": False,
    }
    try:
        out["klines"] = adapter.get_klines(symbol, config.KLINE_INTERVAL, config.KLINE_LIMIT)
        out["orderbook"] = adapter.get_orderbook(symbol, config.ORDERBOOK_DEPTH)
        out["ticker"] = adapter.get_ticker(symbol)
        out["funding"] = adapter.get_funding_rate(symbol)
        out["oi"] = adapter.get_open_interest(symbol)
        out["long_short"] = adapter.get_long_short_ratio(symbol)
        out["ok"] = bool(out["klines"])  # coi như "có data" nếu lấy được nến
    except Exception as e:  # noqa: BLE001
        print(f"[{exchange_name}] lỗi khi lấy {symbol}: {e}")
    return out


def collect_all(symbols: list[str]) -> dict:
    """
    Trả về: { symbol: { exchange_name: {klines, orderbook, ticker, funding, oi, long_short, ok} } }
    """
    adapters = {
        name: cls() for name, cls in ADAPTER_REGISTRY.items()
        if config.ENABLED_EXCHANGES.get(name, False)
    }

    result = {s: {} for s in symbols}
    jobs = [(s, ex_name, ad) for s in symbols for ex_name, ad in adapters.items()]

    with ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as pool:
        futures = {
            pool.submit(_fetch_one, ex_name, ad, s): (s, ex_name)
            for s, ex_name, ad in jobs
        }
        for fut in as_completed(futures):
            s, ex_name = futures[fut]
            try:
                result[s][ex_name] = fut.result()
            except Exception as e:  # noqa: BLE001
                print(f"[{ex_name}] job lỗi cho {s}: {e}")
                result[s][ex_name] = {"ok": False}

    # ---- Real-time WebSocket layer (CVD/taker ratio/liquidation dùng data thật) ----
    if config.WS_ENABLED:
        print(f"==> Lắng nghe WebSocket real-time trong {config.WS_WINDOW_SEC}s "
              f"(trade{'+liquidation' if config.WS_LIQUIDATION_ENABLED else ''})...")
        ws_data = collect_ws_all_sync(symbols)
        for s in symbols:
            for ex_name in result.get(s, {}):
                extra = ws_data.get(s, {}).get(ex_name, {})
                result[s][ex_name]["ws_trades"] = extra.get("ws_trades")
                result[s][ex_name]["ws_liq"] = extra.get("ws_liq")

    return result
