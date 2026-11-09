"""Persistent forward-only paper execution. No exchange credentials or order API."""
import json,math,time
from datetime import datetime,timezone,timedelta
from html import escape
from . import store
KST=timezone(timedelta(hours=9))
ACTIVE=('waiting','armed','open')
MARKET_MODES=('market','close_then_market')
CANCEL_REASONS={'structure_failure_before_entry':'진입 전 구조 실패선 이탈','reversal_or_breakout_failed_at_open':'진입 직전 반전·돌파 기준선 재이탈','entry_band_chase_or_rr_failed':'허용 가격·최대 이격 또는 1차 손익비 조건 불충족','portfolio_risk_budget':'공유 계좌의 남은 손실예산 부족','expiry_or_invalidation':'미체결 유효시간 만료 또는 손절 기준 이탈','unencoded_conditions':'필수 실행 조건 미검증','new_analysis':'새 분석 계획으로 교체','analysis_invalidated':'분석 가설 무효화','paused':'사용자 일시정지'}
CANCEL_REASONS.update(expired='미체결 주문의 유효시간 만료',stop_invalidated='진입 전 손절 기준선 이탈',missing_1m_bars='1분봉 데이터 누락으로 체결 여부를 검증할 수 없어 취소',stop_beyond_isolated_liquidation='손절선이 격리 청산 추정선보다 멀어 진입 취소')

def cancellation_reason(c,p):
    row=c.execute("SELECT detail FROM paper_events WHERE plan_id=? AND kind='cancel' ORDER BY id DESC LIMIT 1",(p['id'],)).fetchone()
    return CANCEL_REASONS.get(row['detail'],'가상 주문 취소') if row else '가상 주문 취소'

def init():
    with store.db() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS paper_plans(id INTEGER PRIMARY KEY,analysis_id INTEGER UNIQUE,symbol TEXT,state TEXT);
