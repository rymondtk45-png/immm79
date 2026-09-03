# -*- coding: utf-8 -*-
"""
Thu thập data REAL-TIME qua WebSocket, thay cho việc ước lượng CVD/Taker Ratio/Liquidation
từ nến (REST) như bản trước. Chạy trong 1 cửa sổ thời gian (config.WS_WINDOW_SEC), gom toàn
bộ trade/liquidation event thật, rồi trả về số liệu tổng hợp cho mỗi (symbol, exchange).

QUAN TRỌNG:
- Mọi URL/format message dưới đây viết theo tài liệu API tại thời điểm biên soạn, CHƯA test
  được với mạng thật (môi trường sandbox không có internet). Khi chạy thật, theo dõi log
  "[ws:<sàn>] lỗi ..." — sàn nào lỗi sẽ tự rơi về công thức proxy cũ trong core/signals.py,
  không làm hỏng cả pipeline.
- Liquidation stream: chỉ Binance, Bybit, OKX có public feed đủ ổn định để implement tin cậy.
  Bitget/KuCoin/MEXC hiện chưa có endpoint liquidation public được xác nhận chắc chắn -> trả
  None, signal #15 sẽ tự dùng lại proxy cho các sàn này.

Kết quả trả về (collect_ws_all):
    { symbol: { exchange: {"ws_trades": {"buy_vol": f, "sell_vol": f, "count": i} | None,
                            "ws_liq": {"long_liq_notional": f, "short_liq_notional": f, "count": i} | None } } }
"""
from __future__ import annotations
import asyncio
import json
import time

import config

try:
    import websockets
except ImportError:  # pragma: no cover
    websockets = None


def _empty_trade_acc() -> dict:
    return {"buy_vol": 0.0, "sell_vol": 0.0, "count": 0}


def _empty_liq_acc() -> dict:
    return {"long_liq_notional": 0.0, "short_liq_notional": 0.0, "count": 0}


async def _listen(url: str, subscribe_msg: dict | None, on_message, window_sec: float,
                   tag: str, ping_interval: float | None = None):
    """Kết nối WS, gửi subscribe (nếu có), đọc message tới khi hết `window_sec`."""
    if websockets is None:
        print(f"[ws:{tag}] thư viện 'websockets' chưa cài — bỏ qua real-time, dùng proxy REST.")
        return
    deadline = time.time() + window_sec
    try:
        async with websockets.connect(
            url, open_timeout=config.WS_CONNECT_TIMEOUT_SEC, ping_interval=ping_interval
        ) as ws:
            if subscribe_msg is not None:
                await ws.send(json.dumps(subscribe_msg))
            while time.time() < deadline:
                remaining = max(0.1, deadline - time.time())
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
                except asyncio.TimeoutError:
                    break
                try:
                    msg = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    continue
                try:
                    on_message(msg)
                except Exception as e:  # noqa: BLE001
                    print(f"[ws:{tag}] lỗi parse message: {e}")
    except Exception as e:  # noqa: BLE001
        print(f"[ws:{tag}] lỗi kết nối: {e}")


# ========================= BINANCE =========================

async def _binance_trades(symbols: list[str], window_sec: float) -> dict:
    acc = {s: _empty_trade_acc() for s in symbols}
    sym_map = {f"{s.split('/')[0]}{s.split('/')[1]}".lower(): s for s in symbols}
    streams = "/".join(f"{k}@aggTrade" for k in sym_map)
    url = f"wss://stream.binance.com:9443/stream?streams={streams}"

    def on_msg(msg):
        data = msg.get("data", {})
        stream = msg.get("stream", "")
        raw_sym = stream.split("@")[0]
        symbol = sym_map.get(raw_sym)
        if not symbol or "q" not in data:
            return
        qty = float(data["q"])
        is_buyer_maker = data.get("m", False)  # True = taker là bên BÁN
        if is_buyer_maker:
            acc[symbol]["sell_vol"] += qty
        else:
            acc[symbol]["buy_vol"] += qty
        acc[symbol]["count"] += 1

    await _listen(url, None, on_msg, window_sec, "binance-trades")
    return acc


