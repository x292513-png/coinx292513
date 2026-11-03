"""Persistent, source-separated historical research. No AI calls or model training.

All feature windows end before their outcomes. Retrieval excludes overlapping
episodes and the current query window. Empirical rates are descriptive, not odds.
"""
import asyncio
import json
import logging
import math
import sqlite3
import time
from collections import Counter
from datetime import datetime, timezone
import numpy as np
from aiohttp import ClientSession, ClientTimeout
from . import store
from .net import connector
from .analysis import indicators, pivots

log=logging.getLogger('wave.learning')
FRAMES=['1M','1w','1d','4h']
HORIZONS={'1M':3,'1w':4,'1d':7,'4h':12}
ENDPOINTS={'futures':'https://fapi.binance.com/fapi/v1/klines','spot':'https://data-api.binance.vision/api/v3/klines'}


def db():
    c=sqlite3.connect(store.ROOT/'data/history.sqlite3',timeout=30);c.row_factory=sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('CREATE TABLE IF NOT EXISTS bars(market TEXT,symbol TEXT,tf TEXT,t INTEGER,o REAL,h REAL,l REAL,c REAL,v REAL,close_t INTEGER,PRIMARY KEY(market,symbol,tf,t))')
    c.execute('CREATE TABLE IF NOT EXISTS samples(market TEXT,symbol TEXT,tf TEXT,kind TEXT,t INTEGER,known_until INTEGER,data TEXT,PRIMARY KEY(market,symbol,tf,kind,t))')
    return c


def history(market,symbol,tf):
    with db() as c:return [dict(x) for x in c.execute('SELECT * FROM bars WHERE market=? AND symbol=? AND tf=? ORDER BY t',(market,symbol,tf))]


async def download(session,market,symbol,tf):
    with db() as c:
        last=c.execute('SELECT MAX(t) FROM bars WHERE market=? AND symbol=? AND tf=?',(market,symbol,tf)).fetchone()[0]
    cursor=last+1 if last else 0;total=0
    while True:
        params={'symbol':symbol,'interval':tf,'startTime':cursor,'limit':1000}
        for attempt in range(5):
            try:
                async with session.get(ENDPOINTS[market],params=params) as response:
                    if response.status!=200:raise RuntimeError('history_http_'+str(response.status))
                    data=await response.json()
                    if not isinstance(data,list):raise ValueError('history_shape')
                break
            except (OSError,asyncio.TimeoutError,RuntimeError):
                if attempt==4:raise
                await asyncio.sleep(min(30,2**attempt*2))
        now=int(time.time()*1000)
        clean=[]
        for x in data:
            t=int(x[0]);ct=int(x[6]);o,h,l,close,v=map(float,x[1:6])
            if ct>=now:continue
            if not all(math.isfinite(a) for a in [o,h,l,close,v]) or not (0<l<=min(o,close)<=max(o,close)<=h and v>=0):raise ValueError('history_ohlcv')
            if t<cursor or ct<t:raise ValueError('history_timestamp')
            clean.append((market,symbol,tf,t,o,h,l,close,v,ct))
        if clean:
            with db() as c:c.executemany('INSERT OR REPLACE INTO bars VALUES (?,?,?,?,?,?,?,?,?,?)',clean)
            total+=len(clean)
        if not data or len(data)<1000 or not clean:break
        new=int(data[-1][0])+1
        if new<=cursor:raise ValueError('history_no_progress')
        cursor=new
        await asyncio.sleep(.4)
    log.info('history_downloaded %s %s %s added=%s',market,symbol,tf,total)


def contiguous(rows):
    # A month has variable duration; exchange close_t is the authoritative boundary.
    return all(b['t']==a['close_t']+1 for a,b in zip(rows,rows[1:]))