CREATE TABLE IF NOT EXISTS paper_events(id INTEGER PRIMARY KEY,plan_id INTEGER,created REAL,symbol TEXT,kind TEXT,price REAL,qty REAL,pnl REAL,detail TEXT);''')

def event(c,p,now,kind,price=0,qty=0,pnl=0,detail=''):
    c.execute('INSERT INTO paper_events(plan_id,created,symbol,kind,price,qty,pnl,detail) VALUES (?,?,?,?,?,?,?,?)',(p['id'],now,p['symbol'],kind,price,qty,pnl,detail))
    if kind not in ('entry','add','cancel'):return
    row=c.execute("SELECT value FROM kv WHERE key='paper_topic_id'").fetchone()
    if not row or not json.loads(row[0]):return
    if kind=='cancel':
        side='롱(매수)' if p['sign']==1 else '숏(매도)'
        label='예정 기준가' if p['rules']['mode'] in MARKET_MODES else '대기 지정가'
        reason=CANCEL_REASONS.get(detail,'가상 주문 취소: '+detail)
        if detail=='structure_failure_before_entry' and p['rules'].get('cancel_price') is not None:
            reason+=f" · {p['rules']['cancel_tf']} 종가 {p['rules']['cancel_price']:,.2f} {'이하' if p['sign']==1 else '이상'}"
        if detail=='stop_invalidated':reason+=f" · {p['stop']:,.2f} USDT"
        text=(f"🚫 <b>가상 진입 대기 취소 · {escape(p['symbol'])} {side}</b>\n"
              f"{label} <b>{p['limit']:,.2f} USDT</b>\n"
              f"취소 근거: {escape(reason)}\n"
              f"{datetime.fromtimestamp(now,KST).strftime('%m/%d %H:%M:%S KST')} · 주문 #{p['id']} · 미체결")
        c.execute('INSERT INTO outbox(created,text,topic_id) VALUES (?,?,?)',(time.time(),text,json.loads(row[0])))
        return
    # Use the same transaction as the fill; a rollback must never announce a trade.
    title='가상 진입 체결' if kind=='entry' else '가상 추가 진입 체결'
    side='롱' if p['sign']==1 else '숏'
    reason=' '.join(str(p.get('reason') or '저장된 진입 조건 충족').split())
    if len(reason)>180:reason=reason[:177]+'…'
    text=(f"✅ <b>{title} · {escape(p['symbol'])} {side}</b>\n"
          f"체결가 <b>{price:,.2f} USDT</b> · {qty:.6g}개 · {p.get('leverage',1):g}배\n"
          f"근거: {escape(reason)}\n"
          f"{datetime.fromtimestamp(now,KST).strftime('%m/%d %H:%M:%S KST')} · 주문 #{p['id']}\n"
          "1분봉 OHLC 기준 가상 체결")
    c.execute('INSERT INTO outbox(created,text,topic_id) VALUES (?,?,?)',(time.time(),text,json.loads(row[0])))

def account_spec(c):
    row=c.execute("SELECT value FROM kv WHERE key='paper_account_v2'").fetchone()
    return json.loads(row[0]) if row else dict(initial=100,leverage=1,mode='legacy',event_floor=0,plan_floor=0)

def start_usdt_account(now):
    """One-time new forward account; preserve all legacy plans/events unchanged."""
    with store.db() as c:
        c.execute('BEGIN IMMEDIATE')
        if account_spec(c)['mode']=='isolated':return False
        spec=dict(initial=10000,leverage=5,mode='isolated',maintenance_rate=.005,created=now,
                  event_floor=c.execute('SELECT COALESCE(MAX(id),0) FROM paper_events').fetchone()[0],
                  plan_floor=c.execute('SELECT COALESCE(MAX(id),0) FROM paper_plans').fetchone()[0])
        for key,value in [('paper_account_v2',spec),('paper_started',now)]:
            c.execute('INSERT OR REPLACE INTO kv VALUES (?,?)',(key,json.dumps(value)))
    return True

def account(c):
    spec=account_spec(c)
    realized=c.execute('SELECT COALESCE(SUM(pnl),0) FROM paper_events WHERE id>?',(spec['event_floor'],)).fetchone()[0]
    return spec['initial']+realized

def read_states(c):
    return [json.loads(r['state']) for r in c.execute('SELECT state FROM paper_plans WHERE id>? ORDER BY id',(account_spec(c)['plan_floor'],))]

def liquidation_price(p,entry=None):
    entry=p['average'] if entry is None else entry
    return entry*(1-p['sign']/p.get('leverage',1))/(1-p['sign']*p.get('maintenance_rate',0))

def save(c,p):c.execute('UPDATE paper_plans SET state=? WHERE id=?',(json.dumps(p,ensure_ascii=False),p['id']))

def reserve(p):
    if p['status'] not in ACTIVE:return 0,0
    if p['status']=='open':
        value=p['qty']*p['average'];risk=p['qty']*max(0,(p['average']-p['stop'])*p['sign'])
        if not p['added'] and not p['tp1_done']:value+=p['add_amount'];risk+=p['add_amount']*abs(p['add_limit']-p['stop'])/p['add_limit'] if p['add_amount'] else 0
        return value/p.get("leverage",1),risk
    amount=p['amount']+p['add_amount'];risk=p['amount']*abs(p['limit']-p['stop'])/p['limit']
    if p['add_amount']:risk+=p['add_amount']*abs(p['add_limit']-p['stop'])/p['add_limit']
    return amount/p.get("leverage",1),risk

def valid_execution(result):
    p=result.get('trade_plan',{});x=p.get('paper_execution',{})
    if not p.get('enabled') or x.get('mode','disabled')=='disabled':return False
    if x.get('conditions_fully_encoded') is not True:raise ValueError('paper_unencoded_conditions')
    if '표현할 수 없' in x.get('reason',''):raise ValueError('paper_unencoded_conditions')
    if result.get('bias') not in ('bullish','bearish'):raise ValueError('paper_direction')
    for k in ('entry_preferred','stop','tp1','tp2'):
        if not isinstance(p.get(k),(int,float)) or not math.isfinite(p[k]) or p[k]<=0:raise ValueError('paper_price')
    s=1 if result['bias']=='bullish' else -1
    if not (p['entry_preferred']-p['stop'])*s>0 or not (p['tp1']-p['entry_preferred'])*s>0 or not (p['tp2']-p['tp1'])*s>0:raise ValueError('paper_price_order')
    if not 0<p['take_pct']<100:raise ValueError('paper_partial')
    if x['mode'] not in ('limit','close_then_limit',*MARKET_MODES):raise ValueError('paper_mode')
    if x['confirmation_tf'] not in ('1m','5m','15m','1h','4h'):raise ValueError('paper_tf')
    if not .05<=x['expires_hours']<=12 or not 1<=x['hold_hours']<=72:raise ValueError('paper_expiry')
    if x['mode']!='limit' and (not isinstance(x['confirmation_price'],(int,float)) or not math.isfinite(x['confirmation_price']) or x['confirmation_price']<=0):raise ValueError('paper_confirmation')
    if x['mode'] in MARKET_MODES:
        if x.get('setup') not in ('c_wave_reversal','wave4_reversal','impulse_continuation','pullback'):raise ValueError('paper_setup')
        if not .05<=x.get('max_entry_deviation_pct',0)<=2:raise ValueError('paper_chase_cap')
        if x['add_enabled']:raise ValueError('paper_market_add_not_supported')
        for k in ('entry_low','entry_high'):
            if not isinstance(p.get(k),(int,float)) or not math.isfinite(p[k]):raise ValueError('paper_entry_band')
        if not p['entry_low']<=p['entry_preferred']<=p['entry_high']:raise ValueError('paper_entry_band')
    cancel=x.get('cancel_price')
    if cancel is not None:
        if not isinstance(cancel,(int,float)) or not math.isfinite(cancel) or cancel<=0 or x.get('cancel_tf') not in ('1m','5m','15m','1h','4h'):raise ValueError('paper_cancel')
        if (cancel-p['stop'])*s<0 or (p['entry_preferred']-cancel)*s<=0:raise ValueError('paper_cancel_order')
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
        spec=account_spec(c);leverage=plan.get('position_plan',{}).get('leverage',spec['leverage'])
        if isinstance(leverage,bool) or not isinstance(leverage,int) or not 1<=leverage<=spec.get('max_leverage',spec['leverage']):
            p['reason']='계좌 허용 레버리지 초과';save(c,p);return
        pp=plan['position_plan'];equity=account(c);used,risk=map(sum,zip(*(reserve(v) for v in states))) if states else (0,0)
        amount=equity*leverage*pp['initial_units']/100;add=equity*leverage*pp['add_units']/100 if x['add_enabled'] else 0
        proposed=amount*abs(plan['entry_preferred']-plan['stop'])/plan['entry_preferred']
        if add:proposed+=add*abs(pp['add_price']-plan['stop'])/pp['add_price']
        structural=spec.get('risk_policy')=='structural' and pp.get('risk_policy')=='structural'
        risk_available=equity*pp['risk_budget_units']/100 if structural else max(0,equity*.01-risk)
        factor=min(1,max(0,equity-used)*leverage/max(amount+add,1e-9),risk_available/max(proposed,1e-9))
        if equity<=0 or amount*factor<.01:p['reason']='공유 자금 또는 손실예산 부족';save(c,p);return
        if x['mode']=='market':
            bar=c.execute('SELECT * FROM candles WHERE symbol=? AND tf=? AND closed=1 AND close_t<=? ORDER BY t DESC LIMIT 1',(a['symbol'],x['confirmation_tf'],now*1000)).fetchone()
            confirmation=bar
            observed=a['snapshot'].get('frames',{}).get(x['confirmation_tf'],{}).get('last_closed')
            if observed:
                # The AI already observed the crossing. Do not demand a second crossing
                # just because another candle closed while inference was running.
                from .analysis import TF_MS
                confirmation=c.execute('SELECT * FROM candles WHERE symbol=? AND tf=? AND t=? AND closed=1 AND close_t<=?',(a['symbol'],x['confirmation_tf'],observed['t'],now*1000)).fetchone()
                if confirmation and now*1000-confirmation['close_t']>2*TF_MS[x['confirmation_tf']]:confirmation=None
            sign=1 if r['bias']=='bullish' else -1
            if not confirms_level(c,confirmation,x['confirmation_price'],sign,x.get('setup') in ('c_wave_reversal','wave4_reversal')) or not confirms_level(c,bar,x['confirmation_price'],sign):
                p['reason']='즉시 진입의 확정봉 조건 미충족';save(c,p);return
        p.update(risk_policy='structural' if structural else 'legacy',leverage=leverage,margin_mode=spec['mode'],maintenance_rate=spec.get('maintenance_rate',0),status='waiting' if x['mode'].startswith('close_then_') else 'armed',sign=1 if r['bias']=='bullish' else -1,limit=plan['entry_preferred'],stop=plan['stop'],tp1=plan['tp1'],tp2=plan['tp2'],take=plan['take_pct']/100,amount=amount*factor,add_amount=add*factor,add_limit=pp['add_price'] if add else 0,added=False,add_armed=None,qty=0,average=0,tp1_done=False,entry_time=None,armed_time=now if x['mode'] in ('limit','market') else None,last_t=(math.ceil(now/60)-1)*60000,expires=now+x['expires_hours']*3600,hold_hours=x['hold_hours'],rules=x,entry_low=plan.get('entry_low'),entry_high=plan.get('entry_high'))
        if leverage>1 and (p['stop']-liquidation_price(p,p['limit']))*p['sign']<=0:
            p['status']='skipped';p['reason']='손절이 격리 청산 추정선보다 멀어 진입 제외';save(c,p);return
        save(c,p);event(c,p,now,'planned',detail=x['reason'])

def confirms_level(c,row,level,sign,reversal=False):
    if not row or (row['c']-level)*sign<=0:return False
    if not reversal:return True
    if (row['c']-row['o'])*sign<=0:return False
    return (row['o']-level)*sign<=0

def confirmed(c,p,bar,add=False):
    x=p['rules'];level=x['add_confirmation_price'] if add else x['confirmation_price']
    after=p['entry_time'] if add else p['created']
    row=c.execute("SELECT * FROM candles WHERE symbol=? AND tf=? AND closed=1 AND close_t<=? AND close_t>? ORDER BY close_t DESC LIMIT 1",(p['symbol'],x['confirmation_tf'],bar['close_t'],after*1000)).fetchone()
    reversal=not add and x['mode'] in MARKET_MODES and x.get('setup') in ('c_wave_reversal','wave4_reversal')
    return bool(row and row['t']>=after*1000 and confirms_level(c,row,level,p['sign'],reversal))

def hit_stop(p,b):return b['l']<=p['stop'] if p['sign']==1 else b['h']>=p['stop']
def hit_target(p,b,level):return b['h']>=level if p['sign']==1 else b['l']<=level

def failed_structure(c,p,b):
    x=p['rules'];level=x.get('cancel_price')
    if level is None:return False
    # Only information known at this minute's open can cancel an already active order.
    cutoff=b['close_t'] if p['status']=='waiting' else b['t']-1
    row=c.execute('SELECT c FROM candles WHERE symbol=? AND tf=? AND closed=1 AND t>=? AND close_t<=? ORDER BY t DESC LIMIT 1',(p['symbol'],x['cancel_tf'],p['created']*1000,cutoff)).fetchone()
    return bool(row and (row['c']-level)*p['sign']<=0)

def market_amount(c,p,price):
    """Resize for the actual simulated fill, retaining the original loss budget."""
    others=[s for s in read_states(c) if s.get('id')!=p['id']]
    used=sum(reserve(s)[0] for s in others);risk=sum(reserve(s)[1] for s in others)
    equity=account(c);budget=p['amount']*abs(p['limit']-p['stop'])/p['limit']
    if p.get('risk_policy')!='structural':budget=min(budget,max(0,equity*.01-risk))
    return min(p['amount'],max(0,equity-used)*p.get('leverage',1),budget/(abs(price-p['stop'])/price))

def unrealized(p,price):
    pnl=p['qty']*(price-p['average'])*p['sign']
    return max(pnl,-p['qty']*p['average']/p['leverage']) if p.get('margin_mode')=='isolated' else pnl

def exit_qty(c,p,b,qty,price,kind,detail=''):
    pnl=qty*(price-p['average'])*p['sign']
    if p.get('margin_mode')=='isolated':pnl=max(pnl,-qty*p['average']/p['leverage'])
    p['qty']=max(0,p['qty']-qty)
    event(c,p,b['close_t']/1000,kind,price,qty,pnl,detail)
    if p['qty']<1e-12:p['status']='closed'

def step(c,p,b):
    now=b['close_t']/1000;p['last_t']=b['t']
    if p['status'] in ('waiting','armed'):
        decision_time=b['t']/1000 if p['status']=='armed' and p['rules']['mode'] in MARKET_MODES else now
        if decision_time>p['expires'] or (p['status']=='waiting' and hit_stop(p,b)) or (b['o']-p['stop'])*p['sign']<=0:
            p['status']='canceled';event(c,p,now,'cancel',detail='expired' if decision_time>p['expires'] else 'stop_invalidated');return
        if failed_structure(c,p,b):p['status']='canceled';event(c,p,now,'cancel',detail='structure_failure_before_entry');return
        if p['status']=='waiting':
            if confirmed(c,p,b):p['status']='armed';p['armed_time']=now;event(c,p,now,'armed',detail='closed_candle_confirmation')
            return # cannot fill on the candle that first confirms
        if b['t']/1000<=p['armed_time']:return
        if p['rules']['mode'] in MARKET_MODES:
            price=b['o'];risk=(price-p['stop'])*p['sign'];reward=(p['tp1']-price)*p['sign']
            deviation=(price-p['limit'])*p['sign']/p['limit']*100
            cancel=p['rules'].get('cancel_price')
            if (price-p['rules']['confirmation_price'])*p['sign']<=0 or (cancel is not None and (price-cancel)*p['sign']<=0):
                p['status']='canceled';event(c,p,now,'cancel',detail='reversal_or_breakout_failed_at_open');return
            if not p['entry_low']<=price<=p['entry_high'] or deviation>p['rules']['max_entry_deviation_pct'] or reward/risk<1.5:
                p['status']='canceled';event(c,p,now,'cancel',detail='entry_band_chase_or_rr_failed');return
            if p.get('margin_mode')=='isolated' and (p['stop']-liquidation_price(p,price))*p['sign']<=0:
                p['status']='canceled';event(c,p,now,'cancel',detail='stop_beyond_isolated_liquidation');return
            amount=market_amount(c,p,price)
            if amount<.01:p['status']='canceled';event(c,p,now,'cancel',detail='portfolio_risk_budget');return
            p.update(status='open',amount=amount,qty=amount/price,average=price,entry_time=b['t']/1000)
            event(c,p,b['t']/1000,'entry',price,p['qty'],detail='market_next_1m_open_after_confirmation')
            if hit_stop(p,b):exit_qty(c,p,b,p['qty'],p['stop'],'stop','entry_bar_stop_first')
            return
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
    if p.get('margin_mode')=='isolated' and (b['o']-liquidation_price(p))*p['sign']<=0:
        exit_qty(c,p,b,p['qty'],b['o'],'liquidation','isolated_gap_loss_capped_at_margin');return
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
        capital=account(c);spec=account_spec(c);states=read_states(c)
        events=[dict(r) for r in c.execute('SELECT * FROM paper_events WHERE created>=? AND id>? ORDER BY id DESC LIMIT 15',(now-21600,spec['event_floor']))]
    unreal=0;stale=False;positions=[]
    for p in states:
        if p.get('status')!='open':continue
        price=store.get('price:'+p['symbol'],{})
        if now-price.get('time',0)>30:stale=True
        mark=price.get('price',p['average']);pnl=unrealized(p,mark);unreal+=pnl
        positions.append(f"{p['symbol']} {'롱' if p['sign']==1 else '숏'} · 평균 {p['average']:,.2f} · 평가 {pnl:+.3f} USDT")
        positions.append(f"수량 {p['qty']:.6f} {p['symbol'].removesuffix('USDT')} · {p.get('leverage',1)}배 · 격리 증거금 {p['qty']*p['average']/p.get('leverage',1):,.2f} USDT")
        if full:positions.append(f"현재 스탑 {p['stop']:,.2f} · 잔량 목표 {p['tp2']:,.2f} · 포지션 명목액 {p['qty']*p['average']:.3f} USDT")
    reserved=sum(reserve(p)[0] for p in states if p.get('status') in ACTIVE)
    lines=['🧪 가상 매매 · 실제 주문 없음',f"{str(spec['leverage'])+'배' if not spec.get('max_leverage') else '거래별 1~'+str(spec['max_leverage'])+'배'} · {'격리 마진' if spec['mode']=='isolated' else '기존 계좌'}",f"총자산 {capital+unreal:,.2f} USDT / 시작 {spec['initial']:,.0f}",f"실현 {capital-spec['initial']:+.2f} · 평가 {unreal:+.2f} USDT",f'미배정 증거금 {max(0,capital-reserved):,.2f} USDT',f'조건 관찰 {sum(p.get("status")=="waiting" for p in states)}건 / 확인 완료·체결 대기 {sum(p.get("status")=="armed" for p in states)}건']
    if stale:lines.append('⚠ 시세 지연: 평가손익은 마지막 관측 가격 기준')
    lines+=positions or ['현재 보유 없음']
    if full:
        reasons={'queued':'새 기회 분석 요청','no_new_candidate':'새 유효 후보 없음','position_open':'기존 포지션 관리 중','analysis_in_progress':'분석 진행 중','paper_daily_budget':'기회 판단 하루 상한 도달','review_cooldown':'같은 종목 재판단 간격 대기'}
        for symbol in store.settings()['symbols']:
            scan=store.get('opportunity_status:'+symbol,{})
            if scan:lines.append(f"상시 탐색 {symbol}: {reasons.get(scan.get('reason'),scan.get('reason'))} · 후보 {len(scan.get('candidates',[]))}개")
        names={'planned':'계획 등록','armed':'진입 조건 확인','entry':'진입','add':'추가 진입','tp1':'1차 익절','tp2':'잔량 익절','stop':'손절','time_exit':'시간 만료 청산','cancel':'미체결 취소','gap_exit':'데이터 공백 후 첫 관측가 청산','liquidation':'격리 강제청산 모형','gap':'데이터 공백'}
        lines+=['','최근 6시간 기록']
        for e in reversed(events):
            stamp=datetime.fromtimestamp(e['created'],KST).strftime('%H:%M')
            lines.append(f"{stamp} {e['symbol']} {names.get(e['kind'],e['kind'])}"+(f" {e['price']:,.2f} · 거래금액 {e['qty']*e['price']:.3f} USDT · 손익 {e['pnl']:+.3f}" if e['price'] else ''))
        if not events:lines.append('새 거래 없음')
        for p in states:
            if p.get('status') in ('waiting','armed'):
                lines.extend(['',order_status(p),f"계획 명목액 {p['amount']:.3f} USDT / 손절 {p['stop']:,.2f}",f"1차 {p['tp1']:,.2f} ({p['take']*100:g}%) / 잔량 {p['tp2']:,.2f}",f"최대 보유 {p['hold_hours']:g}시간 · 조건: {p['reason']}"])
        for symbol in store.settings()['symbols']:
            latest=next((p for p in reversed(states) if p.get('symbol')==symbol),None)
            if latest and latest.get('status')=='skipped' and latest.get('reason')!='position_already_open':lines.extend(['',symbol+' · 미진입: '+latest.get('reason','실행 조건 없음')])
        lines+=['','수수료·펀딩 제외 / 1분 OHLC 가상 체결. 격리 손실은 해당 증거금 한도. 유지증거금률 0.5% 고정 모형이며 거래소 마크가격·구간별 실제 청산과 다를 수 있음. 같은 봉 손절·목표 동시 도달은 손절 우선. 과거 유리한 체결 소급 없음.']
    return '\n'.join(lines)

def order_status(p):
    side='롱' if p['sign']==1 else '숏'
    market=p['rules']['mode'] in MARKET_MODES
    setup={'c_wave_reversal':'C파 말단 반전','wave4_reversal':'4파 조정 후 반전','impulse_continuation':'추진파 돌파·가속','pullback':'눌림'}.get(p['rules'].get('setup'),'파동 계획')
    cancel=p['rules'].get('cancel_price')
    extra=f"\n진입 전 구조 실패: {p['rules']['cancel_tf']} 종가 {cancel:,.2f} {'이하' if p['sign']==1 else '이상'}면 취소" if cancel is not None else ''
    if market:
        trigger=f"{p['rules']['confirmation_tf']} 종가 {p['rules']['confirmation_price']:,.2f} {'위' if p['sign']==1 else '아래'}"
        state='조건 관찰 중' if p['status']=='waiting' else '확인 완료·진입 대기'
        return f"⚡ {p['symbol']} {side} · {setup} · {state}\n{trigger} 확인 후 다음 1분봉 시가로 가상 진입 · 지정가 재방문 불필요\n허용 {p['entry_low']:,.2f}~{p['entry_high']:,.2f} / 최대 이격 {p['rules']['max_entry_deviation_pct']:g}% / 1차 손익비 1.5R 이상"+extra
    if p['status']=='waiting':
        direction='위' if p['sign']==1 else '아래'
        return f"🔎 {p['symbol']} {side} · 조건 관찰 중, 지정가 미활성\n선행 조건: {p['rules']['confirmation_tf']} 종가 {p['rules']['confirmation_price']:,.2f} {direction}\n조건 충족 후 예정가 {p['limit']:,.2f} · 지금 이 가격을 지나도 체결하지 않음"+extra
    return f"📌 {p['symbol']} {side} · 활성 지정가 {p['limit']:,.2f}\n이후 가격 도달 시 가상 체결 (1분봉 기준)"+extra

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
            if p['status'] in ('waiting','armed') and p['rules'].get('conditions_fully_encoded') is not True:
                p['status']='canceled';p['block_reason']='필수 조건의 수치 실행 가능 여부 미검증';event(c,p,now,'cancel',detail='unencoded_conditions');save(c,p);continue
            if paused and p['status']!='open':
                p['status']='canceled';event(c,p,now,'cancel',detail='paused');save(c,p);continue
            bars=c.execute("SELECT * FROM candles WHERE symbol=? AND tf='1m' AND closed=1 AND t>? AND close_t<=? ORDER BY t",(p['symbol'],p['last_t'],now*1000)).fetchall()
            for row in bars:
                b=dict(row)
                if b['t']>p['last_t']+60000:
                    event(c,p,b['t']/1000,'gap',detail='missing_1m_bars')
                    if p['status']!='open':
                        p['status']='canceled';event(c,p,b['t']/1000,'cancel',detail='missing_1m_bars');break
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
