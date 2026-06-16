#!/usr/bin/env python3
"""
Daily Briefing Bot v1.2
Claude Haiku 4.5 + Web Search → Telegram

Fixes so với v1.1:
- Thêm agentic loop xử lý tool_use đúng cách
- Retry logic (3 lần) cho network errors
- Validate env variables trước khi chạy
- Cải thiện error notification qua Telegram
"""

import os
import sys
import time
import requests
from datetime import datetime, timezone, timedelta
from anthropic import Anthropic, APIConnectionError, APITimeoutError, APIStatusError

# ── Timezone ────────────────────────────────────────────────────────────────
ICT = timezone(timedelta(hours=7))

# ── Task definitions ─────────────────────────────────────────────────────────
TASKS: dict[str, dict] = {
    "weather_today": {
        "emoji": "🌤️",
        "title": "Thời tiết Hà Nội — Hôm nay",
        "prompt": (
            "Tìm dự báo thời tiết Hà Nội, Việt Nam cho hôm nay. "
            "Trả lời bằng tiếng Việt, gồm:\n"
            "- Nhiệt độ cao/thấp (°C)\n"
            "- Khả năng mưa (%)\n"
            "- Độ ẩm (%) và tốc độ gió (km/h)\n"
            "- 1 dòng khuyến nghị thực tế (mang ô, tránh nắng...)\n\n"
            "Tối đa 150 từ. Không preamble, không lời kết."
        ),
    },
    "gold_price": {
        "emoji": "🥇",
        "title": "Giá vàng SJC — Hôm nay",
        "prompt": (
            "Tìm giá vàng SJC mới nhất tại Hà Nội, Việt Nam hôm nay. "
            "Ưu tiên nguồn: SJC.com.vn hoặc Vietcombank.\n"
            "Gồm: giá mua vào và giá bán ra (triệu VNĐ/lượng), "
            "chênh lệch so với hôm qua nếu có.\n\n"
            "Tối đa 80 từ. Không preamble, không lời kết."
        ),
    },
    "usd_rate": {
        "emoji": "💵",
        "title": "Tỷ giá USD/VNĐ — Hôm nay",
        "prompt": (
            "Tìm tỷ giá USD/VNĐ mới nhất hôm nay tại Việt Nam. "
            "Ưu tiên nguồn: Vietcombank, NHNN.\n"
            "Gồm:\n"
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
            "Tìm dự báo thời tiết Hà Nội, Việt Nam cho ngày mai. "
            "Gồm:\n"
            "- Nhiệt độ dự kiến (°C)\n"
            "- Khả năng mưa theo buổi (sáng/chiều/tối)\n"
            "- Điều kiện thời tiết chung\n"
            "- Cảnh báo nếu có thời tiết cực đoan\n\n"
            "Tối đa 150 từ. Không preamble, không lời kết."
        ),
    },
}


