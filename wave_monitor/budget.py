"""Application call limits use calendar days in Korea, including failed attempts."""
from datetime import datetime,timezone,timedelta

def day_start(now):return int((now+32400)//86400)*86400-32400

def reset_label(now):
    return datetime.fromtimestamp(day_start(now)+86400,timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M KST')

def notice(kind,count,limit,now):
    name='자동' if kind=='auto' else '질문'
    return (f'⏸ 프로그램의 {name} AI 분석 하루 상한 도달\n'
            f'오늘 호출 {count}/{limit}회 · 전체 종목 합산, 실패 시도 포함\n'
            f'🔄 초기화: {reset_label(now)}\n\n'
            '운영용으로 설정한 상한이며 Codex 계정 자체의 사용 한도와는 별개입니다.\n'
            '가격·매물대·구조 감시와 기존 시나리오 무효화 알림은 계속됩니다. /status 로 확인할 수 있어요.')
