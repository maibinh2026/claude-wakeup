#!/usr/bin/env python3
"""
Daily Briefing Bot — Claude Haiku 4.5 + Web Search → Telegram
Chạy qua GitHub Actions, 4 task/ngày theo giờ ICT.

Tasks:
  weather_today    — 03:50 ICT (thời tiết Hà Nội hôm nay)
  gold_price       — 09:00 ICT (giá vàng SJC)
  usd_rate         — 14:10 ICT (tỷ giá USD/VNĐ)
  weather_tomorrow — 19:20 ICT (dự báo thời tiết ngày mai)

Usage:
  python scripts/daily_briefing.py <task_key>
"""

import os
import sys
import requests
from datetime import datetime, timezone, timedelta
from anthropic import Anthropic

# ── Vietnam timezone ────────────────────────────────────────────────────────
ICT = timezone(timedelta(hours=7))

# ── Task definitions ─────────────────────────────────────────────────────────
TASKS: dict[str, dict] = {
    "weather_today": {
        "emoji": "🌤️",
        "title": "Thời tiết Hà Nội — Hôm nay",
        "prompt": (
            "Hãy tìm dự báo thời tiết Hà Nội, Việt Nam cho hôm nay. "
            "Trình bày bằng tiếng Việt, súc tích, gồm:\n"
            "- Nhiệt độ cao / thấp (°C)\n"
            "- Khả năng mưa (%)\n"
            "- Độ ẩm (%) và tốc độ gió (km/h)\n"
            "- 1 dòng khuyến nghị thực tế (mang ô, tránh nắng, v.v.)\n\n"
            "Tối đa 120 từ. Không preamble, không lời kết."
        ),
    },
    "gold_price": {
        "emoji": "🥇",
        "title": "Giá vàng SJC — Hôm nay",
        "prompt": (
            "Hãy tìm giá vàng SJC mới nhất tại Hà Nội, Việt Nam hôm nay. "
            "Ưu tiên nguồn: SJC.com.vn hoặc Vietcombank.\n"
            "Trình bày bằng tiếng Việt, gồm:\n"
            "- Giá mua vào và giá bán ra (triệu VNĐ/lượng)\n"
            "- Chênh lệch so với hôm qua và xu hướng nếu có dữ liệu\n\n"
            "Tối đa 80 từ. Không preamble, không lời kết."
        ),
    },
    "usd_rate": {
        "emoji": "💵",
        "title": "Tỷ giá USD/VNĐ — Hôm nay",
        "prompt": (
            "Hãy tìm tỷ giá USD/VNĐ mới nhất hôm nay tại Việt Nam. "
            "Ưu tiên nguồn: Vietcombank, NHNN.\n"
            "Trình bày bằng tiếng Việt, gồm:\n"
            "- Tỷ giá Vietcombank: mua TM / mua CK / bán\n"
            "- Tỷ giá trung tâm NHNN (nếu có)\n"
            "- Xu hướng so với hôm qua (tăng/giảm bao nhiêu đồng)\n\n"
            "Tối đa 80 từ. Không preamble, không lời kết."
        ),
    },
    "weather_tomorrow": {
        "emoji": "🌙",
        "title": "Dự báo thời tiết Hà Nội — Ngày mai",
        "prompt": (
            "Hãy tìm dự báo thời tiết Hà Nội, Việt Nam cho ngày mai. "
            "Trình bày bằng tiếng Việt, gồm:\n"
            "- Nhiệt độ dự kiến (°C)\n"
            "- Khả năng mưa theo buổi (sáng / chiều / tối)\n"
            "- Điều kiện thời tiết chung\n"
            "- 1 dòng cảnh báo nếu có thời tiết cực đoan\n\n"
            "Tối đa 120 từ. Không preamble, không lời kết."
        ),
    },
}


def run_haiku(task_key: str) -> str:
    """Gọi Haiku 4.5 với web search, trả về nội dung text."""
    task = TASKS[task_key]
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        tools=[
            {
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": 3,
            }
        ],
        messages=[{"role": "user", "content": task["prompt"]}],
    )

    # Chỉ lấy text blocks; bỏ qua tool_use / tool_result blocks
    texts = [
        block.text
        for block in response.content
        if hasattr(block, "text") and block.type == "text"
    ]
    result = "\n".join(texts).strip()
    return result or "⚠️ Không lấy được dữ liệu — thử lại sau."


def send_telegram(text: str) -> None:
    """Gửi message qua Telegram Bot API."""
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    r = requests.post(url, json=payload, timeout=15)
    r.raise_for_status()


def send_error_telegram(task_key: str, error: str) -> None:
    """Gửi thông báo lỗi qua Telegram nếu task thất bại."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return

    msg = (
        f"⚠️ <b>Daily Briefing thất bại</b>\n\n"
        f"Task: <code>{task_key}</code>\n"
        f"Lỗi: <code>{error[:300]}</code>\n\n"
        f"<i>Kiểm tra GitHub Actions logs để biết thêm chi tiết.</i>"
    )
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(
            url,
            json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception:
        pass  # Error notification itself shouldn't raise


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python daily_briefing.py <task_key>")
        print(f"Available tasks: {', '.join(TASKS)}")
        sys.exit(1)

    task_key = sys.argv[1]
    if task_key not in TASKS:
        print(f"❌ Unknown task '{task_key}'. Choose from: {list(TASKS)}")
        sys.exit(1)

    task = TASKS[task_key]
    now_ict = datetime.now(ICT).strftime("%d/%m/%Y %H:%M ICT")
    print(f"[{now_ict}] Running task: {task_key}")

    try:
        content = run_haiku(task_key)
        print(f"→ Response: {len(content)} chars")

        message = (
            f"{task['emoji']} <b>{task['title']}</b>\n\n"
            f"{content}\n\n"
            f"<i>🤖 Claude Haiku 4.5 · {now_ict}</i>"
        )
        send_telegram(message)
        print("✅ Sent to Telegram")

    except Exception as e:
        error_msg = str(e)
        print(f"❌ Task failed: {error_msg}")
        send_error_telegram(task_key, error_msg)
        sys.exit(1)


if __name__ == "__main__":
    main()
