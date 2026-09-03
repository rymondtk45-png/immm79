# -*- coding: utf-8 -*-
"""
15 model tín hiệu, chỉ dùng data lấy từ sàn (klines, orderbook, ticker, funding, OI).
Mỗi hàm nhận `data_per_exchange` = { exchange_name: {klines, orderbook, ticker, funding, oi, long_short, ok} }
của MỘT symbol, trả về điểm số signed float, quy ước:
    > 0  => thiên hướng PUMP (tăng)
    < 0  => thiên hướng DUMP (giảm)
    độ lớn ~ -100..100, càng xa 0 càng mạnh.

Đây là MVP heuristic — dùng để rank/lọc coin đáng chú ý, KHÔNG phải công thức
đã backtest học thuật. Cần tự kiểm định lại bằng dữ liệu lịch sử trước khi tin tưởng 100%.
"""
from __future__ import annotations
import math
import numpy as np
import pandas as pd


def _ok_exchanges(data: dict) -> dict:
    return {k: v for k, v in data.items() if v.get("ok") and v.get("klines")}


def _klines_df(ex_data: dict) -> pd.DataFrame | None:
    kl = ex_data.get("klines") or []
    if len(kl) < 10:
        return None
    df = pd.DataFrame(kl)
    df = df.sort_values("ts").reset_index(drop=True)
    return df


def _clip(x: float, lo: float = -100, hi: float = 100) -> float:
    return float(max(lo, min(hi, x)))


# ================= NHÓM ORDER FLOW (per-exchange, lấy trung bình) =================

def orderbook_imbalance(data: dict) -> float:
    """(1) Tổng khối lượng bid vs ask ở top N mức giá."""
    vals = []
    for ex, d in _ok_exchanges(data).items():
        ob = d.get("orderbook", {})
        bids, asks = ob.get("bids", []), ob.get("asks", [])
        if not bids or not asks:
            continue
        bid_vol = sum(q for _, q in bids)
        ask_vol = sum(q for _, q in asks)
        total = bid_vol + ask_vol
        if total <= 0:
            continue
        vals.append((bid_vol - ask_vol) / total)
    if not vals:
        return 0.0
    return _clip(float(np.mean(vals)) * 150)


