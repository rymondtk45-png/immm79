# -*- coding: utf-8 -*-
"""
MVP Crypto Multi-Exchange Signal Scanner
=========================================
Quét data spot + futures (best-effort) từ Binance, Bybit, OKX, Bitget, KuCoin, MEXC,
tính 15 model tín hiệu (order flow, cross-exchange, futures), gộp thành 1 điểm số
và xếp hạng coin nào đang có khả năng PUMP/DUMP cao nhất.

Chạy:
    pip install -r requirements.txt
    python main.py
    python main.py --symbols BTC/USDT,ETH/USDT --top 10
"""
import argparse
import json
import time
from datetime import datetime

from tabulate import tabulate

import config
from core.collector import collect_all
from core.signals import compute_all_signals
from core.scorer import build_ranking


def parse_args():
    p = argparse.ArgumentParser(description="MVP Crypto Multi-Exchange Signal Scanner")
    p.add_argument("--symbols", type=str, default=None,
                    help="Danh sách coin, cách nhau bởi dấu phẩy, vd: BTC/USDT,ETH/USDT")
    p.add_argument("--top", type=int, default=config.TOP_N_RESULTS,
                    help="Số coin hiển thị trong bảng xếp hạng")
    p.add_argument("--save", action="store_true",
                    help="Lưu kết quả đầy đủ ra output/result_<timestamp>.json")
    p.add_argument("--no-ws", action="store_true",
                    help="Tắt WebSocket real-time, chỉ dùng REST + proxy (chạy nhanh hơn)")
    p.add_argument("--ws-window", type=int, default=None,
                    help="Số giây lắng nghe WebSocket trước khi tính signal (mặc định trong config.py)")
    return p.parse_args()


def run():
    args = parse_args()
    symbols = args.symbols.split(",") if args.symbols else config.SYMBOLS
    symbols = [s.strip() for s in symbols if s.strip()]

    if args.no_ws:
        config.WS_ENABLED = False
    if args.ws_window is not None:
        config.WS_WINDOW_SEC = args.ws_window

    enabled = [k for k, v in config.ENABLED_EXCHANGES.items() if v]
    print(f"==> Quét {len(symbols)} coin trên {len(enabled)} sàn: {', '.join(enabled)}")
    print(f"==> Khung nến: {config.KLINE_INTERVAL}, độ sâu order book: {config.ORDERBOOK_DEPTH}")
    print(f"==> WebSocket real-time: {'BẬT (' + str(config.WS_WINDOW_SEC) + 's)' if config.WS_ENABLED else 'TẮT'}")

    t0 = time.time()
    all_data = collect_all(symbols)
    print(f"==> Lấy data xong trong {time.time() - t0:.1f}s")

    all_signals = {s: compute_all_signals(all_data.get(s, {})) for s in symbols}
    ranking = build_ranking(all_signals, all_data)

    print_table(ranking[: args.top])

    if args.save:
        save_result(ranking)


def print_table(rows: list[dict]):
    table = []
    for r in rows:
        table.append([
            r["symbol"],
            r["label"],
            r["score"],
            f'{r["confidence"]}%',
            r["avg_price"],
            f'{r["avg_change_24h_pct"]}%' if r["avg_change_24h_pct"] is not None else "-",
        ])
    headers = ["Coin", "Nhãn", "Điểm (-100..100)", "Độ tin cậy", "Giá TB", "%24h TB"]
    print("\n" + tabulate(table, headers=headers, tablefmt="github"))
    print(
        "\nGhi chú: Điểm >= "
        f"{config.SCORE_THRESHOLD_PUMP} => thiên hướng PUMP | "
        f"Điểm <= {config.SCORE_THRESHOLD_DUMP} => thiên hướng DUMP | "
        "còn lại NEUTRAL.\n"
        "Đây là MVP heuristic, KHÔNG phải lời khuyên đầu tư — tự backtest/kiểm chứng "
        "trước khi dùng để vào lệnh thật."
    )


def save_result(rows: list[dict]):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"output/result_{ts}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print(f"\n==> Đã lưu chi tiết đầy đủ (kể cả breakdown từng signal) tại: {path}")


if __name__ == "__main__":
    run()