async def _binance_liquidations(symbols: list[str], window_sec: float) -> dict:
    acc = {s: _empty_liq_acc() for s in symbols}
    sym_lookup = {f"{s.split('/')[0]}{s.split('/')[1]}": s for s in symbols}
    url = "wss://fstream.binance.com/ws/!forceOrder@arr"

    def on_msg(msg):
        o = msg.get("o", {})
        raw_sym = o.get("s")
        symbol = sym_lookup.get(raw_sym)
        if not symbol:
            return
        qty = float(o.get("q", 0))
        price = float(o.get("p", 0))
        notional = qty * price
        side = o.get("S")  # SELL = lệnh thanh lý bán = LONG bị thanh lý; BUY = SHORT bị thanh lý
        if side == "SELL":
            acc[symbol]["long_liq_notional"] += notional
        elif side == "BUY":
            acc[symbol]["short_liq_notional"] += notional
        acc[symbol]["count"] += 1

    await _listen(url, None, on_msg, window_sec, "binance-liq")
    return acc


# ========================= BYBIT =========================

async def _bybit_trades(symbols: list[str], window_sec: float) -> dict:
    acc = {s: _empty_trade_acc() for s in symbols}
    sym_map = {f"{s.split('/')[0]}{s.split('/')[1]}": s for s in symbols}
    url = "wss://stream.bybit.com/v5/public/spot"
    sub = {"op": "subscribe", "args": [f"publicTrade.{k}" for k in sym_map]}

    def on_msg(msg):
        topic = msg.get("topic", "")
        if not topic.startswith("publicTrade."):
            return
        raw_sym = topic.split(".", 1)[1]
        symbol = sym_map.get(raw_sym)
        if not symbol:
            return
        for row in msg.get("data", []):
            qty = float(row.get("v", 0))
            side = row.get("S")  # "Buy" | "Sell"
            if side == "Buy":
                acc[symbol]["buy_vol"] += qty
            elif side == "Sell":
                acc[symbol]["sell_vol"] += qty
            acc[symbol]["count"] += 1

    await _listen(url, sub, on_msg, window_sec, "bybit-trades", ping_interval=15)
    return acc


async def _bybit_liquidations(symbols: list[str], window_sec: float) -> dict:
    acc = {s: _empty_liq_acc() for s in symbols}
    sym_map = {f"{s.split('/')[0]}{s.split('/')[1]}": s for s in symbols}
    url = "wss://stream.bybit.com/v5/public/linear"
    sub = {"op": "subscribe", "args": [f"liquidation.{k}" for k in sym_map]}

    def on_msg(msg):
        topic = msg.get("topic", "")
        if not topic.startswith("liquidation."):
            return
        raw_sym = topic.split(".", 1)[1]
        symbol = sym_map.get(raw_sym)
        if not symbol:
            return
        row = msg.get("data", {})
        qty = float(row.get("size", 0))
        price = float(row.get("price", 0))
        notional = qty * price
        side = row.get("side")  # "Buy" = short bị thanh lý (forced buy) | "Sell" = long bị thanh lý
        if side == "Sell":
            acc[symbol]["long_liq_notional"] += notional
        elif side == "Buy":
            acc[symbol]["short_liq_notional"] += notional
        acc[symbol]["count"] += 1

    await _listen(url, sub, on_msg, window_sec, "bybit-liq", ping_interval=15)
    return acc


# ========================= OKX =========================

async def _okx_trades(symbols: list[str], window_sec: float) -> dict:
    acc = {s: _empty_trade_acc() for s in symbols}
    sym_map = {f"{s.split('/')[0]}-{s.split('/')[1]}": s for s in symbols}
    url = "wss://ws.okx.com:8443/ws/v5/public"
    sub = {"op": "subscribe", "args": [{"channel": "trades", "instId": k} for k in sym_map]}

    def on_msg(msg):
        arg = msg.get("arg", {})
        if arg.get("channel") != "trades":
            return
        raw_sym = arg.get("instId")
        symbol = sym_map.get(raw_sym)
        if not symbol:
            return
        for row in msg.get("data", []):
            qty = float(row.get("sz", 0))
            side = row.get("side")  # "buy" | "sell"
            if side == "buy":
                acc[symbol]["buy_vol"] += qty
            elif side == "sell":
                acc[symbol]["sell_vol"] += qty
            acc[symbol]["count"] += 1

    await _listen(url, sub, on_msg, window_sec, "okx-trades", ping_interval=15)
    return acc


