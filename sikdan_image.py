import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont


KST = ZoneInfo("Asia/Seoul")


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

    if text in {"👍", "👎", "/", "0"}:
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


def build_weekly_rows(headers, breakfast_by_day, lunch_by_day):
    rows = []

    for day_idx in range(5):
        breakfast_items = breakfast_by_day.get(day_idx, [])
        lunch_items = lunch_by_day.get(day_idx, [])

        breakfast_text = "\n".join(f"• {item}" for item in breakfast_items) if breakfast_items else "조식 메뉴가 없습니다."
        lunch_text = "\n".join(f"• {item}" for item in lunch_items) if lunch_items else "중식 메뉴가 없습니다."

        rows.append({
            "day": headers[day_idx],
            "breakfast": breakfast_text,
            "lunch": lunch_text
        })

    return rows


def load_font(size, bold=False):
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf" if bold else "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "C:/Windows/Fonts/malgun.ttf"
    ]

    if bold:
        candidates = [
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
            "/System/Library/Fonts/AppleSDGothicNeo.ttc",
            "C:/Windows/Fonts/malgunbd.ttf",
            "C:/Windows/Fonts/malgun.ttf"
        ]

    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size=size)

    return ImageFont.load_default()


def wrap_text(draw, text, font, max_width):
    if not text:
        return [""]

    lines = []
    for paragraph in text.split("\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            lines.append("")
            continue

        current = ""
        for token in paragraph.split(" "):
            test = token if not current else f"{current} {token}"
            bbox = draw.textbbox((0, 0), test, font=font)
            width = bbox[2] - bbox[0]

            if width <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = token

        if current:
            lines.append(current)

    return lines if lines else [""]


def calc_line_height(draw, font):
    bbox = draw.textbbox((0, 0), "가A", font=font)
    return (bbox[3] - bbox[1]) + 8


def create_weekly_menu_image(headers, breakfast_by_day, lunch_by_day, output_path):
    title_font = load_font(34, bold=True)
    header_font = load_font(22, bold=True)
    body_font = load_font(20, bold=False)
    small_font = load_font(16, bold=False)

    temp_img = Image.new("RGB", (1, 1), "white")
    temp_draw = ImageDraw.Draw(temp_img)

    rows = build_weekly_rows(headers, breakfast_by_day, lunch_by_day)

    width = 1700
    padding = 40
    title_height = 70
    subtitle_height = 40
    header_height = 60
    col_day = 220
    col_breakfast = 620
    col_lunch = 620
    table_width = col_day + col_breakfast + col_lunch

    line_h = calc_line_height(temp_draw, body_font)
    cell_padding_x = 18
    cell_padding_y = 14

    wrapped_rows = []
    total_rows_height = 0

    for row in rows:
        day_lines = wrap_text(temp_draw, row["day"], body_font, col_day - cell_padding_x * 2)
        breakfast_lines = wrap_text(temp_draw, row["breakfast"], body_font, col_breakfast - cell_padding_x * 2)
        lunch_lines = wrap_text(temp_draw, row["lunch"], body_font, col_lunch - cell_padding_x * 2)

        row_line_count = max(len(day_lines), len(breakfast_lines), len(lunch_lines))
        row_height = cell_padding_y * 2 + row_line_count * line_h

        wrapped_rows.append({
            "day_lines": day_lines,
            "breakfast_lines": breakfast_lines,
            "lunch_lines": lunch_lines,
            "row_height": row_height
        })
        total_rows_height += row_height

    height = padding + title_height + subtitle_height + header_height + total_rows_height + padding + 20

    img = Image.new("RGB", (width, height), "#f7f8fa")
    draw = ImageDraw.Draw(img)

    table_x = (width - table_width) // 2
    y = padding

    draw.text((table_x, y), "성공회대학교 밥full 주간 식단", font=title_font, fill="#111111")
    y += title_height

    subtitle = "스크래핑 기준 주간 식단표"
    draw.text((table_x, y), subtitle, font=small_font, fill="#555555")
    y += subtitle_height

    draw.rounded_rectangle(
        (table_x, y, table_x + table_width, y + header_height + total_rows_height),
        radius=18,
        fill="white",
        outline="#d9dce1",
        width=2
    )

    draw.rectangle(
        (table_x, y, table_x + table_width, y + header_height),
        fill="#eef3ff"
    )

    x1 = table_x
    x2 = x1 + col_day
    x3 = x2 + col_breakfast
    x4 = x3 + col_lunch

    for x in [x2, x3]:
        draw.line((x, y, x, y + header_height + total_rows_height), fill="#d9dce1", width=2)

    draw.line((x1, y + header_height, x4, y + header_height), fill="#d9dce1", width=2)

    draw.text((x1 + 20, y + 16), "요일", font=header_font, fill="#1a1a1a")
    draw.text((x2 + 20, y + 16), "조식", font=header_font, fill="#1a1a1a")
    draw.text((x3 + 20, y + 16), "중식", font=header_font, fill="#1a1a1a")

    y_cursor = y + header_height

    for idx, row in enumerate(wrapped_rows):
        row_bottom = y_cursor + row["row_height"]

        if idx > 0:
            draw.line((x1, y_cursor, x4, y_cursor), fill="#e5e7eb", width=2)

        def draw_multiline(lines, x, top):
            current_y = top + cell_padding_y
            for line in lines:
                draw.text((x + cell_padding_x, current_y), line, font=body_font, fill="#111111")
                current_y += line_h

        draw_multiline(row["day_lines"], x1, y_cursor)
        draw_multiline(row["breakfast_lines"], x2, y_cursor)
        draw_multiline(row["lunch_lines"], x3, y_cursor)

        y_cursor = row_bottom

    footer_y = y + header_height + total_rows_height + 18
    today = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    footer = f"생성 시각: {today} (KST)"
    draw.text((table_x, footer_y), footer, font=small_font, fill="#666666")

    img.save(output_path, format="PNG")


def create_notice_image(headers, output_path):
    title_font = load_font(32, bold=True)
    body_font = load_font(22, bold=False)
    small_font = load_font(16, bold=False)

    width = 1200
    height = 520
    padding = 50

    img = Image.new("RGB", (width, height), "#f7f8fa")
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle(
        (padding, padding, width - padding, height - padding),
        radius=24,
        fill="white",
        outline="#d9dce1",
        width=2
    )

    draw.text((90, 110), "주간 메뉴가 아직 갱신되지 않았습니다.", font=title_font, fill="#111111")
    draw.text((90, 190), "사이트의 현재 주간 표", font=body_font, fill="#333333")
    draw.text((90, 240), " | ".join(headers), font=body_font, fill="#444444")

    today = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    draw.text((90, 360), f"생성 시각: {today} (KST)", font=small_font, fill="#666666")

    img.save(output_path, format="PNG")


def send_image_to_discord(image_path, headers, is_current_week):
    content = "주간 식단 이미지"
    if not is_current_week:
        content = f"이번 주 메뉴가 아직 갱신되지 않은 것 같습니다.\n현재 감지된 주간 표: {' | '.join(headers)}"

    with open(image_path, "rb") as f:
        files = {
            "files[0]": ("weekly_menu.png", f, "image/png")
        }
        data = {
            "payload_json": (
                '{"content": ' + '"' + content.replace('"', '\\"').replace("\n", "\\n") + '"' + "}"
            )
        }
        response = requests.post(get_webhook_url(), data=data, files=files, timeout=30)
        response.raise_for_status()


def main():
    headers, breakfast_by_day, lunch_by_day = get_menu_data()
    output_path = "weekly_menu.png"

    current = is_this_week(headers)

    if current:
        create_weekly_menu_image(headers, breakfast_by_day, lunch_by_day, output_path)
    else:
        create_notice_image(headers, output_path)

    send_image_to_discord(output_path, headers, current)


if __name__ == "__main__":
    main()