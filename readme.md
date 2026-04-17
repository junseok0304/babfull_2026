# BABFULL Discord Menu Bot

성공회대학교 밥full 식단 페이지를 HTML 스크래핑해서  
디스코드 웹훅으로 식단을 전송하는 봇입니다.

## 기능

- 밥full 식단 페이지 스크래핑
- 평일 오전 9시 7분 오늘의 식단 자동 전송
- 식단 미갱신 시 안내 메시지 전송
- 주간 식단 수동 전송
- 주간 식단 표 이미지 생성 및 전송

## 파일 구조

- `menu_bot.py` : 일간 식단 전송
- `sub.py` : 주간 식단 수동 전송
- `sikdan_image.py` : 주간 식단 표 이미지 생성 및 전송
- `requirements.txt` : 필요한 패키지 목록
- `.github/workflows/daily_menu.yml` : 일간 식단 자동 실행
- `.github/workflows/weekly_manual.yml` : 주간 식단 수동 실행
- `fonts/` : Pretendard 폰트 파일

## 실행 방식

- 일간 식단: 평일 오전 9시 7분 자동 실행
- 주간 식단: GitHub Actions에서 수동 실행

## 주의

- 스크래핑 대상 사이트 구조가 변경되면 코드 수정이 필요할 수 있습니다.
- 식단이 아직 갱신되지 않은 경우 메뉴가 정상적으로 표시되지 않을 수 있습니다.
- `fonts` 폴더에 Pretendard 폰트 파일이 있어야 한글이 정상 출력됩니다.

## 사용 폰트

이 프로젝트는 OFL 라이선스를 따르는 Pretendard 폰트를 사용했습니다.