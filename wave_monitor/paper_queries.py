"""Read-only paper account queries; never invoke models or execution."""
import json,time
from datetime import datetime
from html import escape
from . import store,paper
from .presentation import pack,quoted

HELP='이 주제는 가상계좌 조회용입니다. /start · /balance · /positions 또는 “지금 잔고 얼마야”, “현재 포지션”, “이더 언제 왜 들어갔어?”라고 보내세요. 조회는 새 분석·매수·알림 재개를 실행하지 않습니다.'

def supported(text):
    low=text.strip().lower();command=low.split()[0].split('@')[0] if low else ''
    if command.startswith('/'):
        return command in ('/start','/balance','/positions','/position','/status','/report')
    return any(k in low for k in ('잔고','포지션','수익','손익','얼마','보유','진입','근거','손절','익절','상태','언제','몇','평단','계좌','거래',' USDT','왜','매수','매도'))

def stamp(t):return datetime.fromtimestamp(t,paper.KST).strftime('%m/%d %H:%M:%S KST')

def answer(text,now=None):
    now=time.time() if now is None else now
    if not supported(text):return pack([escape(HELP)])
    blocks=['<b>🧪 가상계좌 조회</b>\n'+stamp(now),escape(paper.summary(now))]
    age=now-store.get('paper_heartbeat',0)
    if age>30:blocks.append('⚠ 체결 기록 갱신이 지연되고 있습니다. 아래는 마지막 저장 상태입니다.')
    symbols=[]
    if any(k in text.lower() for k in ('btc','비트')):symbols.append('BTCUSDT')
    if any(k in text.lower() for k in ('eth','이더')):symbols.append('ETHUSDT')
    with store.db() as c:
        spec=paper.account_spec(c);states=paper.read_states(c)
        for p in states:
            if p.get('status') not in paper.ACTIVE or symbols and p['symbol'] not in symbols:continue
            row=c.execute('SELECT result FROM analyses WHERE id=?',(p['analysis_id'],)).fetchone()
            r=json.loads(row['result']) if row else {};plan=r.get('trade_plan',{});pp=plan.get('position_plan',{})
            side='롱' if p['sign']==1 else '숏'
            lines=[f"판단 {pp.get('thesis_timeframe','미기록')} / 진입 {pp.get('entry_timeframe',p['rules']['confirmation_tf'])} / 손절 {pp.get('stop_timeframe','미기록')}"]
            if p['status']=='open':
                price=store.get('price:'+p['symbol'],{});mark=price.get('price',p['average']);pnl=paper.unrealized(p,mark);notional=p['qty']*p['average']
                lines.append(f"수량 {p['qty']:.6f} {p['symbol'].removesuffix('USDT')} / 격리 증거금 {notional/p.get('leverage',1):,.2f} USDT / {p.get('leverage',1)}배")
                lines.extend([f"진입 시각 {stamp(p['entry_time'])} (1분봉 가상 체결)",f"평균 진입 {p['average']:,.2f} / 명목액 {notional:.3f} USDT",f"평가손익 {pnl:+.3f} USDT (증거금 수익률 {pnl/notional*p.get('leverage',1)*100:+.2f}%)" if notional else '잔량 없음',f"평가 가격 {mark:,.2f} · 기준 {stamp(price['time']) if price.get('time') else '시세 없음; 진입가 임시 사용'}"])
                realized=c.execute('SELECT COALESCE(SUM(pnl),0) FROM paper_events WHERE plan_id=?',(p['id'],)).fetchone()[0]
                lines.extend([f"이 포지션 실현손익 {realized:+.3f} USDT",f"최대 보유 종료 {stamp(p['entry_time']+p['hold_hours']*3600)}"])
            else:
                blocks.append(escape(paper.order_status(p)))
                lines.extend(['아직 보유하지 않습니다.',paper.order_status(p),f"계획 금액 {p['amount']:.3f} USDT",f"미체결 만료 {stamp(p['expires'])}"])
            lines.extend([f"현재 손절 {p['stop']:,.2f}",f"1차 익절 {p['tp1']:,.2f} ({p['take']*100:g}%) · "+('완료' if p['tp1_done'] else '대기'),f"잔량 목표 {p['tp2']:,.2f}",f"실행 조건: {p['reason']}"])
            for label,value in [('진입 근거',plan.get('entry_reason')),('파동·중첩 근거',r.get('entry_logic',{}).get('confluence'))]:
                if value:lines.append(label+': '+value[:700])
            blocks+=quoted(f"{'📍 보유' if p['status']=='open' else '⏳ 미체결'} {p['symbol']} {side} — 상세 보기",'\n\n'.join(lines))
        for symbol in symbols or store.settings()['symbols']:
            latest=next((p for p in reversed(states) if p.get('symbol')==symbol),None)
            if latest and latest.get('status')=='canceled':blocks.append(escape('🚫 '+symbol+' 최근 계획 취소: '+paper.cancellation_reason(c,latest)))
        events=[dict(x) for x in c.execute("SELECT symbol,kind,created,price,pnl FROM paper_events WHERE id>? AND kind IN ('entry','add','tp1','tp2','stop','time_exit','gap_exit','liquidation') ORDER BY id DESC LIMIT 10",(spec['event_floor'],))]
    if events:
        names={'entry':'진입','add':'추가 진입','tp1':'1차 익절','tp2':'잔량 익절','stop':'손절','time_exit':'시간 만료 청산','gap_exit':'데이터 공백 청산','liquidation':'격리 강제청산 모형'}
        lines=[f"{stamp(e['created'])} {e['symbol']} {names[e['kind']]} · {e['price']:,.2f} · 실현 {e['pnl']:+.3f} USDT" for e in events if not symbols or e['symbol'] in symbols]
        if lines:blocks+=quoted('📒 최근 체결 — 펼쳐 보기','\n\n'.join(lines))
    blocks.append('수수료·펀딩 제외 / 실제 주문 없음. USDT 손익·실제 코인 수량 기준의 가상계좌입니다.')
    return pack(blocks)