def fvg_samples(rows,atr,horizon=24):
    out=[];last_end={'bullish':-1,'bearish':-1}
    for i in range(16,len(rows)-horizon):
        a,b,c=rows[i-2:i+1];v=float(atr[i])
        if not math.isfinite(v) or v<=0:continue
        if c['l']>a['h']:side=1;lo,hi=a['h'],c['l'];direction='bullish'
        elif c['h']<a['l']:side=-1;lo,hi=c['h'],a['l'];direction='bearish'
        else:continue
        if hi-lo<v*.1 or side*(b['c']-b['o'])<v*.8 or i<=last_end[direction]:continue
        future=rows[i+1:i+horizon+1]
        if not contiguous(rows[i-2:i+horizon+1]):continue
        mid=(lo+hi)/2;touch=None;invalid=False;early=False;reaction=False;ambiguous=False
        for j,r in enumerate(future):
            reached=r['l']<=mid if side==1 else r['h']>=mid
            broken=r['c']<lo if side==1 else r['c']>hi
            continued=side*(r['c']-c['c'])>=v
            if touch is None:
                if reached:touch=j
                elif continued:early=True
            if touch is not None and j>touch and side*(r['c']-mid)>=v*.5:reaction=True
            if broken:
                invalid=True
                if touch==j:ambiguous=True
                break
            if reaction:break
        state='same_bar_touch_and_invalid' if ambiguous else ('reaction_after_CE' if reaction else ('invalidated' if invalid else ('CE_touch_no_reaction_yet' if touch is not None else 'no_CE_touch')))
        out.append({'kind':'FVG_'+direction,'t':c['close_t'],'known_until':future[-1]['close_t'],'outcome':state,'continued_before_CE':early,'CE_touched':touch is not None,'CE':mid,'horizon_bars':horizon})
        last_end[direction]=i+horizon
    return out


def triangle_samples(rows,atr,horizon=24):
    # Full causal pivots returned by the same live reversal detector.
    points=[p for p in pivots(rows,1.5,limit=None) if p['confirmed']]
    close_index={r['close_t']:i for i,r in enumerate(rows)};open_index={r['t']:i for i,r in enumerate(rows)};out=[];busy=-1
    for k in range(3,len(points)):
        a,b,c,d=points[k-3:k+1]
        if a['kind']!=c['kind'] or b['kind']!=d['kind'] or a['kind']==b['kind']:continue
        highs=[p['price'] for p in [a,b,c,d] if p['kind']=='H'];lows=[p['price'] for p in [a,b,c,d] if p['kind']=='L']
        if not (highs[1]<highs[0] and lows[1]>lows[0]):continue
        i=close_index[d['confirmed_at']]
        if i<=busy or i+horizon>=len(rows) or not contiguous(rows[open_index[a['t']]:i+horizon+1]):continue
        v=float(atr[i]);side=1 if a['kind']=='L' else -1
        if not math.isfinite(v) or v<=0:continue
        slope=(c['price']-a['price'])/(c['t']-a['t'])
        slope2=(d['price']-b['price'])/(d['t']-b['t'])
        nearest=1e9;outcome='no_reversal_in_window';distance=None
        for r in rows[i+1:i+horizon+1]:
            line=c['price']+slope*(r['t']-c['t'])
            other=d['price']+slope2*(r['t']-d['t'])
            if side*(other-line)<=0:outcome='past_triangle_apex';break
            extreme=r['l'] if side==1 else r['h']
            nearest=min(nearest,side*(extreme-line)/v)
            if nearest<=.75 and side*(r['c']-line)/v>=nearest+.5:
                distance=round(nearest,3)
                outcome='early_reversal' if nearest>.15 else ('line_overshoot_reversal' if nearest<-.15 else 'line_touch_reversal')
                break
        out.append({'kind':'contracting_triangle_AC_projection','t':rows[i]['close_t'],'known_until':rows[i+horizon]['close_t'],'outcome':outcome,'distance_ATR':distance,'horizon_bars':horizon,'definition':'four confirmed alternating contracting pivots; projected A-C boundary; reversal close >=0.5 ATR from observed extreme, near <=0.75 ATR; early >0.15 ATR'})
        busy=i+horizon
    return out


def stats(samples,now_ms):
    result={}
    for kind in sorted({s['kind'] for s in samples}):
        groups={}
        for label,days,older in [('recent_90d',90,False),('recent_365d',365,False),('before_90d',90,True),('before_365d',365,True),('all',None,False)]:
            ss=[s for s in samples if s['kind']==kind and s['known_until']<=now_ms and (days is None or ((s['t']<now_ms-days*86400000) if older else (s['t']>=now_ms-days*86400000)))]
            counts=dict(Counter(x['outcome'] for x in ss))
            groups[label]={'n':len(ss),'counts':counts,'continued_before_CE':sum(bool(x.get('continued_before_CE')) for x in ss),'small_sample':len(ss)<20}
        result[kind]=groups
    return result


def period_stats(groups):
    """Compatible with old summaries; disjoint periods, descriptive outcome fractions."""
    import copy
    groups=copy.deepcopy(groups)
    for buckets in groups.values():
        recent=buckets.get('recent_365d',{});total=buckets.get('all',{})
        if 'before_365d' not in buckets:
            n=max(0,total.get('n',0)-recent.get('n',0))
            buckets['before_365d']={'n':n,'small_sample':n<20,'counts':{k:max(0,v-recent.get('counts',{}).get(k,0)) for k,v in total.get('counts',{}).items()}}
        for key in ('recent_365d','before_365d'):
            b=buckets.get(key,{})
            b['outcome_fractions']={k:round(v/b['n'],3) for k,v in b.get('counts',{}).items()} if b.get('n') else {}
    return groups


