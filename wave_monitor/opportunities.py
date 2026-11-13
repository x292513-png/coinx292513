"""Broad, event-driven paper review; measurements nominate, book-aware AI decides."""
import json
from . import store
from .analysis import TF_MS


def candidates(snap, raw):
    found=[]
    def add(kind,tf,anchor,detail):
        found.append({'kind':kind,'tf':tf,'key':f'{kind}:{tf}:{anchor}','detail':detail})
    for tf in ('5m','15m','1h'):
        rows=raw.get(tf,[]);frame=snap['frames'].get(tf,{})
        if len(rows)<3:continue
        prev,bar=rows[-2:];atr=frame.get('atr14',0)
        if atr<=0:continue
        points=[p for p in frame.get('pivots',[]) if p.get('confirmed') and (p.get('confirmed_at') or 0)<=bar['close_t']]
        move=(bar['c']/bar['o']-1)*100
        if abs(move)>={'5m':.8,'15m':1.2,'1h':2}[tf]:
            add('displacement',tf,bar['t'],{'change_pct':round(move,3),'close':bar['c'],'atr':atr})
        for d in frame.get('divergences',[]):
            if d.get('status')=='confirmed_pivots' and d['points'][-1].get('confirmed_at',0)>=bar['close_t']-2*TF_MS[tf]:
                add('divergence',tf,str(d['points'][-1]['t'])+d['type'],d)
        for pattern in frame.get('candidates',[]):
            pts=pattern.get('points',[])
            if pts and all(p.get('confirmed') for p in pts) and pts[-1].get('confirmed_at',0)>=bar['close_t']-2*TF_MS[tf]:
                add('wave_structure',tf,str(pts[-1]['t'])+pattern['pattern'],pattern)
        for kind,sign in [('H',1),('L',-1)]:
            pivot=next((p for p in reversed(points) if p['kind']==kind and p.get('confirmed_at',0)<bar['t']),None)
            if pivot and (prev['c']-pivot['price'])*sign<=0<(bar['c']-pivot['price'])*sign:
                add('swing_breakout',tf,pivot['t'],{'direction':sign,'pivot':pivot,'close':bar['c']})
        directional=1 if bar['c']>bar['o'] else -1 if bar['c']<bar['o'] else 0
        if not directional:continue
        # A touch alone is not an entry. Look for a directional close back across the reference.
        references=[]
        for m in snap.get('entry_measurements',{}).get('levels',[]):
            if m['tf']!=tf:continue
            if m['kind']=='channel':
                references.extend((m['id']+':'+edge,m[edge],'channel',m) for edge in ('lower','mid','upper'))
            elif m['kind'] in ('retracement','moving_average'):
                references.append((m['id'],m['price'],m['kind'],m))
        for z in frame.get('ict',{}).get('active',[]):
            references.append((z['id'],z['mid'],z['kind'],z))
        relevant=[(key,level,kind,m) for key,level,kind,m in references if bar['l']<=level<=bar['h']
                  and (bar['c']-level)*directional>0 and abs(bar['c']-level)<=atr*.75]
        # Keep diverse reference families instead of filling the prompt with near-identical Fibonacci anchors.
        seen=set()
        for key,level,kind,m in sorted(relevant,key=lambda x:abs(x[1]-bar['c'])):
            if kind in seen:continue
            seen.add(kind)
            add('reference_reaction',tf,key,{'family':kind,'direction':directional,'level':level,'measurement':m})
    return found


