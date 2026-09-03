# MVP Crypto Multi-Exchange Signal Scanner

Quét data **spot + futures (best-effort)** từ 6 sàn: **Binance, Bybit, OKX, Bitget, KuCoin, MEXC**,
tính 15 model tín hiệu chỉ dựa trên data sàn (không onchain), gộp thành 1 điểm số và xếp hạng
coin nào đang có khả năng **PUMP/DUMP** cao nhất.

## Cài đặt

```bash
pip install -r requirements.txt
```

## Chạy

```bash
python main.py                                   # quét toàn bộ SYMBOLS trong config.py
python main.py --symbols BTC/USDT,ETH/USDT,SOL/USDT --top 5
python main.py --save                             # lưu breakdown đầy đủ ra output/result_*.json
python main.py --no-ws                             # tắt WebSocket, chạy nhanh hơn (REST-only)
python main.py --telegram --loop 15                # bot cảnh báo tự động, quét lại mỗi 15 phút
```

## Cấu trúc project

```
config.py            <- sửa danh sách coin, bật/tắt sàn, trọng số signal ở đây
exchanges/            <- 1 adapter/sàn, tự chuẩn hoá data về format chung
  base.py
  binance.py bybit.py okx.py bitget.py kucoin.py mxc.py
core/
  collector.py        <- gọi song song tất cả sàn cho tất cả coin
  signals.py          <- 15 model tín hiệu
  scorer.py           <- gộp điểm có trọng số + xếp hạng
main.py               <- entry point, in bảng kết quả
output/                <- kết quả lưu ra (khi dùng --save)
```

## 📲 Telegram Alert (mới)

Bot tự động bắn cảnh báo vào Telegram (cá nhân hoặc group) khi có coin vượt ngưỡng PUMP/DUMP.

**Setup (3 bước):**
1. Chat với **@BotFather** trên Telegram → `/newbot` → làm theo hướng dẫn → lấy `TOKEN`
   (dạng `123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`).
2. Chat với bot vừa tạo (hoặc thêm bot vào group) 1 tin nhắn bất kỳ.
3. Mở trình duyệt: `https://api.telegram.org/bot<TOKEN>/getUpdates` → tìm `"chat":{"id": ...}`
   → đó là `CHAT_ID` (group thì thường là số âm).

**Cấu hình (chọn 1 trong 2 cách):**
```bash
# Cách 1 — biến môi trường (khuyên dùng, không lộ token khi đẩy code lên Git)
export TELEGRAM_BOT_TOKEN="123456789:AA..."
export TELEGRAM_CHAT_ID="987654321"
python main.py --telegram

# Cách 2 — truyền thẳng qua CLI
python main.py --telegram --telegram-token "123456789:AA..." --telegram-chat-id "987654321"
```

Mặc định chỉ gửi coin có nhãn **PUMP/DUMP** (không spam NEUTRAL) và **độ tin cậy >= 50%**
(`config.TELEGRAM_ONLY_ACTIONABLE`, `config.TELEGRAM_MIN_CONFIDENCE`) — chỉnh trong `config.py`.

**Chạy như 1 bot cảnh báo tự động, quét lặp lại mỗi N phút:**
```bash
python main.py --telegram --loop 15      # quét lại mỗi 15 phút, chạy liên tục tới khi Ctrl+C
```

**Tắt Telegram cho 1 lần chạy cụ thể** (kể cả khi đã bật sẵn trong `config.py`):
```bash
python main.py --no-telegram
```

## 🔴 Real-time WebSocket (mới)

3 model quan trọng nhất giờ dùng **data thật** thay vì ước lượng từ nến:

| Model | Trước (REST proxy) | Giờ (WebSocket thật) |
|---|---|---|
| #2 CVD | Suy ra buy/sell qua nến xanh/đỏ | Từng lệnh khớp thật (`aggTrade`/`publicTrade`/`trades`...) |
| #7 Taker Ratio | Tỷ trọng volume nến tăng/giảm | Buy/sell volume thật từ trade stream |
| #15 Liquidation Cluster | Suy ra qua biến động return đột biến | Lệnh thanh lý thật (Binance/Bybit/OKX `forceOrder`/`liquidation`) |

Cơ chế: mỗi lần chạy, hệ thống mở WebSocket, **lắng nghe trong `WS_WINDOW_SEC` giây** (mặc định 20s)
để gom trade/liquidation event thật, sau đó tính signal. Sàn nào WS lỗi/không hỗ trợ sẽ **tự động
rơi về công thức proxy cũ** cho riêng sàn đó — không văng lỗi, không ảnh hưởng các sàn khác.

**Độ phủ theo sàn:**

| Sàn | Trade WS (CVD/Taker) | Liquidation WS |
|---|---|---|
| Binance | ✅ | ✅ (all-market `!forceOrder@arr`) |
| Bybit | ✅ | ✅ |
| OKX | ✅ | ✅ |
| Bitget | ✅ | ❌ chưa có endpoint public xác nhận chắc chắn |
| KuCoin | ✅ (cần lấy bullet-token trước khi connect) | ❌ |
| MEXC | ⚠️ data đẩy dạng protobuf, bản JSON có thể không nhận được — cần verify | ❌ |

