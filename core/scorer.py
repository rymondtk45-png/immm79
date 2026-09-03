# -*- coding: utf-8 -*-
import numpy as np
import config


def weighted_score(signal_scores: dict) -> float:
    """Gộp các signal (mỗi cái đã ở thang -100..100) thành 1 điểm tổng, có trọng số."""
    total_w = sum(config.SIGNAL_WEIGHTS.values())
    if total_w == 0:
        return 0.0
    s = 0.0
    for name, score in signal_scores.items():
        w = config.SIGNAL_WEIGHTS.get(name, 1.0)
        s += score * w
    return float(np.clip(s / total_w, -100, 100))


def confidence_score(data_per_exchange: dict) -> float:
    """
    Điểm tin cậy 0-100 dựa trên: có bao nhiêu sàn trả data OK cho symbol này.
    Coin chỉ có data từ 1-2 sàn -> độ tin cậy thấp, cần cẩn trọng hơn khi đọc tín hiệu.
    """
    total = len(config.ENABLED_EXCHANGES)
    ok = sum(1 for d in data_per_exchange.values() if d.get("ok"))
    if total == 0:
        return 0.0
    return round(ok / total * 100, 1)


def label_from_score(score: float) -> str:
    if score >= config.SCORE_THRESHOLD_PUMP:
        return "PUMP"
    if score <= config.SCORE_THRESHOLD_DUMP:
        return "DUMP"
    return "NEUTRAL"


def build_ranking(all_symbol_signals: dict, all_symbol_data: dict) -> list[dict]:
    """
    all_symbol_signals: {symbol: {signal_name: score}}
    all_symbol_data: {symbol: {exchange: {...}}}  (để tính confidence + hiển thị giá)
    """
    rows = []
    for symbol, signals in all_symbol_signals.items():
        score = weighted_score(signals)
        conf = confidence_score(all_symbol_data.get(symbol, {}))
        label = label_from_score(score)

        # Lấy giá & % thay đổi 24h trung bình các sàn có data để hiển thị
        prices, changes = [], []
        for ex, d in all_symbol_data.get(symbol, {}).items():
            t = d.get("ticker", {})
            if t.get("last"):
                prices.append(t["last"])
                changes.append(t.get("price_change_pct_24h", 0.0))

        rows.append({
            "symbol": symbol,
            "score": round(score, 1),
            "label": label,
            "confidence": conf,
            "avg_price": round(float(np.mean(prices)), 6) if prices else None,
            "avg_change_24h_pct": round(float(np.mean(changes)), 2) if changes else None,
            "signals": {k: round(v, 1) for k, v in signals.items()},
        })

    rows.sort(key=lambda r: abs(r["score"]) * (r["confidence"] / 100), reverse=True)
    return rows