def analogs(rows,query,horizon,asof_ms,limit=12):
    window=min(32,len(query));query=query[-window:]
    if window<16 or len(rows)<window+horizon:return {'n':0,'reason':'insufficient_history'}
    if not contiguous(query):return {'n':0,'reason':'current_query_has_data_gap'}
    qc=np.array([r['c'] for r in query]);qr=np.diff(np.log(qc));scale=max(float(qr.std()),1e-6)
    qshape=np.log(qc/qc[0])/scale
    prices=np.array([r['c'] for r in rows]);windows=np.lib.stride_tricks.sliding_window_view(prices,window)
    logreturns=np.diff(np.log(windows),axis=1);scales=np.maximum(logreturns.std(axis=1),1e-6)
    shapes=np.log(windows/windows[:,0,None])/scales[:,None]
    distances=np.mean((shapes-qshape)**2,axis=1)**.5+.2*np.abs(np.log(scales/scale))
    chosen=[];occupied=[];query_start=query[0]['t']
    for start in np.argsort(distances):
        start=int(start);end=start+window-1;future=end+horizon
        if future>=len(rows) or rows[future]['close_t']>=min(query_start,asof_ms):continue
        if any(not(future<a or start>b) for a,b in occupied):continue
        if not contiguous(rows[start:future+1]):continue
        age=(asof_ms-rows[end]['close_t'])/86400000
        chosen.append({'end':rows[end]['close_t'],'outcome_end':rows[future]['close_t'],'distance':round(float(distances[start]),4),'return_pct':round((prices[future]/prices[end]-1)*100,3),'weight':round(.25+.75*math.exp(-age/365),4)})
        occupied.append((start,future))
        if len(chosen)>=limit:break
    if not chosen:return {'n':0,'reason':'no_nonoverlapping_past_matches'}
    returns=np.array([x['return_pct'] for x in chosen]);weights=np.array([x['weight'] for x in chosen])
    return {'n':len(chosen),'window_bars':window,'horizon_bars':horizon,'weighted_up_fraction':round(float(np.average(returns>0,weights=weights)),3),'weighted_return_pct':round(float(np.average(returns,weights=weights)),3),'return_quartiles_pct':np.round(np.quantile(returns,[.25,.5,.75]),3).tolist(),'examples':chosen[:3],'warning':'nearest shape matches, not validated prediction probability; same-price correlation across spot/futures, never add their sample counts'}


def summarize():
    now=int(time.time()*1000);result={'updated_at':time.time(),'sources':{},'method_version':1,'scope':'Binance available listing history only, spot and futures kept separate. No pre-Binance history.'}
    for market in ENDPOINTS:
        for symbol in store.settings()['symbols']:
            for tf in FRAMES:
                rows=history(market,symbol,tf)
                if not rows:continue
                rsi,atr=indicators(rows)
                observations=fvg_samples(rows,atr)+triangle_samples(rows,atr)
                with db() as c:
                    c.executemany('INSERT OR REPLACE INTO samples VALUES (?,?,?,?,?,?,?)',[(market,symbol,tf,o['kind'],o['t'],o['known_until'],json.dumps(o)) for o in observations])
                gaps=sum(b['t']!=a['close_t']+1 for a,b in zip(rows,rows[1:]))
                result['sources'][f'{market}:{symbol}:{tf}']={'bars':len(rows),'first':rows[0]['t'],'last_closed':rows[-1]['close_t'],'gaps':gaps,'stats':stats(observations,now),'monthly_context':{'last_close':rows[-1]['c'],'rsi14':round(float(rsi[-1]),2),'return_3bars_pct':round((rows[-1]['c']/rows[-4]['c']-1)*100,2)} if tf=='1M' and len(rows)>15 else None}
    path=store.ROOT/'data/learning-summary.json';tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(result,ensure_ascii=False));tmp.replace(path)
    store.put('learning_updated_at',result['updated_at']);store.put('learning_error',None)
    return result


