import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup


KST = ZoneInfo("Asia/Seoul")
WEEKDAY_LABELS = ["월", "화", "수", "목", "금"]


def get_menu_url():
    url = os.environ.get("BABFULL_MENU_URL")
    if not url:
        raise RuntimeError("BABFULL_MENU_URL 환경변수가 설정되지 않았습니다.")
    return url


def get_webhook_url():
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        raise RuntimeError("DISCORD_WEBHOOK_URL 환경변수가 설정되지 않았습니다.")
    return url


def fetch_soup():
    response = requests.get(
        get_menu_url(),
        timeout=20,
        headers={"User-Agent": "Mozilla/5.0"}
    )
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def normalize(text):
    return " ".join(text.replace("\xa0", " ").split()).strip()


def extract_cell_text(cell):
    text = normalize(cell.get_text(" ", strip=True))

    if not text:
        return ""

    vote_tokens = ["👍", "👎", "/", "0"]

    if "👍" in text or "👎" in text:
        parts = text.split()
        filtered_parts = []

        skip_next_zero = False
        for part in parts:
            if part in {"👍", "👎"}:
                skip_next_zero = True
                continue

            if skip_next_zero and part == "0":
                skip_next_zero = False
                continue

            if part == "/":
                continue

            filtered_parts.append(part)

        text = " ".join(filtered_parts)

    if text in vote_tokens:
        return ""

    return normalize(text)


def parse_date_headers(table):
    rows = table.find_all("tr")
    if not rows:
        raise RuntimeError("표를 찾지 못했습니다.")

    header_cells = rows[0].find_all(["th", "td"])
    headers = [normalize(cell.get_text(" ", strip=True)) for cell in header_cells[:5]]

    if len(headers) < 5:
        raise RuntimeError("요일 헤더 5개를 찾지 못했습니다.")

    return headers


def extract_section_rows(table, section_name):
    rows = table.find_all("tr")
    section_rows = []
    in_section = False

    for row in rows[1:]:
        cells = row.find_all(["th", "td"])
        if not cells:
            continue

        values = [extract_cell_text(cell) for cell in cells]
        joined = " ".join(v for v in values if v)

        if "조식" in joined:
            if section_name == "조식":
                in_section = True
                continue
            if in_section:
                break

        if "중식" in joined:
            if section_name == "중식":
                in_section = True
                continue
            if in_section:
                break

        if "석식" in joined and in_section:
            break

        if in_section:
            row_values = values[:5]
            if len(row_values) < 5:
                row_values += [""] * (5 - len(row_values))
            section_rows.append(row_values)

    return section_rows


def parse_menu_by_day(section_rows):
    result = {i: [] for i in range(5)}

    for row in section_rows:
        for col in range(5):
            value = normalize(row[col])

            if not value:
                continue

            if "👍" in value or "👎" in value:
                continue

            if value in {"0", "/"}:
                continue

            result[col].append(value)

    return result


def get_menu_data():
    soup = fetch_soup()
    table = soup.find("table")
    if table is None:
        raise RuntimeError("식단 표를 찾지 못했습니다.")

    headers = parse_date_headers(table)

    breakfast_rows = extract_section_rows(table, "조식")
    lunch_rows = extract_section_rows(table, "중식")

    breakfast_by_day = parse_menu_by_day(breakfast_rows)
    lunch_by_day = parse_menu_by_day(lunch_rows)

    return headers, breakfast_by_day, lunch_by_day


def current_week_monday():
    today = datetime.now(KST).date()
    return today - timedelta(days=today.weekday())


def parse_header_date(header_text):
    month_day = header_text.split("(")[0].strip()
    month, day = month_day.split("-")
    year = datetime.now(KST).year
    return datetime(year, int(month), int(day), tzinfo=KST).date()


def is_this_week(headers):
    try:
        site_monday = parse_header_date(headers[0])
        return site_monday == current_week_monday()
    except Exception:
        return False


