# -*- coding: utf-8 -*-
"""
Cấu hình trung tâm cho hệ thống tín hiệu multi-exchange.
Chỉnh ở đây, không cần sửa code logic.
"""

# Danh sách coin cần quét (dùng symbol chuẩn kiểu BASE/QUOTE, hệ thống tự map sang format từng sàn)
SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    "DOGE/USDT", "ADA/USDT", "AVAX/USDT", "LINK/USDT", "SUI/USDT",
    "TON/USDT", "TRX/USDT", "APT/USDT", "ARB/USDT", "OP/USDT",
    "NEAR/USDT", "INJ/USDT", "SEI/USDT", "TIA/USDT", "WIF/USDT",
]

# Sàn nào bật/tắt (để tắt nhanh 1 sàn nếu bị rate-limit/lỗi mạng khi chạy thật)
ENABLED_EXCHANGES = {
    "binance": True,
    "bybit": True,
    "okx": True,
    "bitget": True,
    "kucoin": True,
    "mxc": True,
}

# Khung thời gian nến dùng để tính signal
KLINE_INTERVAL = "5m"
KLINE_LIMIT = 100          # số nến lấy về (dùng để tính baseline/zscore)

ORDERBOOK_DEPTH = 50        # số mức giá lấy từ order book mỗi sàn

# Timeout & retry cho HTTP request tới từng sàn
HTTP_TIMEOUT_SEC = 8
HTTP_RETRY = 2

# Số luồng chạy song song (fetch nhiều coin/sàn cùng lúc để đỡ chậm)
MAX_WORKERS = 12

# ==== WebSocket real-time (nâng cấp CVD / Taker Ratio / Liquidation lên data thật) ====
# Bật/tắt tổng: nếu False, hệ thống chạy hoàn toàn bằng REST + công thức proxy như bản trước.
WS_ENABLED = True
# Bật/tắt riêng liquidation stream (nặng hơn, không phải sàn nào cũng có public feed ổn định)
WS_LIQUIDATION_ENABLED = True
# Thời gian (giây) lắng nghe trade/liquidation stream trước khi tính signal.
# Cao hơn = data thật chính xác hơn nhưng chạy lâu hơn. 15-30s là hợp lý cho MVP.
WS_WINDOW_SEC = 20
# Timeout kết nối WebSocket ban đầu (giây)
WS_CONNECT_TIMEOUT_SEC = 8

# ==== Trọng số các nhóm signal khi tính điểm tổng (0-1, tổng không bắt buộc =1) ====
SIGNAL_WEIGHTS = {
    # Order flow (per-exchange, lấy trung bình/đồng thuận giữa các sàn)
    "orderbook_imbalance": 1.0,
    "cvd_approx": 1.0,
    "volume_zscore": 1.2,
    "vwap_deviation": 0.8,
    "spread_depth_compression": 0.6,
    "large_trade_tape": 0.7,          # best-effort, dùng volume nến lớn bất thường làm proxy
    "taker_ratio_extreme": 1.0,

    # Cross-exchange (trọng số cao nhất vì khó fake)
    "cross_exchange_volume_surge": 1.8,
    "cross_exchange_price_divergence": 1.3,
    "cross_exchange_ob_imbalance": 1.5,

    # Futures (chỉ Binance/Bybit/OKX chuẩn nhất, các sàn khác best-effort)
    "funding_oi_divergence": 1.4,
    "long_short_ratio_extreme": 0.9,
    "basis_spread": 1.0,
    "oi_surge_price_flat": 1.3,
    "liquidation_cluster_estimate": 1.1,
}

# Ngưỡng để quyết định nhãn PUMP / DUMP / NEUTRAL trên điểm tổng đã chuẩn hoá (-100..100)
SCORE_THRESHOLD_PUMP = 35
SCORE_THRESHOLD_DUMP = -35

TOP_N_RESULTS = 15
