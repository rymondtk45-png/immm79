# -*- coding: utf-8 -*-
"""
Gửi cảnh báo qua Telegram Bot khi có coin vượt ngưỡng PUMP/DUMP.

Setup nhanh:
1. Chat với @BotFather trên Telegram -> /newbot -> lấy TOKEN.
2. Chat với bot vừa tạo 1 tin nhắn bất kỳ (để bot "thấy" được chat_id).
3. Mở: https://api.telegram.org/bot<TOKEN>/getUpdates -> tìm "chat":{"id": ...}
4. export TELEGRAM_BOT_TOKEN="..." và export TELEGRAM_CHAT_ID="..." (hoặc sửa thẳng config.py)
"""
import requests
import config

API_BASE = "https://api.telegram.org"


def is_configured() -> bool:
    return bool(config.TELEGRAM_ENABLED and config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID)


def send_telegram_message(text: str) -> bool:
    if not is_configured():
        return False
    url = f"{API_BASE}/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={
                "chat_id": config.TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        if resp.status_code != 200:
            print(f"[telegram] gửi lỗi: HTTP {resp.status_code} - {resp.text[:200]}")
            return False
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[telegram] gửi lỗi: {e}")
        return False


def _emoji(label: str) -> str:
    return {"PUMP": "🟢🚀", "DUMP": "🔴🔻"}.get(label, "⚪")


def format_row(r: dict) -> str:
    chg = r.get("avg_change_24h_pct")
    chg_str = f"{chg:+.2f}%" if chg is not None else "-"
    price = r.get("avg_price")
    price_str = f"{price}" if price is not None else "-"
    return (
        f"{_emoji(r['label'])} <b>{r['symbol']}</b>  [{r['label']}]\n"
        f"  Điểm: <b>{r['score']}</b>/100 | Tin cậy: {r['confidence']}% "
        f"| Giá: {price_str} | 24h: {chg_str}"
    )


def build_alert_message(rows: list[dict]) -> str | None:
    """Lọc theo config (chỉ actionable + đủ confidence), format thành 1 tin nhắn Telegram."""
    filtered = []
    for r in rows:
        if config.TELEGRAM_ONLY_ACTIONABLE and r["label"] == "NEUTRAL":
            continue
        if r["confidence"] < config.TELEGRAM_MIN_CONFIDENCE:
            continue
        filtered.append(r)

    if not filtered:
        return None

    lines = ["<b>📡 Crypto Signal Scanner — Cảnh báo mới</b>", ""]
    for r in filtered:
        lines.append(format_row(r))
    lines.append("")
    lines.append("⚠️ MVP heuristic, không phải lời khuyên đầu tư. Tự kiểm chứng trước khi vào lệnh.")
    return "\n".join(lines)


def send_alerts(rows: list[dict]) -> bool:
    """Build + gửi cảnh báo. Trả về True nếu gửi thành công (hoặc không có gì cần gửi)."""
    if not is_configured():
        print("[telegram] chưa cấu hình TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID -> bỏ qua gửi.")
        return False

    msg = build_alert_message(rows)
    if msg is None:
        print("[telegram] không có coin nào đạt ngưỡng cảnh báo trong lần quét này.")
        return True

    # Telegram giới hạn ~4096 ký tự/tin nhắn -> chia nhỏ nếu message quá dài
    MAX_LEN = 3800
    if len(msg) <= MAX_LEN:
        ok = send_telegram_message(msg)
    else:
        chunks, current = [], ""
        for line in msg.split("\n"):
            if len(current) + len(line) + 1 > MAX_LEN:
                chunks.append(current)
                current = line
            else:
                current += ("\n" if current else "") + line
        if current:
            chunks.append(current)
        ok = all(send_telegram_message(c) for c in chunks)

    if ok:
        print("[telegram] đã gửi cảnh báo thành công.")
    return ok
