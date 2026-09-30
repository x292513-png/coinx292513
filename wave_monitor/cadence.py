"""Quiet scheduled briefings; sharp-move alerts never depend on AI availability."""
from datetime import datetime,timezone,timedelta
from . import store

KST=timezone(timedelta(hours=9))
def enabled():return store.settings().get('notification_mode') in ('hourly','twice_daily')

def briefing_slot(now,cfg):
    local=datetime.fromtimestamp(now,KST)
    if cfg.get('notification_mode')=='hourly':return local.strftime('%Y-%m-%d-%H')
    if local.hour in cfg.get('briefing_hours_kst',[9,21]):return local.strftime('%Y-%m-%d-%H')
    return None

def refresh_slot(now,cfg):
    local=datetime.fromtimestamp(now,KST)
    if cfg.get('notification_mode')=='hourly':
        return local.strftime('%Y-%m-%d-%H') if local.minute>=55 else None
    next_hour=(local.hour+1)%24
    if local.minute>=55 and next_hour in cfg.get('briefing_hours_kst',[9,21]):
        return local.strftime('%Y-%m-%d-')+str(next_hour).zfill(2)
    return None

def next_briefing(now,cfg):
    local=datetime.fromtimestamp(now,KST)
    hours=sorted(cfg.get('briefing_hours_kst',[9,21]))
    for day_offset in (0,1):
        day=local.date()+timedelta(days=day_offset)
        for hour in hours:
            candidate=datetime(day.year,day.month,day.day,hour,tzinfo=KST)
            if candidate>local:return candidate

def changes(symbol,price,now):
    out={}
    with store.db() as c:
        for minutes in (5,15,60):
            target=(now-minutes*60)*1000
            row=c.execute("SELECT t,o FROM candles WHERE symbol=? AND tf='1m' AND t<=? AND t>=? ORDER BY t DESC LIMIT 1",(symbol,target,target-90000)).fetchone()
            if row and row['o']>0:out[minutes]=(price/row['o']-1)*100
    return out

def sharp_candidate(moves,rules):
    hits=[(minutes,moves[minutes]) for minutes,threshold in rules if minutes in moves and abs(moves[minutes])>=threshold]
    return max(hits,key=lambda x:abs(x[1])) if hits else None

def can_alert(previous,now,change,cooldown):
    return not previous or now-previous['time']>=cooldown or change*previous['change']<0 or abs(change)>=abs(previous['change'])+1

def briefing(now):
    from .engine import is_invalid
    lines=['🕐 현재 상황 브리핑 · '+datetime.fromtimestamp(now,KST).strftime('%m/%d %H:%M KST')]
    for symbol in store.settings()['symbols']:
        p=store.get('price:'+symbol,{})
        if now-p.get('time',0)>30:
            lines += ['',symbol+' · 실시간 데이터 지연, 현재 판단 보류'];continue
        price=p['price'];moves=changes(symbol,price,now)
        lines += ['',f"📍 {symbol} · {price:,.2f}",' · '.join(f'{m}분 {v:+.2f}%' for m,v in moves.items()) or '변동률 기준 데이터 수집 중']
        with store.db() as c:
            span=c.execute("SELECT MIN(l),MAX(h),COUNT(*) FROM candles WHERE symbol=? AND tf='1m' AND t>=?",(symbol,(now-3600)*1000)).fetchone()
        if span[2]>=58:lines.append(f'최근 1시간 범위 {span[0]:,.2f}–{span[1]:,.2f}')
        a=store.latest(symbol)
        if not a:lines.append('AI 해석 기록 대기');continue
        r=a['result'];stamp=datetime.fromtimestamp(a['created'],KST).strftime('%m/%d %H:%M')
        # Do not reference an unpublished report: that would cause an extra archive notification.
        from .message_links import existing
        reference=f"분석 #{a['id']}" if existing(a['id']) else '저장된 AI 해석'
        invalid=bool(store.get('invalidated:'+str(a['id']))) or is_invalid(r,price)
        lines.append(f"{reference} · {stamp} 기준 · "+('무효화됨, 새 판단 대기' if invalid else '이전 해석 참고'))
        if invalid or now-a['created']>7200:
            lines.append('새 AI 해석 대기 · 이전 진입 조건은 현재 신호로 사용하지 않습니다.')
            continue
        lines.append('🧭 '+r.get('headline','')[:100])
        if r.get('thesis'):lines.append('내 판단: '+r['thesis'][:160])
        if r.get('fractal_comment') and r.get('fractal_evidence'):lines.append('🔁 과거 비교: '+r['fractal_comment'][:140])
        from .trade_plan import format_plan
        plan=format_plan(r,compact=True)
        if plan:lines.append(plan)
        zones=[] if plan else r.get('zones',[])[:3]
        for z in zones:
            role={'support':'지지','resistance':'저항','watch':'관찰'}.get(z['role'],z['role'])
            lines.append(f"• {role} {z['low']:,.2f}–{z['high']:,.2f}"+(' (이전 분석)' if invalid else ''))
        lines.append('다음 확인: '+r.get('next_watch',r.get('confirmation_rule',''))[:120])
        if r.get('invalidation_price'):
            side='하회' if r['invalidation_side']=='below' else '상회'
            lines.append(f"관점 철회: {r['invalidation_price']:,.2f} {side}")
    hours=store.settings().get('briefing_hours_kst',[9,21])
    schedule='·'.join(f'{hour:02d}:00' for hour in hours)
    lines += ['',f'정기 브리핑은 하루 2회 ({schedule} KST) · 급변만 별도 알림. AI 해석 시각과 현재 가격 시각은 다를 수 있어요.']
    return '\n'.join(lines)

def tick(now):
    cfg=store.settings()
    if not enabled() or store.get('paused',False):return
    for symbol in cfg['symbols']:
        p=store.get('price:'+symbol,{})
        if now-p.get('time',0)>30:continue
        moves=changes(symbol,p['price'],now)
        hit=sharp_candidate(moves,cfg['sharp_move_rules'])
        if hit:
            minutes,change=hit;previous=store.get('sharp_alert:'+symbol)
            if can_alert(previous,now,change,cfg['sharp_alert_cooldown_seconds']):
                store.enqueue_message(f"🚨 {symbol} 급변 · {minutes}분 {change:+.2f}%\n현재 {p['price']:,.2f}\n실시간 가격 기준 알림입니다. AI의 새 파동 판단은 아직 확인되지 않았습니다.")
                store.put('sharp_alert:'+symbol,{'time':now,'change':change})
    # Refresh silently five minutes before a scheduled briefing.
    refresh=refresh_slot(now,cfg)
    if refresh and store.get('briefing_ai_slot')!=refresh:
        from .budget import day_start
        with store.db() as c:used=c.execute("SELECT COUNT(*) FROM calls WHERE kind='auto' AND started>=?",(day_start(now),)).fetchone()[0]
        if used<cfg['auto_calls_per_day']:
            for symbol in cfg['symbols']:store.queue(symbol,'hourly_refresh')
        store.put('briefing_ai_slot',refresh)
    slot=briefing_slot(now,cfg)
    if slot and store.get('briefing_sent_slot')!=slot:
        from .presentation import pack
        from html import escape
        store.enqueue_message(pack([escape(briefing(now))]));store.put('briefing_sent_slot',slot)