def run_haiku(task_key: str) -> str:
    """
    Gọi Haiku 4.5 với web search tool.
    Xử lý đúng tool_use loop và có retry cho lỗi mạng.
    """
    task = TASKS[task_key]
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    tools = [{
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": 3,
    }]

    for attempt in range(3):  # Retry tối đa 3 lần
        try:
            messages = [{"role": "user", "content": task["prompt"]}]

            # Agentic loop: xử lý tool_use nếu Haiku quyết định search
            for iteration in range(8):
                print(f"  → API call #{iteration + 1} (attempt {attempt + 1})")
                response = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=700,
                    tools=tools,
                    messages=messages,
                )

                # Thu thập tất cả text blocks trong response hiện tại
                texts = [
                    b.text for b in response.content
                    if hasattr(b, "text") and b.type == "text"
                ]

                # Nếu model đã xong → trả về kết quả
                if response.stop_reason == "end_turn":
                    result = "\n".join(texts).strip()
                    return result or "⚠️ Nhận được response rỗng từ model."

                # Nếu model muốn dùng tool → tiếp tục loop
                if response.stop_reason == "tool_use":
                    # Nếu đã có text rồi (ít gặp) → return luôn
                    if texts:
                        return "\n".join(texts).strip()

                    # Append assistant turn
                    messages.append({
                        "role": "assistant",
                        "content": response.content,
                    })

                    # Tạo tool_result placeholder cho mỗi tool_use block
                    tool_results = []
                    for block in response.content:
                        if hasattr(block, "type") and block.type == "tool_use":
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": "",
                            })

                    if tool_results:
                        messages.append({
                            "role": "user",
                            "content": tool_results,
                        })
                    continue

                # stop_reason khác (vd: max_tokens) → dùng text đã có
                if texts:
                    return "\n".join(texts).strip()
                break

            return "⚠️ Không lấy được dữ liệu sau nhiều vòng lặp."

        except (APIConnectionError, APITimeoutError) as e:
            # Lỗi mạng → retry
            if attempt < 2:
                wait = (attempt + 1) * 10
                print(f"  ⚠️ Network error (attempt {attempt + 1}): {e}")
                print(f"  → Retry sau {wait}s...")
                time.sleep(wait)
            else:
                raise

        except APIStatusError as e:
            # Lỗi API (401 auth, 429 rate limit...) → không retry
            raise RuntimeError(f"Anthropic API error {e.status_code}: {e.message}") from e

    return "⚠️ Không lấy được dữ liệu sau 3 lần thử."


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
    resp = requests.post(url, json=payload, timeout=15)
    resp.raise_for_status()


def send_error_notification(task_key: str, error: str) -> None:
    """Gửi thông báo lỗi qua Telegram (best-effort, không raise exception)."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat_id):
        return
    try:
        now_ict = datetime.now(ICT).strftime("%d/%m %H:%M ICT")
        msg = (
            f"⚠️ <b>Daily Briefing lỗi</b> — {now_ict}\n\n"
            f"Task: <code>{task_key}</code>\n"
            f"Lỗi: <code>{error[:400]}</code>\n\n"
            f"<i>Xem chi tiết: GitHub → Actions → Daily Briefing</i>"
        )
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(
            url,
            json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception:
        pass  # Error notification không được phép raise


def validate_env() -> list[str]:
    """Kiểm tra các biến môi trường bắt buộc."""
    required = ["ANTHROPIC_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]
    return [v for v in required if not os.environ.get(v)]


def main() -> None:
    # 1. Validate environment variables
    missing = validate_env()
    if missing:
        print(f"❌ Thiếu environment variables: {', '.join(missing)}")
        print("   Kiểm tra GitHub Secrets trong repo Settings.")
        sys.exit(1)

    # 2. Parse task argument
    if len(sys.argv) < 2 or not sys.argv[1]:
        print(f"Usage: python daily_briefing.py <task_key>")
        print(f"Tasks có sẵn: {', '.join(TASKS)}")
        sys.exit(1)

    task_key = sys.argv[1].strip()
    if task_key not in TASKS:
        print(f"❌ Task không hợp lệ: '{task_key}'")
        print(f"   Chọn một trong: {', '.join(TASKS)}")
        sys.exit(1)

    task = TASKS[task_key]
    now_ict = datetime.now(ICT).strftime("%d/%m/%Y %H:%M ICT")
    print(f"[{now_ict}] Running task: {task_key}")

    # 3. Chạy task
    try:
        content = run_haiku(task_key)
        print(f"✓ Response nhận được: {len(content)} ký tự")

        message = (
            f"{task['emoji']} <b>{task['title']}</b>\n\n"
            f"{content}\n\n"
            f"<i>🤖 Claude Haiku 4.5 · {now_ict}</i>"
        )
        send_telegram(message)
        print("✅ Đã gửi Telegram thành công")

    except Exception as e:
        error_msg = str(e)
        print(f"❌ Task failed: {error_msg}")
        send_error_notification(task_key, error_msg)
        sys.exit(1)


if __name__ == "__main__":
    main()