async def _okx_liquidations(symbols: list[str], window_sec: float) -> dict:
    acc = {s: _empty_liq_acc() for s in symbols}
    sym_map = {f"{s.split('/')[0]}-{s.split('/')[1]}-SWAP": s for s in symbols}
    url = "wss://ws.okx.com:8443/ws/v5/public"
    # OKX liquidation-orders subscribe theo instType, trả về tất cả instrument thuộc loại đó
    sub = {"op": "subscribe", "args": [{"channel": "liquidation-orders", "instType": "SWAP"}]}

    def on_msg(msg):
        arg = msg.get("arg", {})
        if arg.get("channel") != "liquidation-orders":
            return
        for row in msg.get("data", []):
            raw_sym = row.get("instId")
            symbol = sym_map.get(raw_sym)
            if not symbol:
                continue
            for d in row.get("details", []):
                qty = float(d.get("sz", 0))
                price = float(d.get("bkPx", 0) or d.get("px", 0) or 0)
                notional = qty * price
                side = d.get("side")  # "buy" = short bị thanh lý | "sell" = long bị thanh lý
                if side == "sell":
                    acc[symbol]["long_liq_notional"] += notional
                elif side == "buy":
                    acc[symbol]["short_liq_notional"] += notional
                acc[symbol]["count"] += 1

    await _listen(url, sub, on_msg, window_sec, "okx-liq", ping_interval=15)
    return acc


# ========================= BITGET =========================

async def _bitget_trades(symbols: list[str], window_sec: float) -> dict:
    acc = {s: _empty_trade_acc() for s in symbols}
    sym_map = {f"{s.split('/')[0]}{s.split('/')[1]}": s for s in symbols}
    url = "wss://ws.bitget.com/v2/ws/public"
    sub = {"op": "subscribe",
           "args": [{"instType": "SPOT", "channel": "trade", "instId": k} for k in sym_map]}

    def on_msg(msg):
        arg = msg.get("arg", {})
        if arg.get("channel") != "trade":
            return
        raw_sym = arg.get("instId")
        symbol = sym_map.get(raw_sym)
        if not symbol:
            return
        for row in msg.get("data", []):
            qty = float(row.get("size", 0))
            side = row.get("side")  # "buy" | "sell"
            if side == "buy":
                acc[symbol]["buy_vol"] += qty
            elif side == "sell":
                acc[symbol]["sell_vol"] += qty
            acc[symbol]["count"] += 1

    await _listen(url, sub, on_msg, window_sec, "bitget-trades", ping_interval=20)
    return acc


# ========================= KUCOIN (cần lấy token trước khi connect) =========================

async def _kucoin_get_ws_endpoint():
    """KuCoin yêu cầu POST /bullet-public để lấy token + endpoint động trước khi mở WS."""
    import urllib.request

    try:
        req = urllib.request.Request(
            "https://api.kucoin.com/api/v1/bullet-public", method="POST"
        )
        with urllib.request.urlopen(req, timeout=config.WS_CONNECT_TIMEOUT_SEC) as resp:
            data = json.loads(resp.read().decode())
        token = data["data"]["token"]
        server = data["data"]["instanceServers"][0]
        endpoint = f'{server["endpoint"]}?token={token}&connectId=mvp{int(time.time())}'
        return endpoint
    except Exception as e:  # noqa: BLE001
        print(f"[ws:kucoin-trades] lỗi lấy bullet token: {e}")
        return None


async def _kucoin_trades(symbols: list[str], window_sec: float) -> dict:
    acc = {s: _empty_trade_acc() for s in symbols}
    sym_map = {f"{s.split('/')[0]}-{s.split('/')[1]}": s for s in symbols}

    url = await _kucoin_get_ws_endpoint()
    if not url:
        return acc
    topic = f'/market/match:{",".join(sym_map.keys())}'
    sub = {"id": str(int(time.time())), "type": "subscribe", "topic": topic,
           "privateChannel": False, "response": True}

    def on_msg(msg):
        if msg.get("type") != "message":
            return
        row = msg.get("data", {})
        raw_sym = row.get("symbol")
        symbol = sym_map.get(raw_sym)
        if not symbol:
            return
        qty = float(row.get("size", 0))
        side = row.get("side")  # "buy" | "sell"
        if side == "buy":
            acc[symbol]["buy_vol"] += qty
        elif side == "sell":
            acc[symbol]["sell_vol"] += qty
        acc[symbol]["count"] += 1

    await _listen(url, sub, on_msg, window_sec, "kucoin-trades", ping_interval=15)
    return acc