def meaningful_events(snap, raw, states, now):
    """Price-only wakeups. No model calls for new labels inside an unchanged box."""
    symbol=snap['symbol'];price=snap['price']['price'];rows=raw['5m']
    atr=snap['frames'].get('5m',{}).get('atr14',0)
    baseline=store.get('opportunity_baseline:'+symbol,{})
    if not baseline:
        latest=store.latest(symbol)
        if latest and latest.get('snapshot',{}).get('price',{}).get('price'):
            baseline={'price':latest['snapshot']['price']['price'],'time':latest['created']}
            store.put('opportunity_baseline:'+symbol,baseline)
    previous=store.get('opportunity_tick:'+symbol,{});previous_price=previous.get('price')
    store.put('opportunity_tick:'+symbol,{'price':price,'time':now})
    events=[]
    # Use rolling closed 1-minute observations, not the current candle's open.
    minutes=raw.get('1m',[])
    if minutes and 0<=now-minutes[-1]['close_t']/1000<=90:
        for window,threshold in store.settings().get('sharp_move_rules',[[5,2],[15,3],[60,4]]):
            start=now-window*60
            anchor=next((b for b in reversed(minutes) if b['t']/1000<=start),None)
            if anchor and 0<=start-anchor['t']/1000<90 and anchor['o']>0:
                move=(price/anchor['o']-1)*100
                if abs(move)>=threshold:
                    events.append({'kind':'sharp_move','tf':str(window)+'m','key':'sharp:'+str(window)+':'+str(1 if move>0 else -1),
                                   'detail':{'change_pct':round(move,3),'price':price},'urgent':True})
    # Also catch a gradual large move since the last analysis, not just a fast candle.
    if baseline.get('price') and abs(price/baseline['price']-1)>=.02:
        events.append({'kind':'price_change','tf':'live','key':'move:'+str(baseline['time']),
                       'detail':{'from':baseline['price'],'to':price},'urgent':True})
    if previous_price and now-previous.get('time',0)<=120:
        for state in states:
            if state.get('symbol')!=symbol or state.get('status') not in ('waiting','armed','open'):continue
            levels={k:state.get(k) for k in ('entry_low','entry_high','stop','tp1','tp2','emergency_stop')}
            levels.update({k:state.get('rules',{}).get(k) for k in ('confirmation_price','cancel_price')})
            for name,level in levels.items():
                if isinstance(level,(int,float)) and level>0 and (previous_price-level)*(price-level)<0:
                    events.append({'kind':'plan_cross','tf':'live','key':f"plan:{state.get('id')}:{name}:{level}:{price>level}",
                                   'detail':{'level':level,'name':name,'price':price},'urgent':True})
    low=min(b['l'] for b in rows[-13:-1]);high=max(b['h'] for b in rows[-13:-1])
    near_edge=price<=low+atr*.25 or price>=high-atr*.25
    moved=not baseline or abs(price-baseline['price'])>=max(atr*.75,price*.0025)
    for event in candidates(snap,raw):
        kind=event['kind']
        if kind=='displacement' or (kind=='swing_breakout' and moved) or (near_edge and moved):
            events.append(event)
    return events