def build_today_embed(headers, breakfast_by_day, lunch_by_day):
    now = datetime.now(KST)
    weekday = now.weekday()
    week_text = " | ".join(headers)

    if weekday >= 5:
        return {
            "title": f"🍚 {now.strftime('%Y-%m-%d')} 오늘의 학식",
            "description": "주말이라 운영 식단이 없습니다.",
            "fields": [
                {"name": "주간 표", "value": week_text, "inline": False}
            ]
        }

    if not is_this_week(headers):
        return {
            "title": f"⚠️ {now.strftime('%Y-%m-%d')} 오늘의 학식",
            "description": "사이트의 주간 메뉴가 아직 이번 주 기준으로 갱신되지 않은 것 같습니다.",
            "fields": [
                {"name": "현재 감지된 주간 표", "value": week_text, "inline": False}
            ]
        }

    breakfast_items = breakfast_by_day.get(weekday, [])
    lunch_items = lunch_by_day.get(weekday, [])

    fields = [
        {"name": "주간 표", "value": week_text, "inline": False},
        {"name": "오늘", "value": f"{headers[weekday]} ({WEEKDAY_LABELS[weekday]})", "inline": False},
    ]

    if breakfast_items:
        fields.append({
            "name": "조식",
            "value": "\n".join(f"• {item}" for item in breakfast_items),
            "inline": False
        })
    else:
        fields.append({
            "name": "조식",
            "value": "조식 메뉴가 없습니다.",
            "inline": False
        })

    if lunch_items:
        fields.append({
            "name": "중식",
            "value": "\n".join(f"• {item}" for item in lunch_items),
            "inline": False
        })
    else:
        fields.append({
            "name": "중식",
            "value": "중식 메뉴가 없습니다.",
            "inline": False
        })

    return {
        "title": f"🍚 {now.strftime('%Y-%m-%d')} 오늘의 학식",
        "description": "성공회대학교 밥full 식단 안내",
        "fields": fields
    }


def build_weekly_embed(headers, breakfast_by_day, lunch_by_day):
    now = datetime.now(KST)

    if not is_this_week(headers):
        return {
            "title": f"⚠️ {now.strftime('%Y-%m-%d')} 주간 학식",
            "description": "사이트의 주간 메뉴가 아직 이번 주 기준으로 갱신되지 않은 것 같습니다.",
            "fields": [
                {"name": "현재 감지된 주간 표", "value": " | ".join(headers), "inline": False}
            ]
        }

    fields = []

    for day_idx in range(5):
        day_lines = []

        breakfast_items = breakfast_by_day.get(day_idx, [])
        lunch_items = lunch_by_day.get(day_idx, [])

        day_lines.append("[조식]")
        if breakfast_items:
            day_lines.extend(f"• {item}" for item in breakfast_items)
        else:
            day_lines.append("• 조식 메뉴가 없습니다.")

        day_lines.append("")
        day_lines.append("[중식]")
        if lunch_items:
            day_lines.extend(f"• {item}" for item in lunch_items)
        else:
            day_lines.append("• 중식 메뉴가 없습니다.")

        fields.append({
            "name": headers[day_idx],
            "value": "\n".join(day_lines),
            "inline": False
        })

    return {
        "title": f"🍱 {now.strftime('%Y-%m-%d')} 주간 학식",
        "description": "성공회대학교 밥full 주간 식단 안내",
        "fields": fields
    }


def send_discord_embed(embed):
    payload = {
        "username": "오늘의 학식",
        "embeds": [embed]
    }

    response = requests.post(get_webhook_url(), json=payload, timeout=20)
    response.raise_for_status()


def main():
    headers, breakfast_by_day, lunch_by_day = get_menu_data()
    now = datetime.now(KST)

    if now.weekday() == 0:
        weekly_embed = build_weekly_embed(headers, breakfast_by_day, lunch_by_day)
        send_discord_embed(weekly_embed)

    today_embed = build_today_embed(headers, breakfast_by_day, lunch_by_day)
    send_discord_embed(today_embed)


if __name__ == "__main__":
    main()