# ========================= MEXC =========================

async def _mxc_trades(symbols: list[str], window_sec: float) -> dict:
    acc = {s: _empty_trade_acc() for s in symbols}
    sym_map = {f"{s.split('/')[0]}{s.split('/')[1]}": s for s in symbols}
    url = "wss://wbs.mexc.com/ws"
    sub = {"method": "SUBSCRIPTION",
           "params": [f"spot@public.deals.v3.api@{k}" for k in sym_map]}

    def on_msg(msg):
        # LƯU Ý: MEXC v3 hiện chủ yếu đẩy data dạng protobuf nhị phân, không phải JSON thuần.
        # Nếu bản JSON dưới đây không nhận được data thật khi chạy live, cần thêm bước decode
        # protobuf (MEXC cung cấp .proto schema riêng) — ghi rõ trong README.
        d = msg.get("d", {})
        deals = d.get("deals", [])
        raw_sym = msg.get("s") or d.get("s")
        symbol = sym_map.get(raw_sym)
        if not symbol or not deals:
            return
        for row in deals:
            qty = float(row.get("v", 0))
            trade_type = row.get("S")  # 1 = buy, 2 = sell (theo tài liệu MEXC)
            if trade_type == 1:
                acc[symbol]["buy_vol"] += qty
            elif trade_type == 2:
                acc[symbol]["sell_vol"] += qty
            acc[symbol]["count"] += 1

    await _listen(url, sub, on_msg, window_sec, "mxc-trades", ping_interval=20)
    return acc


# ========================= DISPATCH =========================

_TRADE_COLLECTORS = {
    "binance": _binance_trades,
    "bybit": _bybit_trades,
    "okx": _okx_trades,
    "bitget": _bitget_trades,
    "kucoin": _kucoin_trades,
    "mxc": _mxc_trades,
}

# Chỉ 3 sàn có public liquidation feed đủ tin cậy để implement trong bản này.
_LIQ_COLLECTORS = {
    "binance": _binance_liquidations,
    "bybit": _bybit_liquidations,
    "okx": _okx_liquidations,
}


async def collect_ws_all(symbols: list[str]) -> dict:
    """
    Chạy TẤT CẢ trade-stream + liquidation-stream của các sàn đang bật, song song,
    trong cùng 1 cửa sổ config.WS_WINDOW_SEC. Trả về:
        { symbol: { exchange: {"ws_trades": {...}|None, "ws_liq": {...}|None} } }
    """
    if not config.WS_ENABLED or websockets is None:
        return {s: {} for s in symbols}

    tasks = {}
    for ex_name, fn in _TRADE_COLLECTORS.items():
        if config.ENABLED_EXCHANGES.get(ex_name, False):
            tasks[("trades", ex_name)] = asyncio.create_task(fn(symbols, config.WS_WINDOW_SEC))

    if config.WS_LIQUIDATION_ENABLED:
        for ex_name, fn in _LIQ_COLLECTORS.items():
            if config.ENABLED_EXCHANGES.get(ex_name, False):
                tasks[("liq", ex_name)] = asyncio.create_task(fn(symbols, config.WS_WINDOW_SEC))

    results = {}
    for key, task in tasks.items():
        try:
            results[key] = await task
        except Exception as e:  # noqa: BLE001
            kind, ex_name = key
            print(f"[ws:{ex_name}-{kind}] task lỗi: {e}")
            results[key] = {s: None for s in symbols}

    out = {s: {} for s in symbols}
    for s in symbols:
        for ex_name in config.ENABLED_EXCHANGES:
            trades = results.get(("trades", ex_name), {}).get(s)
            liq = results.get(("liq", ex_name), {}).get(s)
            trades_ok = trades if trades and trades.get("count", 0) > 0 else None
            liq_ok = liq if liq and liq.get("count", 0) > 0 else None
            out[s][ex_name] = {"ws_trades": trades_ok, "ws_liq": liq_ok}
    return out


def collect_ws_all_sync(symbols: list[str]) -> dict:
    """Wrapper đồng bộ để gọi từ core/collector.py (vốn chạy sync bằng ThreadPoolExecutor)."""
    try:
        return asyncio.run(collect_ws_all(symbols))
    except Exception as e:  # noqa: BLE001
        print(f"[ws] lỗi tổng quát khi thu thập real-time data: {e}")
        return {s: {} for s in symbols}
