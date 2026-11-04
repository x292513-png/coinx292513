"""Persistent forward-only paper execution. No exchange credentials or order API."""
import json,math,time
from datetime import datetime,timezone,timedelta
from html import escape
from . import store
KST=timezone(timedelta(hours=9))
ACTIVE=('waiting','armed','open')

def init():
    with store.db() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS paper_plans(id INTEGER PRIMARY KEY,analysis_id INTEGER UNIQUE,symbol TEXT,state TEXT);
CREATE TABLE IF NOT EXISTS paper_events(id INTEGER PRIMARY KEY,plan_id INTEGER,created REAL,symbol TEXT,kind TEXT,price REAL,qty REAL,pnl REAL,detail TEXT);''')

def event(c,p,now,kind,price=0,qty=0,pnl=0,detail=''):
    c.execute('INSERT INTO paper_events(plan_id,created,symbol,kind,price,qty,pnl,detail) VALUES (?,?,?,?,?,?,?,?)',(p['id'],now,p['symbol'],kind,price,qty,pnl,detail))

def account(c):
    realized=c.execute('SELECT COALESCE(SUM(pnl),0) FROM paper_events').fetchone()[0]
    return 100+realized

def read_states(c):return [json.loads(r['state']) for r in c.execute('SELECT state FROM paper_plans')]
def save(c,p):c.execute('UPDATE paper_plans SET state=? WHERE id=?',(json.dumps(p,ensure_ascii=False),p['id']))

def reserve(p):
    if p['status'] not in ACTIVE:return 0,0
    if p['status']=='open':
        value=p['qty']*p['average'];risk=p['qty']*max(0,(p['average']-p['stop'])*p['sign'])
        if not p['added'] and not p['tp1_done']:value+=p['add_amount'];risk+=p['add_amount']*abs(p['add_limit']-p['stop'])/p['add_limit'] if p['add_amount'] else 0
        return value,risk
    amount=p['amount']+p['add_amount'];risk=p['amount']*abs(p['limit']-p['stop'])/p['limit']
    if p['add_amount']:risk+=p['add_amount']*abs(p['add_limit']-p['stop'])/p['add_limit']
    return amount,risk

def valid_execution(result):
    p=result.get('trade_plan',{});x=p.get('paper_execution',{})
    if not p.get('enabled') or x.get('mode','disabled')=='disabled':return False
    if result.get('bias') not in ('bullish','bearish'):raise ValueError('paper_direction')
    for k in ('entry_preferred','stop','tp1','tp2'):
        if not isinstance(p.get(k),(int,float)) or not math.isfinite(p[k]) or p[k]<=0:raise ValueError('paper_price')
    s=1 if result['bias']=='bullish' else -1
    if not (p['entry_preferred']-p['stop'])*s>0 or not (p['tp1']-p['entry_preferred'])*s>0 or not (p['tp2']-p['tp1'])*s>0:raise ValueError('paper_price_order')
    if not 0<p['take_pct']<100:raise ValueError('paper_partial')
    if x['mode'] not in ('limit','close_then_limit'):raise ValueError('paper_mode')
    if x['confirmation_tf'] not in ('5m','15m','1h','4h'):raise ValueError('paper_tf')
    if not 1<=x['expires_hours']<=12 or not 1<=x['hold_hours']<=72:raise ValueError('paper_expiry')
    if x['mode']=='close_then_limit' and (not isinstance(x['confirmation_price'],(int,float)) or not math.isfinite(x['confirmation_price']) or x['confirmation_price']<=0):raise ValueError('paper_confirmation')
    if not 0<p.get('position_plan',{}).get('initial_units',0)<=100:raise ValueError('paper_units')
    if x['add_enabled']:
        if not p['position_plan']['add_units'] or not isinstance(x['add_confirmation_price'],(int,float)) or not math.isfinite(x['add_confirmation_price']) or x['add_confirmation_price']<=0:raise ValueError('paper_add_confirmation')
        add=p['position_plan']['add_price']
        if not isinstance(add,(int,float)) or not math.isfinite(add) or not (add-p['stop'])*s>0 or not (p['entry_preferred']-add)*s>0:raise ValueError('paper_add_price')
    return True

def register(a,now):
    r=a['result'];plan=r.get('trade_plan',{});x=plan.get('paper_execution',{})
    with store.db() as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute('SELECT 1 FROM paper_plans WHERE analysis_id=?',(a['id'],)).fetchone():return
        states=read_states(c)
        # A new report never silently rewrites an existing position's stop or target.
        if any(p['symbol']==a['symbol'] and p['status']=='open' for p in states):
            c.execute('INSERT INTO paper_plans(analysis_id,symbol,state) VALUES (?,?,?)',(a['id'],a['symbol'],json.dumps({'symbol':a['symbol'],'status':'skipped','reason':'position_already_open'})))
            return
        for old in states:
            if old['symbol']==a['symbol'] and old['status'] in ('waiting','armed'):
                old['status']='canceled';event(c,old,now,'cancel',detail='new_analysis');save(c,old)
        pid=c.execute('INSERT INTO paper_plans(analysis_id,symbol,state) VALUES (?,?,?)',(a['id'],a['symbol'],'{}')).lastrowid
        p={'id':pid,'analysis_id':a['id'],'symbol':a['symbol'],'status':'skipped','created':now,'reason':x.get('reason','수치 실행 규칙 없는 분석')}
        try:valid=valid_execution(r)
        except (ValueError,KeyError,TypeError):valid=False;p['reason']='실행 수치 검증 실패'
        if not valid or a['snapshot'].get('stale_at_publication') or store.get('invalidated:'+str(a['id'])):
            save(c,p);return
        pp=plan['position_plan'];equity=account(c);used,risk=map(sum,zip(*(reserve(v) for v in states))) if states else (0,0)
        amount=equity*pp['initial_units']/100;add=equity*pp['add_units']/100 if x['add_enabled'] else 0
        proposed=amount*abs(plan['entry_preferred']-plan['stop'])/plan['entry_preferred']
        if add:proposed+=add*abs(pp['add_price']-plan['stop'])/pp['add_price']
        factor=min(1,max(0,equity-used)/max(amount+add,1e-9),max(0,equity*.01-risk)/max(proposed,1e-9))
        if equity<=0 or amount*factor<.01:p['reason']='공유 자금 또는 손실예산 부족';save(c,p);return
        p.update(status='waiting' if x['mode']=='close_then_limit' else 'armed',sign=1 if r['bias']=='bullish' else -1,limit=plan['entry_preferred'],stop=plan['stop'],tp1=plan['tp1'],tp2=plan['tp2'],take=plan['take_pct']/100,amount=amount*factor,add_amount=add*factor,add_limit=pp['add_price'] if add else 0,added=False,add_armed=None,qty=0,average=0,tp1_done=False,entry_time=None,armed_time=now if x['mode']=='limit' else None,last_t=(math.ceil(now/60)-1)*60000,expires=now+x['expires_hours']*3600,hold_hours=x['hold_hours'],rules=x)
        save(c,p);event(c,p,now,'planned',detail=x['reason'])

def confirmed(c,p,bar,add=False):
    x=p['rules'];level=x['add_confirmation_price'] if add else x['confirmation_price']
    after=p['entry_time'] if add else p['created']
    row=c.execute("SELECT c,close_t,t FROM candles WHERE symbol=? AND tf=? AND closed=1 AND close_t<=? AND close_t>? ORDER BY close_t DESC LIMIT 1",(p['symbol'],x['confirmation_tf'],bar['close_t'],after*1000)).fetchone()
    return bool(row and row['t']>=after*1000 and (row['c']-level)*p['sign']>0)

def hit_stop(p,b):return b['l']<=p['stop'] if p['sign']==1 else b['h']>=p['stop']
def hit_target(p,b,level):return b['h']>=level if p['sign']==1 else b['l']<=level

def exit_qty(c,p,b,qty,price,kind,detail=''):
    pnl=qty*(price-p['average'])*p['sign'];p['qty']=max(0,p['qty']-qty)
    event(c,p,b['close_t']/1000,kind,price,qty,pnl,detail)
    if p['qty']<1e-12:p['status']='closed'

def step(c,p,b):
    now=b['close_t']/1000;p['last_t']=b['t']
    if p['status'] in ('waiting','armed'):
        if now>p['expires'] or (p['status']=='waiting' and hit_stop(p,b)) or (b['o']-p['stop'])*p['sign']<=0:p['status']='canceled';event(c,p,now,'cancel',detail='expiry_or_invalidation');return
        if p['status']=='waiting':
            if confirmed(c,p,b):p['status']='armed';p['armed_time']=now;event(c,p,now,'armed',detail='closed_candle_confirmation')
            return # cannot fill on the candle that first confirms
        if b['t']/1000<=p['armed_time']:return
        touched=b['l']<=p['limit'] if p['sign']==1 else b['h']>=p['limit']
        if not touched:return
        price=min(p['limit'],b['o']) if p['sign']==1 else max(p['limit'],b['o'])
        if (price-p['stop'])*p['sign']<=0:return
        p.update(status='open',qty=p['amount']/price,average=price,entry_time=now)
        event(c,p,now,'entry',price,p['qty'],detail='1m_OHLC_simulated_fill')
        # Entry and exit order within one bar is unknowable: stop first; never TP on entry bar.
        if hit_stop(p,b):exit_qty(c,p,b,p['qty'],p['stop'],'stop','entry_bar_stop_first')
        return
    if p['status']!='open':return
    added_now=False
    if p['add_amount'] and not p['added'] and not p['tp1_done'] and p['add_armed'] is not None and b['t']/1000>p['add_armed'] and (b['o']-p['stop'])*p['sign']>0:
        touched=b['l']<=p['add_limit'] if p['sign']==1 else b['h']>=p['add_limit']
        if touched:
            price=min(p['add_limit'],b['o']) if p['sign']==1 else max(p['add_limit'],b['o'])
            qty=p['add_amount']/price;p['average']=(p['average']*p['qty']+price*qty)/(p['qty']+qty);p['qty']+=qty;p['added']=True;added_now=True
            event(c,p,now,'add',price,qty,detail='conditional_limit')
    if hit_stop(p,b):
        price=min(p['stop'],b['o']) if p['sign']==1 else max(p['stop'],b['o'])
        exit_qty(c,p,b,p['qty'],price,'stop','stop_first_if_both_targets_hit');return
    if added_now:return # no optimistic target fill on an ambiguous add bar
    if not p['tp1_done'] and hit_target(p,b,p['tp1']):
        exit_qty(c,p,b,p['qty']*p['take'],p['tp1'],'tp1');p['tp1_done']=True
        if p['rules']['breakeven_after_tp1']:p['stop']=p['average']
        # Do not assume path after TP1; test new break-even conservatively in same bar.
        if hit_stop(p,b):exit_qty(c,p,b,p['qty'],p['stop'],'stop','tp1_then_breakeven_ambiguous');return
    if hit_target(p,b,p['tp2']):exit_qty(c,p,b,p['qty'],p['tp2'],'tp2');return
    if now>=p['entry_time']+p['hold_hours']*3600:exit_qty(c,p,b,p['qty'],b['c'],'time_exit');return
    if p['add_amount'] and not p['added'] and not p['tp1_done']:
        if p['add_armed'] is None:
            if confirmed(c,p,b,True):p['add_armed']=now

def summary(now,full=False):
    if not store.get('paper_started'):return '가상 매매 준비 중'
    with store.db() as c:
        capital=account(c);states=read_states(c)
        events=[dict(r) for r in c.execute('SELECT * FROM paper_events WHERE created>=? ORDER BY id DESC LIMIT 15',(now-21600,))]
    unreal=0;stale=False;positions=[]
    for p in states:
        if p.get('status')!='open':continue
        price=store.get('price:'+p['symbol'],{})
        if now-price.get('time',0)>30:stale=True
        mark=price.get('price',p['average']);pnl=p['qty']*(mark-p['average'])*p['sign'];unreal+=pnl
        positions.append(f"{p['symbol']} {'롱' if p['sign']==1 else '숏'} · 평균 {p['average']:,.2f} · 평가 {pnl:+.3f}유닛")
        if full:positions.append(f"현재 스탑 {p['stop']:,.2f} · 잔량 목표 {p['tp2']:,.2f} · 투입잔액 {p['qty']*p['average']:.3f}유닛")
    reserved=sum(reserve(p)[0] for p in states if p.get('status') in ACTIVE)
    lines=['🧪 가상 매매 · 실제 주문 없음',f'총자산 {capital+unreal:.3f}유닛 / 시작 100',f'실현 {capital-100:+.3f} · 평가 {unreal:+.3f}유닛',f'미배정 {max(0,capital-reserved):.3f}유닛 · 조건/지정가 대기 {sum(p.get("status") in ("waiting","armed") for p in states)}건']
    if stale:lines.append('⚠ 시세 지연: 평가손익은 마지막 관측 가격 기준')
    lines+=positions or ['현재 보유 없음']
    if full:
        names={'planned':'계획 등록','armed':'진입 조건 확인','entry':'진입','add':'추가 진입','tp1':'1차 익절','tp2':'잔량 익절','stop':'손절','time_exit':'시간 만료 청산','cancel':'미체결 취소','gap_exit':'데이터 공백 후 첫 관측가 청산','gap':'데이터 공백'}
        lines+=['','최근 6시간 기록']
        for e in reversed(events):
            stamp=datetime.fromtimestamp(e['created'],KST).strftime('%H:%M')
            lines.append(f"{stamp} {e['symbol']} {names.get(e['kind'],e['kind'])}"+(f" {e['price']:,.2f} · 거래금액 {e['qty']*e['price']:.3f}유닛 · 손익 {e['pnl']:+.3f}" if e['price'] else ''))
        if not events:lines.append('새 거래 없음')
        for p in states:
            if p.get('status') in ('waiting','armed'):
                lines.extend(['',f"대기 {p['symbol']} {'롱' if p['sign']==1 else '숏'} · {p['amount']:.3f}유닛",f"지정가 {p['limit']:,.2f} / 손절 {p['stop']:,.2f}",f"1차 {p['tp1']:,.2f} ({p['take']*100:g}%) / 잔량 {p['tp2']:,.2f}",f"최대 보유 {p['hold_hours']:g}시간 · 조건: {p['reason']}"])
        for symbol in store.settings()['symbols']:
            latest=next((p for p in reversed(states) if p.get('symbol')==symbol),None)
            if latest and latest.get('status')=='skipped' and latest.get('reason')!='position_already_open':lines.extend(['',symbol+' · 미진입: '+latest.get('reason','실행 조건 없음')])
        lines+=['','수수료·펀딩 제외 / 1배 / 1분 OHLC 가상 체결. 같은 봉 손절·목표 동시 도달은 손절 우선. 과거 유리한 체결 소급 없음.']
    return '\n'.join(lines)

def report(now):
    from .presentation import pack,quoted
    core,_,details=summary(now,True).partition('\n\n최근 6시간 기록\n')
    first,_,body=core.partition('\n')
    blocks=['<b>'+escape(first)+'</b>\n'+datetime.fromtimestamp(now,KST).strftime('%m/%d %H:%M KST'),'\n\n'.join(escape(line) for line in body.splitlines())]
    if details:blocks+=quoted('📒 최근 거래 · 대기 조건 · 계산 기준 — 펼쳐 보기',details)
    return pack(blocks)

def tick(now):
    if not store.settings().get('paper_enabled',False):return
    if not store.get('paper_started'):store.put('paper_started',now)
    paused=store.get('paused',False)
    for symbol in store.settings()['symbols']:
        if paused:break
        a=store.latest(symbol)
        if a and a['created']>=store.get('paper_started') and a['created']>now-7200:register(a,now)
    with store.db() as c:
        c.execute('BEGIN IMMEDIATE')
        for p in read_states(c):
            if p.get('status') not in ACTIVE:continue
            if paused and p['status']!='open':
                p['status']='canceled';event(c,p,now,'cancel',detail='paused');save(c,p);continue
            bars=c.execute("SELECT * FROM candles WHERE symbol=? AND tf='1m' AND closed=1 AND t>? AND close_t<=? ORDER BY t",(p['symbol'],p['last_t'],now*1000)).fetchall()
            for row in bars:
                b=dict(row)
                if b['t']>p['last_t']+60000:
                    event(c,p,b['t']/1000,'gap',detail='missing_1m_bars')
                    if p['status']!='open':p['status']='canceled';break
                    # No fabricated profitable path across an unknown interval: close at next observed open.
                    exit_qty(c,p,b,p['qty'],b['o'],'gap_exit','data_gap_next_open');break
                step(c,p,b)
                if p['status'] not in ACTIVE:break
            if p['status'] in ('waiting','armed') and store.get('invalidated:'+str(p['analysis_id'])):
                p['status']='canceled';event(c,p,now,'cancel',detail='analysis_invalidated')
            save(c,p)
    store.put('paper_heartbeat',now)
    topic=store.get('paper_topic_id');local=datetime.fromtimestamp(now,KST)
    slot=local.strftime('%Y-%m-%d-')+str((local.hour-3)//6)
    if not paused and topic and local.hour in (3,9,15,21) and store.get('paper_report_slot')!=slot:
        store.enqueue_message(report(now),topic_id=topic);store.put('paper_report_slot',slot)