def cvd_approx(data: dict) -> float:
    """
    (2) CVD (Cumulative Volume Delta).
    ƯU TIÊN data thật từ WebSocket (ws_trades: buy_vol/sell_vol từng lệnh khớp thật).
    Sàn nào không có ws_trades (WS lỗi/không hỗ trợ) sẽ tự rơi về proxy cũ:
    close>open tính là buy volume, ngược lại sell (suy ra từ nến, kém chính xác hơn).
    """
    vals = []
    for ex, d in data.items():
        ws = d.get("ws_trades")
        if ws and (ws["buy_vol"] + ws["sell_vol"]) > 0:
            total = ws["buy_vol"] + ws["sell_vol"]
            vals.append((ws["buy_vol"] - ws["sell_vol"]) / total)
            continue
        if not d.get("ok"):
            continue
        df = _klines_df(d)
        if df is None:
            continue
        direction = np.sign(df["close"] - df["open"])
        delta = direction * df["volume"]
        cvd = delta.cumsum()
        if len(cvd) < 10:
            continue
        # độ dốc CVD ở 20% nến gần nhất so với biên độ toàn kỳ
        recent = cvd.iloc[-max(5, len(cvd) // 5):]
        span = cvd.max() - cvd.min()
        if span <= 0:
            continue
        slope_norm = (recent.iloc[-1] - recent.iloc[0]) / span
        vals.append(slope_norm * 0.4)  # giảm trọng số vì đây là proxy kém chắc hơn data thật
    if not vals:
        return 0.0
    return _clip(float(np.mean(vals)) * 100)


def volume_zscore(data: dict) -> float:
    """(3) Volume nến gần nhất lệch bao nhiêu độ lệch chuẩn so với baseline; hướng theo giá."""
    vals = []
    for ex, d in _ok_exchanges(data).items():
        df = _klines_df(d)
        if df is None or len(df) < 20:
            continue
        vol = df["volume"]
        mean, std = vol[:-1].mean(), vol[:-1].std()
        if std == 0 or math.isnan(std):
            continue
        z = (vol.iloc[-1] - mean) / std
        price_dir = np.sign(df["close"].iloc[-1] - df["open"].iloc[-1])
        vals.append(z * (price_dir if price_dir != 0 else 1))
    if not vals:
        return 0.0
    return _clip(float(np.mean(vals)) * 12)


def vwap_deviation(data: dict) -> float:
    """(4) Giá hiện tại lệch bao nhiêu % so với VWAP của cửa sổ nến."""
    vals = []
    for ex, d in _ok_exchanges(data).items():
        df = _klines_df(d)
        if df is None:
            continue
        typical = (df["high"] + df["low"] + df["close"]) / 3
        vwap = (typical * df["volume"]).sum() / max(df["volume"].sum(), 1e-9)
        last = df["close"].iloc[-1]
        if vwap <= 0:
            continue
        dev_pct = (last - vwap) / vwap * 100
        vals.append(dev_pct)
    if not vals:
        return 0.0
    return _clip(float(np.mean(vals)) * 15)


def spread_depth_compression(data: dict) -> float:
    """(5) Spread hẹp bất thường (tương đối) -> thị trường "nén", sắp bung theo hướng CVD."""
    spreads = []
    for ex, d in _ok_exchanges(data).items():
        ob = d.get("orderbook", {})
        bids, asks = ob.get("bids", []), ob.get("asks", [])
        if not bids or not asks:
            continue
        best_bid, best_ask = bids[0][0], asks[0][0]
        mid = (best_bid + best_ask) / 2
        if mid <= 0:
            continue
        spread_bps = (best_ask - best_bid) / mid * 10000
        spreads.append(spread_bps)
    if not spreads:
        return 0.0
    avg_spread = float(np.mean(spreads))
    # spread càng hẹp -> điểm "sẵn sàng bung" càng cao (0-100), chưa có hướng
    compression_score = _clip(100 - avg_spread * 20, 0, 100)
    direction = np.sign(cvd_approx(data)) or 1
    return _clip(compression_score * direction * 0.6)


def large_trade_tape(data: dict) -> float:
    """(6) Proxy cho lệnh khủng: nến đơn lẻ có volume vọt cao bất thường + biên độ giá lớn."""
    vals = []
    for ex, d in _ok_exchanges(data).items():
        df = _klines_df(d)
        if df is None or len(df) < 20:
            continue
        vol = df["volume"]
        body = (df["close"] - df["open"]).abs()
        vol_z = (vol.iloc[-1] - vol[:-1].mean()) / (vol[:-1].std() + 1e-9)
        body_z = (body.iloc[-1] - body[:-1].mean()) / (body[:-1].std() + 1e-9)
        if vol_z > 2.5 and body_z > 1.0:
            direction = np.sign(df["close"].iloc[-1] - df["open"].iloc[-1])
            vals.append(direction * min(vol_z, 10))
    if not vals:
        return 0.0
    return _clip(float(np.mean(vals)) * 8)


def taker_ratio_extreme(data: dict) -> float:
    """
    (7) Tỷ lệ taker mua/bán thật.
    ƯU TIÊN ws_trades (buy_vol/sell_vol từng lệnh khớp thật, chính xác tuyệt đối).
    Fallback: xấp xỉ qua tỷ trọng volume nến tăng/giảm trong cửa sổ gần (kém chính xác hơn).
    """
    vals = []
    for ex, d in data.items():
        ws = d.get("ws_trades")
        if ws and (ws["buy_vol"] + ws["sell_vol"]) > 0:
            total = ws["buy_vol"] + ws["sell_vol"]
            vals.append((ws["buy_vol"] - ws["sell_vol"]) / total)
            continue
        if not d.get("ok"):
            continue
        df = _klines_df(d)
        if df is None:
            continue
        window = df.tail(20)
        up_vol = window.loc[window["close"] > window["open"], "volume"].sum()
        down_vol = window.loc[window["close"] < window["open"], "volume"].sum()
        total = up_vol + down_vol
        if total <= 0:
            continue
        ratio = (up_vol - down_vol) / total
        vals.append(ratio * 0.6)  # giảm trọng số vì là proxy, kém chắc hơn data thật
    if not vals:
        return 0.0
    return _clip(float(np.mean(vals)) * 90)


# ================= NHÓM CROSS-EXCHANGE (trọng số cao nhất) =================

def cross_exchange_volume_surge(data: dict) -> float:
    """(8) Bao nhiêu sàn cùng lúc có volume vọt -> pump thật; chỉ 1 sàn -> nghi wash trading."""
    ok = _ok_exchanges(data)
    if len(ok) < 2:
        return 0.0
    surge_flags = []
    directions = []
    for ex, d in ok.items():
        df = _klines_df(d)
        if df is None or len(df) < 20:
            continue
        vol = df["volume"]
        mean, std = vol[:-1].mean(), vol[:-1].std()
        if std == 0 or math.isnan(std):
            continue
        z = (vol.iloc[-1] - mean) / std
        surge_flags.append(1 if z > 2.0 else 0)
        directions.append(np.sign(df["close"].iloc[-1] - df["open"].iloc[-1]))
    if not surge_flags:
        return 0.0
    n_total = len(surge_flags)
    n_surge = sum(surge_flags)
    agreement = n_surge / n_total  # tỷ lệ sàn xác nhận surge đồng thời
    direction = np.sign(sum(directions)) or 1
    # agreement thấp (chỉ 1 sàn) sẽ bị giảm điểm mạnh -> phản ánh nghi ngờ wash trading
    return _clip(agreement * agreement * 100 * direction)


def cross_exchange_price_divergence(data: dict) -> float:
    """(9) Độ lệch giá % giữa các sàn trong window gần nhất -> sàn nào dẫn giá."""
    ok = _ok_exchanges(data)
    if len(ok) < 2:
        return 0.0
    pct_changes = []
    for ex, d in ok.items():
        df = _klines_df(d)
        if df is None or len(df) < 5:
            continue
        recent = df.tail(5)
        chg = (recent["close"].iloc[-1] - recent["close"].iloc[0]) / recent["close"].iloc[0] * 100
        pct_changes.append(chg)
    if len(pct_changes) < 2:
        return 0.0
    mean_chg = float(np.mean(pct_changes))
    std_chg = float(np.std(pct_changes))
    # divergence cao = độ tin cậy tín hiệu thấp hơn -> giảm biên độ, giữ hướng theo mean
    confidence = _clip(100 - std_chg * 40, 10, 100) / 100
    return _clip(mean_chg * 10 * confidence)


def cross_exchange_ob_imbalance(data: dict) -> float:
    """(10) Order book imbalance tổng hợp có trọng số theo thanh khoản (quote volume 24h) từng sàn."""
    ok = _ok_exchanges(data)
    if not ok:
        return 0.0
    weighted_sum, weight_total = 0.0, 0.0
    for ex, d in ok.items():
        ob = d.get("orderbook", {})
        bids, asks = ob.get("bids", []), ob.get("asks", [])
        if not bids or not asks:
            continue
        bid_vol = sum(q for _, q in bids)
        ask_vol = sum(q for _, q in asks)
        total = bid_vol + ask_vol
        if total <= 0:
            continue
        imbalance = (bid_vol - ask_vol) / total
        weight = max(d.get("ticker", {}).get("quote_volume_24h", 0.0), 1.0)
        weighted_sum += imbalance * weight
        weight_total += weight
    if weight_total <= 0:
        return 0.0
    return _clip((weighted_sum / weight_total) * 150)


# ================= NHÓM FUTURES (Binance/Bybit/OKX chuẩn nhất) =================

def funding_oi_divergence(data: dict) -> float:
    """(11) Funding thấp/âm nhưng OI tăng -> khả năng short squeeze. Funding cao + OI tăng -> long trap risk."""
    fundings, ois_ok = [], 0
    for ex, d in data.items():
        f = d.get("funding")
        if f and f.get("funding_rate") is not None:
            fundings.append(f["funding_rate"])
        if d.get("oi"):
            ois_ok += 1
    if not fundings or ois_ok == 0:
        return 0.0
    avg_funding = float(np.mean(fundings)) * 100  # về %
    # funding âm mạnh = short đang trả phí cho long -> áp lực short squeeze -> điểm dương (pump bias)
    # funding dương mạnh = long đang trả phí -> quá tải long -> điểm âm (dump bias, dễ bị xả)
    return _clip(-avg_funding * 40)


def long_short_ratio_extreme(data: dict) -> float:
    """(12) Long/short account ratio cực đoan -> tín hiệu contrarian (đám đông sai nhiều)."""
    ratios = []
    for ex, d in data.items():
        ls = d.get("long_short")
        if ls and ls.get("long_ratio") and ls.get("short_ratio"):
            lr, sr = ls["long_ratio"], ls["short_ratio"]
            if sr > 0:
                ratios.append(lr / sr)
    if not ratios:
        return 0.0
    avg_ratio = float(np.mean(ratios))
    # ratio > 1 nghiêng long, < 1 nghiêng short. Contrarian: long quá đông -> điểm âm (rủi ro dump)
    log_ratio = math.log(max(avg_ratio, 1e-6))
    return _clip(-log_ratio * 35)


def basis_spread(data: dict) -> float:
    """(13) Chênh lệch giá spot vs futures (basis) — basis dương lớn bất thường = FOMO, dễ điều chỉnh."""
    spot_prices, has_funding = [], False
    for ex, d in data.items():
        last = d.get("ticker", {}).get("last", 0)
        if last:
            spot_prices.append(last)
        if d.get("funding"):
            has_funding = True
    if not spot_prices or not has_funding:
        return 0.0
    # Không có giá futures riêng biệt trong MVP này -> dùng funding rate trung bình làm proxy basis
    fundings = [d["funding"]["funding_rate"] for d in data.values()
                if d.get("funding") and d["funding"].get("funding_rate") is not None]
    if not fundings:
        return 0.0
    avg_funding_pct = float(np.mean(fundings)) * 100
    # basis/funding dương cao bất thường -> điểm âm (rủi ro điều chỉnh giảm)
    return _clip(-avg_funding_pct * 25)


def oi_surge_price_flat(data: dict) -> float:
    """(14) OI hiện tại lớn so với volume 24h (proxy tích luỹ đòn bẩy) trong khi giá gần như đi ngang."""
    scores = []
    for ex, d in data.items():
        oi = d.get("oi")
        ticker = d.get("ticker", {})
        if not oi or not ticker:
            continue
        oi_val = oi.get("oi", 0)
        qvol = ticker.get("quote_volume_24h", 0)
        price_chg = abs(ticker.get("price_change_pct_24h", 0))
        if qvol <= 0 or oi_val <= 0:
            continue
        oi_to_vol = oi_val / qvol  # tỷ lệ tương đối (đơn vị khác nhau nhưng vẫn có ý nghĩa so sánh)
        if price_chg < 1.5:  # giá gần như đi ngang trong 24h
            scores.append(oi_to_vol)
    if not scores:
        return 0.0
    intensity = _clip(float(np.mean(scores)) * 500, 0, 100)
    # OI tích luỹ khi giá flat: chưa rõ hướng -> lấy hướng nhẹ theo CVD để không luôn = 0
    direction = np.sign(cvd_approx(data)) or 1
    return _clip(intensity * 0.5 * direction)


def liquidation_cluster_estimate(data: dict) -> float:
    """
    (15) Thanh lý thật (ws_liq: Binance/Bybit/OKX forceOrder/liquidation feed).
    Short bị thanh lý nhiều hơn Long -> áp lực mua cưỡng bức -> thiên hướng PUMP (điểm dương).
    Long bị thanh lý nhiều hơn Short -> áp lực bán cưỡng bức -> thiên hướng DUMP (điểm âm).
    Fallback (không sàn nào có ws_liq): ước lượng qua biến động return đột biến gần đây.
    """
    liq_vals = []
    for ex, d in data.items():
        liq = d.get("ws_liq")
        if not liq:
            continue
        total = liq["long_liq_notional"] + liq["short_liq_notional"]
        if total <= 0:
            continue
        net = (liq["short_liq_notional"] - liq["long_liq_notional"]) / total
        liq_vals.append(net)

    if liq_vals:
        return _clip(float(np.mean(liq_vals)) * 100)

    # ---- Fallback proxy (không có data thanh lý thật cho coin này) ----
    vals = []
    for ex, d in data.items():
        df = _klines_df(d)
        if df is None or len(df) < 15:
            continue
        ret = df["close"].pct_change().dropna()
        if len(ret) < 10:
            continue
        recent_vol = ret.tail(3).std()
        base_vol = ret.iloc[:-3].std()
        if base_vol == 0 or math.isnan(base_vol):
            continue
        vol_ratio = recent_vol / base_vol
        if vol_ratio > 1.8:
            direction = np.sign(df["close"].iloc[-1] - df["close"].iloc[-4])
            vals.append(direction * min(vol_ratio, 6))
    if not vals:
        return 0.0
    return _clip(float(np.mean(vals)) * 12 * 0.5)  # giảm trọng số vì là proxy


# ================= DISPATCH TABLE =================

SIGNAL_FUNCS = {
    "orderbook_imbalance": orderbook_imbalance,
    "cvd_approx": cvd_approx,
    "volume_zscore": volume_zscore,
    "vwap_deviation": vwap_deviation,
    "spread_depth_compression": spread_depth_compression,
    "large_trade_tape": large_trade_tape,
    "taker_ratio_extreme": taker_ratio_extreme,
    "cross_exchange_volume_surge": cross_exchange_volume_surge,
    "cross_exchange_price_divergence": cross_exchange_price_divergence,
    "cross_exchange_ob_imbalance": cross_exchange_ob_imbalance,
    "funding_oi_divergence": funding_oi_divergence,
    "long_short_ratio_extreme": long_short_ratio_extreme,
    "basis_spread": basis_spread,
    "oi_surge_price_flat": oi_surge_price_flat,
    "liquidation_cluster_estimate": liquidation_cluster_estimate,
}


def compute_all_signals(data_per_exchange: dict) -> dict:
    """Chạy toàn bộ 15 model cho 1 symbol, trả về {signal_name: score}."""
    scores = {}
    for name, func in SIGNAL_FUNCS.items():
        try:
            scores[name] = func(data_per_exchange)
        except Exception as e:  # noqa: BLE001
            print(f"Signal '{name}' lỗi: {e}")
            scores[name] = 0.0
    return scores