def context(symbol,raw,asof):
    path=store.ROOT/'data/learning-summary.json'
    if not path.exists():return {'status':'history_not_ready'}
    data=json.loads(path.read_text());out={'status':'ready' if asof-data['updated_at']<10*3600 else 'stale','updated_at':data['updated_at'],'scope':data['scope'],'frames':{}}
    for tf in FRAMES:
        sources={}
        for market in ENDPOINTS:
            meta=data['sources'].get(f'{market}:{symbol}:{tf}')
            if not meta:continue
            rows=history(market,symbol,tf)
            query=raw.get(tf) if market=='futures' and tf in raw else rows[-32:]
            sources[market]={'coverage':{k:meta[k] for k in ['bars','first','last_closed','gaps']},'patterns':period_stats(meta['stats']) if market=='futures' else {},'analogs':analogs(rows,query,HORIZONS[tf],int(asof*1000)), 'monthly_context':meta['monthly_context']}
        out['frames'][tf]=sources
    # Feed back actual published thesis outcomes, retaining small samples and ambiguous paths.
    with store.db() as c:
        feedback=c.execute('SELECT a.created,a.result,e.hours,e.data FROM evaluations e JOIN analyses a ON a.id=e.analysis_id WHERE a.symbol=? ORDER BY a.created DESC LIMIT 24',(symbol,)).fetchall()
    out['recent_published_outcomes']=[{'created':r['created'],'bias':json.loads(r['result'])['bias'],'state':json.loads(r['result'])['state'],'hours':r['hours'],'outcome':json.loads(r['data'])} for r in feedback[:8]]
    return out


def report_text():
    from .presentation import pack,quoted
    path=store.ROOT/'data/learning-summary.json'
    if not path.exists():return '📚 과거 차트 수집 중이에요. 완료 후 /learn 으로 확인할 수 있어요.'
    data=json.loads(path.read_text())
    stamp=datetime.fromtimestamp(data['updated_at'],timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    blocks=['📚 <b>과거 차트 관찰 기록</b>\n마지막 갱신 '+stamp+'\n4시간마다 새 확정봉과 사례 결과를 반영해요.']
    date=lambda t:datetime.fromtimestamp(t/1000,timezone.utc).strftime('%Y-%m-%d')
    for symbol in store.settings()['symbols']:
        lines=[]
        for market,name in [('futures','선물'),('spot','현물')]:
            for tf in FRAMES:
                d=data['sources'].get(f'{market}:{symbol}:{tf}')
                if d:lines.append(f"{name} {tf}: {date(d['first'])}~{date(d['last_closed'])} · {d['bars']:,}봉 · 시간 공백 {d['gaps']}개")
        blocks+=quoted(symbol+' · 수집 범위', '\n'.join(lines))
        meta=data['sources'].get(f'futures:{symbol}:4h',{})
        lines=[]
        for kind,groups in meta.get('stats',{}).items():
            label={'FVG_bullish':'상승 FVG','FVG_bearish':'하락 FVG','contracting_triangle_AC_projection':'수렴 삼각형 A-C 예상 선'}[kind]
            lines.append(label)
            for key,name in [('recent_90d','최근 90일'),('before_90d','이전 기간')]:
                g=groups[key];names={'early_reversal':'선 전 반전','line_touch_reversal':'선 부근 반전','line_overshoot_reversal':'선 초과 후 반전','no_reversal_in_window':'관찰 내 반전 없음','past_triangle_apex':'수렴 교점 경과','reaction_after_CE':'CE 접촉 후 반응','invalidated':'무효화','no_CE_touch':'CE 미접촉','CE_touch_no_reaction_yet':'CE 접촉·반응 대기','same_bar_touch_and_invalid':'동일봉 접촉·무효화'}
                counts=', '.join(f'{names.get(k,k)} {v}건' for k,v in g['counts'].items())
                lines.append(f"{name} {g['n']}건{' (표본 적음)' if g['small_sample'] else ''}: {counts}")
            lines.append('')
        blocks+=quoted(symbol+' · 4시간봉 패턴 비교', '\n'.join(lines))
    blocks.append('바이낸스 상장 이후 제공 범위입니다. 현물·선물은 별도 집계하며, 사례 비율은 현재의 승률이 아닙니다. 원시 봉·사례·당시 분석 결과를 보관해 다음 분석의 근거로 사용해요.')
    return pack(blocks)


async def refresh():
    store.init();db().close()
    async with ClientSession(connector=connector(),timeout=ClientTimeout(total=35)) as session:
        for market in ENDPOINTS:
            for symbol in store.settings()['symbols']:
                for tf in FRAMES:await download(session,market,symbol,tf)
    result=await asyncio.to_thread(summarize)
    log.info('learning_ready sources=%s bars=%s',len(result['sources']),sum(s['bars'] for s in result['sources'].values()))


async def main():
    while True:
        try:await refresh()
        except Exception as e:
            log.exception('history_refresh_failed');store.put('learning_error',{'time':time.time(),'type':type(e).__name__})
        await asyncio.sleep(4*3600)


if __name__=='__main__':
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    asyncio.run(main())