def consider(snap,raw,now):
    cfg=store.settings()
    if not cfg.get('paper_opportunity_enabled',False) or not cfg.get('paper_enabled') or store.get('paused',False):return
    symbol=snap['symbol'];bar=raw['5m'][-1];key='opportunity_bar:'+symbol
    if now-snap['price']['time']>30 or not 0<=now-bar['close_t']/1000<=390:return
    for tf in ('5m','15m','1h'):
        rows=raw.get(tf,[])
        if not rows or now*1000-rows[-1]['close_t']>TF_MS[tf]+90000:return
        tail=rows[-12:]
        if any(b['t']-a['t']!=TF_MS[tf] for a,b in zip(tail,tail[1:])):return
    from .budget import day_start
    from .paper import read_states
    with store.db() as c:
        states=read_states(c)
        pending=c.execute("SELECT COUNT(*) FROM jobs WHERE symbol=? AND status IN ('pending','running')",(symbol,)).fetchone()[0]
        used=c.execute("SELECT COUNT(*) FROM calls WHERE kind='paper' AND started>=?",(day_start(now),)).fetchone()[0]
        reserved=c.execute("SELECT COUNT(*) FROM jobs WHERE kind='paper' AND status IN ('pending','running')").fetchone()[0]
    busy=any(p.get('symbol')==symbol and p.get('status')=='open' for p in states)
    events=meaningful_events(snap,raw,states,now)
    latched={e['key']:e for e in store.get('opportunity_latched:'+symbol,[]) if now-e['detected_at']<=900}
    for e in events:
        if e['kind']=='plan_cross':latched[e['key']]=dict(e,detected_at=now)
    events=[e for e in events if e['kind']!='plan_cross']+list(latched.values())
    store.put('opportunity_latched:'+symbol,list(latched.values()))
    baseline=store.get('opportunity_baseline:'+symbol,{})
    price=snap['price']['price']
    fresh=[]
    for e in events:
        seen=store.get('opportunity_seen:'+symbol+':'+e['key'],0)
        if e.get('urgent'):
            # A sustained alert is one event; rearm after another 1% price change.
            changed=not baseline or abs(price/baseline['price']-1)>=.01
            if not seen or (changed and now-seen>=300):fresh.append(e)
        elif not seen or now-seen>=86400:fresh.append(e)
    urgent=any(e.get('urgent') for e in fresh)
    status={'time':now,'bar':bar['close_t'],'candidates':events,'reason':'no_new_candidate','urgent':urgent}
    limit=cfg.get('paper_calls_per_day',12)+(cfg.get('paper_urgent_reserve',8) if urgent else 0)
    cooldown=300 if urgent else cfg.get('paper_review_min_seconds',900)
    if pending:status['reason']='analysis_in_progress'
    elif fresh and used+reserved>=limit:status['reason']='paper_daily_budget'
    elif fresh and now-store.get('opportunity_queued:'+symbol,0)<cooldown:status['reason']='review_cooldown'
    elif busy and fresh:
        jid=store.queue(symbol,'paper_management_urgent' if urgent else 'paper_management','paper','보유 포지션의 가설 유효성, 유지/축소/청산/추가 진입을 최신 차트로 재평가. '+json.dumps(fresh[:12],ensure_ascii=False))
        status.update(reason='management_queued',job_id=jid)
        store.put('management_queued:'+symbol,now);store.put('opportunity_queued:'+symbol,now)
        store.put('opportunity_baseline:'+symbol,{'price':price,'time':now})
        store.put('opportunity_latched:'+symbol,[])
        for e in fresh:store.put('opportunity_seen:'+symbol+':'+e['key'],now)
    elif busy:status['reason']='position_open'
    elif fresh:
        question=('상시 가상매매 기회 검토. 아래 후보는 매수/매도 지시가 아니라 측정된 변화다. '
          '서적 판단 절차와 일봉→4h→1h→15m 맥락으로 롱·숏·대기를 비교하고, 5m/15m 국소 거래도 검토하라. '
          '임펄스 지속/4파 종료, C 말단·복합조정 반등, 채널·피보나치·ICT 반응, 돌파·실패 돌파, 다이버전스를 함께 비교한다. '
          '이미 반전이 확인됐으면 즉시 진입의 실제 가격 손익비와 재시험 대기의 기회비용을 비교한다. '
          '재시험을 무조건 요구하지 말며, 종가 확인 후 한참 아래 재매수만 고집하지 않는다. '
          '거래횟수를 채우려고 진입하거나 파동 완료를 꾸미지 않는다. 대기라면 구체적으로 무엇이 부족한지 적는다. '
          '현재 관측 가격 기준의 실행 가능한 계획을 선택하고 1차 목표 앞 저항, 구조 손절, 짧은 역추세/추세순응 여부를 명시한다. 후보:\n'
          +json.dumps(fresh[:12],ensure_ascii=False))
        jid=store.queue(symbol,'paper_opportunity_urgent' if urgent else 'paper_opportunity','paper',question)
        status.update(reason='queued',job_id=jid)
        store.put('opportunity_queued:'+symbol,now)
        store.put('opportunity_baseline:'+symbol,{'price':price,'time':now})
        store.put('opportunity_latched:'+symbol,[])
        for e in fresh:store.put('opportunity_seen:'+symbol+':'+e['key'],now)
    store.put('opportunity_status:'+symbol,status);store.put(key,bar['close_t'])
