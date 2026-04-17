import os
import json
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


def load_font(size, bold=False):
    font_path = "fonts/Pretendard-Bold.otf" if bold else "fonts/Pretendard-Regular.otf"

    if not os.path.exists(font_path):
        raise RuntimeError(
            f"{font_path} 파일을 찾지 못했습니다. "
            "fonts 폴더에 Pretendard-Regular.otf, Pretendard-Bold.otf를 넣어주세요."
        )

    return ImageFont.truetype(font_path, size=size)


def get_line_height(draw, font):
    box = draw.textbbox((0, 0), "가나다ABC123", font=font)
    return (box[3] - box[1]) + 12


def wrap_text_by_char(draw, text, font, max_width):
    text = normalize(text)
    if not text:
        return [""]

    lines = []

    for paragraph in text.split("\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            lines.append("")
            continue

        current = ""
        for ch in paragraph:
            candidate = current + ch
            box = draw.textbbox((0, 0), candidate, font=font)
            width = box[2] - box[0]

            if width <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = ch

        if current:
            lines.append(current)

    return lines if lines else [""]


def make_day_title(header):
    month_day = header.split("(")[0].strip()
    weekday = header.split("(")[1].replace(")", "").strip()

    weekday_map = {
        "Mon": "월",
        "Tue": "화",
        "Wed": "수",
        "Thu": "목",
        "Fri": "금"
    }

    weekday_kr = weekday_map.get(weekday, weekday)
    return f"{month_day}\n{weekday_kr}"


def join_menu_lines(items, empty_message):
    if not items:
        return empty_message
    return "\n".join(f"• {item}" for item in items)


def create_weekly_menu_image(headers, breakfast_by_day, lunch_by_day, output_path):
    title_font = load_font(56, bold=True)
    subtitle_font = load_font(28, bold=False)
    header_font = load_font(34, bold=True)
    meal_font = load_font(36, bold=True)
    body_font = load_font(28, bold=False)
    footer_font = load_font(22, bold=False)

    temp_img = Image.new("RGB", (1, 1), "white")
    temp_draw = ImageDraw.Draw(temp_img)

    width = 2200
    outer_padding = 50
    title_top = 45
    title_gap = 25
    table_top_gap = 35

    left_label_width = 220
    day_col_width = 390
    header_height = 130
    row_padding_y = 30
    cell_padding_x = 22
    cell_padding_y = 20

    line_height = get_line_height(temp_draw, body_font)

    breakfast_cells = []
    lunch_cells = []

    for i in range(5):
        breakfast_text = join_menu_lines(breakfast_by_day.get(i, []), "조식 메뉴가 없습니다.")
        lunch_text = join_menu_lines(lunch_by_day.get(i, []), "중식 메뉴가 없습니다.")

        breakfast_cells.append(
            wrap_text_by_char(temp_draw, breakfast_text, body_font, day_col_width - cell_padding_x * 2)
        )
        lunch_cells.append(
            wrap_text_by_char(temp_draw, lunch_text, body_font, day_col_width - cell_padding_x * 2)
        )

    breakfast_max_lines = max(len(lines) for lines in breakfast_cells)
    lunch_max_lines = max(len(lines) for lines in lunch_cells)

    breakfast_row_height = cell_padding_y * 2 + breakfast_max_lines * line_height + row_padding_y
    lunch_row_height = cell_padding_y * 2 + lunch_max_lines * line_height + row_padding_y

    table_width = left_label_width + day_col_width * 5
    table_height = header_height + breakfast_row_height + lunch_row_height

    title_box = temp_draw.textbbox((0, 0), "밥full 주간 식단표", font=title_font)
    subtitle_box = temp_draw.textbbox((0, 0), "조식 / 중식 기준", font=subtitle_font)

    title_height = title_box[3] - title_box[1]
    subtitle_height = subtitle_box[3] - subtitle_box[1]

    footer_height = 40
    height = (
        outer_padding
        + title_top
        + title_height
        + title_gap
        + subtitle_height
        + table_top_gap
        + table_height
        + 70
        + footer_height
        + outer_padding
    )

    img = Image.new("RGB", (width, height), "#f5f7fb")
    draw = ImageDraw.Draw(img)

    table_x = (width - table_width) // 2
    y = outer_padding + title_top

    draw.text((table_x, y), "밥full 주간 식단표", font=title_font, fill="#111111")
    y += title_height + title_gap

    draw.text((table_x, y), "조식 / 중식 기준", font=subtitle_font, fill="#5b6470")
    y += subtitle_height + table_top_gap

    table_y = y
    table_bottom = table_y + table_height

    draw.rounded_rectangle(
        (table_x, table_y, table_x + table_width, table_bottom),
        radius=28,
        fill="white",
        outline="#d8dee8",
        width=3
    )

    draw.rounded_rectangle(
        (table_x, table_y, table_x + table_width, table_y + header_height),
        radius=28,
        fill="#e8eefc",
        outline=None
    )
    draw.rectangle(
        (table_x, table_y + header_height - 28, table_x + table_width, table_y + header_height),
        fill="#e8eefc"
    )

    meal_row_y = table_y + header_height
    lunch_row_y = meal_row_y + breakfast_row_height

    draw.rectangle(
        (table_x, meal_row_y, table_x + table_width, meal_row_y + breakfast_row_height),
        fill="#fffdf9"
    )
    draw.rectangle(
        (table_x, lunch_row_y, table_x + table_width, lunch_row_y + lunch_row_height),
        fill="#fbfcff"
    )

    x_positions = [table_x, table_x + left_label_width]
    for i in range(1, 6):
        x_positions.append(table_x + left_label_width + day_col_width * i)

    for x in x_positions[1:-1]:
        draw.line((x, table_y, x, table_bottom), fill="#d8dee8", width=3)

    draw.line(
        (table_x, table_y + header_height, table_x + table_width, table_y + header_height),
        fill="#d8dee8",
        width=3
    )
    draw.line(
        (table_x, lunch_row_y, table_x + table_width, lunch_row_y),
        fill="#d8dee8",
        width=3
    )

    label_box = draw.textbbox((0, 0), "식사", font=header_font)
    label_h = label_box[3] - label_box[1]
    draw.text(
        (table_x + 55, table_y + (header_height - label_h) // 2),
        "식사",
        font=header_font,
        fill="#1b2430"
    )

    for idx, header in enumerate(headers):
        title = make_day_title(header)
        col_x = table_x + left_label_width + day_col_width * idx
        wrapped = title.split("\n")

        total_h = 0
        heights = []
        for line in wrapped:
            box = draw.textbbox((0, 0), line, font=header_font)
            h = box[3] - box[1]
            heights.append(h)
            total_h += h
        total_h += (len(wrapped) - 1) * 8

        current_y = table_y + (header_height - total_h) // 2
        for line, h in zip(wrapped, heights):
            box = draw.textbbox((0, 0), line, font=header_font)
            w = box[2] - box[0]
            draw.text(
                (col_x + (day_col_width - w) // 2, current_y),
                line,
                font=header_font,
                fill="#1b2430"
            )
            current_y += h + 8

    breakfast_label_box = draw.textbbox((0, 0), "조식", font=meal_font)
    breakfast_label_h = breakfast_label_box[3] - breakfast_label_box[1]
    draw.text(
        (table_x + 58, meal_row_y + (breakfast_row_height - breakfast_label_h) // 2),
        "조식",
        font=meal_font,
        fill="#d46a6a"
    )

    lunch_label_box = draw.textbbox((0, 0), "중식", font=meal_font)
    lunch_label_h = lunch_label_box[3] - lunch_label_box[1]
    draw.text(
        (table_x + 58, lunch_row_y + (lunch_row_height - lunch_label_h) // 2),
        "중식",
        font=meal_font,
        fill="#4c8b5d"
    )

    def draw_lines(lines, x, y_top):
        current_y = y_top + cell_padding_y
        for line in lines:
            draw.text((x + cell_padding_x, current_y), line, font=body_font, fill="#111111")
            current_y += line_height

    for idx in range(5):
        col_x = table_x + left_label_width + day_col_width * idx
        draw_lines(breakfast_cells[idx], col_x, meal_row_y)
        draw_lines(lunch_cells[idx], col_x, lunch_row_y)

    footer_y = table_bottom + 28
    footer_text = f"생성 시각 {datetime.now(KST).strftime('%Y-%m-%d %H:%M')} (KST)"
    draw.text((table_x, footer_y), footer_text, font=footer_font, fill="#6b7280")

    img.save(output_path, format="PNG")


def create_notice_image(headers, output_path):
    title_font = load_font(54, bold=True)
    body_font = load_font(30, bold=False)
    small_font = load_font(22, bold=False)

    width = 1600
    height = 700
    padding = 70

    img = Image.new("RGB", (width, height), "#f5f7fb")
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle(
        (padding, padding, width - padding, height - padding),
        radius=28,
        fill="white",
        outline="#d8dee8",
        width=3
    )

    draw.text((120, 150), "주간 메뉴가 아직 갱신되지 않았습니다.", font=title_font, fill="#111111")
    draw.text((120, 270), "현재 감지된 주간 표", font=body_font, fill="#374151")
    draw.text((120, 340), " | ".join(headers), font=body_font, fill="#4b5563")
    draw.text(
        (120, 500),
        f"생성 시각 {datetime.now(KST).strftime('%Y-%m-%d %H:%M')} (KST)",
        font=small_font,
        fill="#6b7280"
    )

    img.save(output_path, format="PNG")


def send_image_to_discord(image_path, headers, is_current_week):
    content = "주간 식단 이미지"
    if not is_current_week:
        content = (
            "이번 주 메뉴가 아직 갱신되지 않은 것 같습니다.\n"
            f"현재 감지된 주간 표: {' | '.join(headers)}"
        )

    payload = {
        "content": content
    }

    with open(image_path, "rb") as f:
        files = {
            "files[0]": ("weekly_menu.png", f, "image/png")
        }
        data = {
            "payload_json": json.dumps(payload, ensure_ascii=False)
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