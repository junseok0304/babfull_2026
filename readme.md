# BABFULL Discord Menu Bot

성공회대학교 밥full 식단 페이지를 HTML 스크래핑해서  
평일 오전 9시 7분에 디스코드 채널로 오늘의 식단을 전송하는 봇입니다.

## 기능

- 밥full 식단 페이지 스크래핑
- 오늘 요일에 맞는 메뉴만 추출
- Discord Webhook으로 자동 전송
- GitHub Actions로 평일 오전 9시 7분 자동 실행
- 이번 주 메뉴가 아직 갱신되지 않았으면 안내 메시지 전송

## 파일 구조

- `menu_bot.py` : 식단 스크래핑 및 디스코드 전송
- `requirements.txt` : 필요한 패키지 목록
- `.github/workflows/daily_menu.yml` : GitHub Actions 자동 실행

## 실행 시간

- 평일 오전 9시 7분 (KST)

## 주의

- 스크랩 해오는 사이트의 페이지 구조가 변경시 코드도 수정해야 함.
- 아직 식단이 갱신되지 않은 경우, 식단이 제공되지 않을 수 있음.