**Tuỳ chọn chạy:**
```bash
python main.py --no-ws                 # tắt hẳn WS, chạy REST-only như bản trước (nhanh hơn)
python main.py --ws-window 30           # lắng nghe 30s thay vì 20s mặc định (chính xác hơn, chậm hơn)
```

## 15 model tín hiệu

**Order flow (per-exchange):**
1. Order Book Imbalance
2. CVD xấp xỉ (Cumulative Volume Delta)
3. Volume Z-score Anomaly
4. VWAP Deviation
5. Spread & Depth Compression
6. Large Trade / Whale Tape Detection (proxy qua volume nến bất thường)
7. Taker Buy/Sell Ratio Extreme (xấp xỉ qua volume nến tăng/giảm)

**Cross-exchange (trọng số cao nhất — khó fake vì phải đồng thời trên nhiều sàn):**
8. Cross-Exchange Volume Surge Correlation
9. Cross-Exchange Price Divergence
10. Cross-Exchange Order Book Imbalance (weighted theo thanh khoản)

**Futures (chuẩn nhất ở Binance/Bybit/OKX, các sàn khác best-effort):**
11. Funding Rate + OI Divergence
12. Long/Short Account Ratio Extreme
13. Basis Spread (proxy qua funding rate)
14. Open Interest Surge vs Price Flat
15. Liquidation Cluster Estimate (proxy qua biến động return đột biến)

## ⚠️ Rất quan trọng — đọc trước khi chạy thật

0. **WebSocket cũng chưa test được với mạng thật** (lý do tương tự bên dưới). Format message,
   tên field (`m`, `S`, `side`, `bkPx`...) viết theo tài liệu API tại thời điểm biên soạn.
   Nếu 1 sàn nào không parse đúng, log sẽ hiện `[ws:<sàn>] lỗi ...` và signal tự dùng lại proxy
   REST cho sàn đó — sửa trực tiếp trong `core/ws_collector.py`, hàm tương ứng
   (`_binance_trades`, `_bybit_liquidations`,...). Riêng **MEXC trade WS nhiều khả năng cần
   decode protobuf** thay vì JSON thuần — đây là việc cần làm thêm nếu muốn MEXC có CVD/Taker
   Ratio thật (hiện sẽ tự fallback về proxy REST nếu JSON parse không ra data).
1. **Chưa test được với mạng thật.** Code được viết trong môi trường sandbox không có
   internet, nên các endpoint/param được viết đúng theo tài liệu API tại thời điểm biên soạn,
   nhưng **bạn cần chạy thử và kiểm tra log lỗi** (mỗi request lỗi sẽ tự in ra
   `[tên_sàn] request lỗi: ...` mà không làm sập chương trình) — nếu sàn nào đổi endpoint/tham
   số, chỉ cần sửa trong file `exchanges/<sàn>.py` tương ứng.
2. **KuCoin Futures cần mã hợp đồng riêng** (`XBTUSDTM`,...). File `exchanges/kucoin.py` có sẵn
   map cho ~20 coin phổ biến trong `config.SYMBOLS`; thêm coin mới thì tự bổ sung vào
   `_FUTURES_SYMBOL_MAP`.
3. **Bitget/MEXC/KuCoin phần futures là best-effort** — nếu 1 sàn không trả funding/OI cho 1 coin,
   hệ thống tự bỏ qua sàn đó cho signal đó, không lỗi toàn bộ.
4. **Rate limit:** `config.MAX_WORKERS` đang để 12 luồng song song. Nếu bị 429 (rate limit) từ
   sàn nào, giảm số này xuống hoặc tăng `HTTP_RETRY`/thời gian sleep trong `exchanges/base.py`.
5. **Đây là MVP heuristic**, các công thức tính điểm (hệ số nhân, ngưỡng z-score...) là ước lượng
   hợp lý ban đầu — **chưa backtest bằng dữ liệu lịch sử**. Trước khi dùng để ra quyết định
   vào lệnh thật, bạn nên:
   - Lưu lại kết quả `--save` theo thời gian để tự đối chiếu với diễn biến giá thực tế sau đó.
   - Tinh chỉnh `SIGNAL_WEIGHTS` và các ngưỡng trong `config.py` dựa trên dữ liệu backtest.
6. **Không phải lời khuyên đầu tư.** Đây là công cụ hỗ trợ lọc/rank, không đảm bảo lợi nhuận.

## Mở rộng tiếp theo (gợi ý)

- Thêm WebSocket (thay vì REST poll) để lấy CVD/taker ratio chính xác hơn (hiện đang xấp xỉ qua nến).
- Thêm bảng liquidation heatmap thật (Coinglass API) nếu muốn chính xác hơn cho signal #15.
- Lưu lịch sử score theo thời gian vào SQLite/Postgres để vẽ biểu đồ xu hướng điểm.
- Thêm Telegram/Discord bot bắn cảnh báo khi coin nào vượt ngưỡng PUMP/DUMP.
