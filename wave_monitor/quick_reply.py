"""Short follow-ups use an existing plan and a fresh quote, without full AI analysis."""
import asyncio
import json
import time
from datetime import datetime, timezone, timedelta
from html import escape
from aiohttp import ClientSession, ClientTimeout
from . import store
from .freshness import refresh_price
from .net import connector


def wants_quick(text):
    import re
    compact=''.join(text.lower().split()).strip('?.!요')
    compact=re.sub(r'^(비트코인|비트|이더리움|이더|btcusdt|ethusdt|btc|eth)', '', compact)
    return bool(re.fullmatch(r'(지금|현재)?(들어간다면|들어가면|진입하면)?(손절|스탑|익절)(은|을|이|를)?(어디|얼마|가격|라인)(야|에|인가|인가요|잡아|잡을까|야해)?',compact))


def recent_symbol():
    context=store.get('conversation_symbol',{})
    if time.time()-context.get('time',0)<21600:return context.get('symbol')
    with store.db() as c:
        rows=c.execute("SELECT symbol,created FROM jobs WHERE kind='manual' ORDER BY id DESC LIMIT 2").fetchall()
    if not rows or time.time()-rows[0]['created']>21600:return None
    if len(rows)>1 and rows[0]['symbol']!=rows[1]['symbol'] and abs(rows[0]['created']-rows[1]['created'])<10:return None
    return rows[0]['symbol']


def short_answer(analysis, price, now, question):
    symbol=analysis['symbol'];result=analysis['result'];plan=result.get('trade_plan') or {}
    stamp=datetime.fromtimestamp(price['time'],timezone(timedelta(hours=9))).strftime('%H:%M:%S')
    head=f"{symbol} · 현재 {price['price']:,.2f} · {stamp} KST"
    asof=analysis.get('snapshot',{}).get('asof',analysis['created'])
    age=now-asof
    from .engine import is_invalid
    if age>7200 or store.get('invalidated:'+str(analysis['id'])) is not None or is_invalid(result,price['price']):
        return head+f"\n\n기존 분석 #{analysis['id']}은 오래됐거나 무효화돼 지금 진입용 손절로 쓸 수 없습니다. 새 분석으로 기준을 다시 잡아야 합니다."
    if not plan.get('enabled'):
        return head+f'\n\n기존 분석 #{analysis["id"]}은 진입 대기입니다.\n'+escape(plan.get('reason','새 파동 분석이 필요합니다.'))+f'\n\n기존 파동 판단 {int(max(0,age)//60)}분 전 · 현재가 재확인'
    from .trade_plan import validate
    validate(plan,result['bias'])
    side='롱' if result['bias']=='bullish' else '숏'
    if ('숏' in question and side=='롱') or ('롱' in question and side=='숏'):
        return head+f'\n\n기존 계획은 {side} 기준입니다. 반대 방향의 손절로 사용할 수 없습니다. 원하는 방향으로 새 분석이 필요합니다.'
    current=price['price'];stop=plan['stop'];tp=plan['tp1'];long=side=='롱'
    if (long and not stop<current<tp) or (not long and not tp<current<stop):
        return head+'\n\n기존 손절선 또는 1차 목표를 이미 지나 지금 진입에는 기존 계획을 적용할 수 없습니다.'
    risk=abs(current-stop);rr=abs(tp-current)/risk
    inside=plan['entry_low']<=current<=plan['entry_high']
    verdict='현재가는 기존 진입 구간 안입니다. 아래 진입 조건 충족은 별도 확인해야 합니다.' if inside else '현재가는 기존 진입 구간 밖입니다. 지금 추격 진입은 대기 판단입니다.'
    return '\n\n'.join([f'⛔ <b>{side} 손절 기준 {stop:,.2f}</b>\n실시간 가격 이탈 기준 · 기존 분석 #{analysis["id"]}',head,
        f'지금 가격에 진입한다고 가정하면 손절까지 <b>{risk/current*100:.2f}%</b>\n1차 익절 {tp:,.2f} · 손익비 {rr:.2f}R (비용 전)',
        verdict+'\n기존 진입 구간 '+f"{plan['entry_low']:,.2f}–{plan['entry_high']:,.2f}",
        '진입 조건: '+escape(plan['entry_rule']),
        '손절 근거: '+escape(plan['stop_reason']),
        f'기존 파동 분석 {int(max(0,age)//60)}분 전 · 현재가만 실시간 재확인'])


async def answer(symbol, ref, question, mid):
    analysis=None
    if ref:
        with store.db() as c:
            row=c.execute('SELECT * FROM analyses WHERE id=? AND symbol=?',(ref,symbol)).fetchone()
        if row:
            analysis=dict(row)
            for field in ['snapshot','result']:analysis[field]=json.loads(analysis[field])
    else:analysis=store.latest(symbol)
    if not analysis:
        store.enqueue_message(symbol+'의 참고할 분석이 없습니다. 먼저 해당 종목 분석을 요청해 주세요.',reply_id=mid)
        return
    try:
        async with ClientSession(connector=connector(),timeout=ClientTimeout(total=5)) as session:
            price=await asyncio.wait_for(refresh_price(session,symbol),timeout=5)
        message=short_answer(analysis,price,time.time(),question)
    except Exception:
        message=symbol+' 현재 가격을 확인하지 못해 지금 진입용 손절을 제시할 수 없습니다. 잠시 후 다시 물어봐 주세요.'
    from .presentation import pack
    store.enqueue_message(pack(message.split('\n\n')),analysis_id=analysis['id'],reply_id=mid)
