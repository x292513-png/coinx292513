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


def consider(snap,raw,now):
    cfg=store.settings()
    if not cfg.get('paper_opportunity_enabled',False) or not cfg.get('paper_enabled') or store.get('paused',False):return
    symbol=snap['symbol'];bar=raw['5m'][-1];key='opportunity_bar:'+symbol
    if store.get(key)==bar['close_t']:return
    if now-snap['price']['time']>30 or not 0<=now-bar['close_t']/1000<=90:return
    for tf in ('5m','15m','1h'):
        rows=raw.get(tf,[])
        if not rows or now*1000-rows[-1]['close_t']>TF_MS[tf]+90000:return
        tail=rows[-12:]
        if any(b['t']-a['t']!=TF_MS[tf] for a,b in zip(tail,tail[1:])):return
    from .budget import day_start
    from .paper import read_states
    events=candidates(snap,raw)
    fresh=[e for e in events if now-store.get('opportunity_seen:'+symbol+':'+e['key'],0)>=3600]
    status={'time':now,'bar':bar['close_t'],'candidates':events,'reason':'no_new_candidate'}
    with store.db() as c:
        busy=any(p.get('symbol')==symbol and p.get('status')=='open' for p in read_states(c))
        pending=c.execute("SELECT COUNT(*) FROM jobs WHERE symbol=? AND status IN ('pending','running')",(symbol,)).fetchone()[0]
        used=c.execute("SELECT COUNT(*) FROM calls WHERE kind='paper' AND started>=?",(day_start(now),)).fetchone()[0]
        reserved=c.execute("SELECT COUNT(*) FROM jobs WHERE kind='paper' AND status IN ('pending','running')").fetchone()[0]
    if busy:status['reason']='position_open'
    elif pending:status['reason']='analysis_in_progress'
    elif used+reserved>=cfg.get('paper_calls_per_day',12):status['reason']='paper_daily_budget'
    elif now-store.get('opportunity_queued:'+symbol,0)<cfg.get('paper_review_min_seconds',900):status['reason']='review_cooldown'
    elif fresh:
        question=('상시 가상매매 기회 검토. 아래 후보는 매수/매도 지시가 아니라 측정된 변화다. '
          '서적 판단 절차와 일봉→4h→1h→15m 맥락으로 롱·숏·대기를 비교하고, 5m/15m 국소 거래도 검토하라. '
          '임펄스 지속/4파 종료, C 말단·복합조정 반등, 채널·피보나치·ICT 반응, 돌파·실패 돌파, 다이버전스를 함께 비교한다. '
          '이미 반전이 확인됐으면 즉시 진입의 실제 가격 손익비와 재시험 대기의 기회비용을 비교한다. '
          '재시험을 무조건 요구하지 말며, 종가 확인 후 한참 아래 재매수만 고집하지 않는다. '
          '거래횟수를 채우려고 진입하거나 파동 완료를 꾸미지 않는다. 대기라면 구체적으로 무엇이 부족한지 적는다. '
          '현재 관측 가격 기준의 실행 가능한 계획을 선택하고 1차 목표 앞 저항, 구조 손절, 짧은 역추세/추세순응 여부를 명시한다. 후보:\n'
          +json.dumps(fresh[:12],ensure_ascii=False))
        jid=store.queue(symbol,'paper_opportunity','paper',question)
        status.update(reason='queued',job_id=jid)
        store.put('opportunity_queued:'+symbol,now)
        for e in fresh:store.put('opportunity_seen:'+symbol+':'+e['key'],now)
    store.put('opportunity_status:'+symbol,status);store.put(key,bar['close_t'])
