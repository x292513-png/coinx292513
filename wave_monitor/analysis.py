"""Deterministic measurements; candidates are not a claim of Elliott ground truth."""
import math
import time
import numpy as np
from . import store

TF_MS = {'1m':60000,'5m':300000,'15m':900000,'1h':3600000,'4h':14400000,'1d':86400000,'1w':604800000}


def indicators(rows, period=14):
    close = np.array([x['c'] for x in rows], dtype=float)
    n = len(close)
    rsi = np.full(n, np.nan)
    atr = np.full(n, np.nan)
    if n <= period:
        return rsi, atr
    delta = np.diff(close)
    gain, loss = np.maximum(delta,0), np.maximum(-delta,0)
    tr = np.array([rows[0]['h']-rows[0]['l']] + [max(rows[i]['h']-rows[i]['l'],abs(rows[i]['h']-close[i-1]),abs(rows[i]['l']-close[i-1])) for i in range(1,n)])
    g,l = gain[:period].mean(),loss[:period].mean()
    atr[period] = tr[1:period+1].mean()
    for i in range(period,n):
        if i>period:
            g=(g*(period-1)+gain[i-1])/period
            l=(l*(period-1)+loss[i-1])/period
            atr[i]=(atr[i-1]*(period-1)+tr[i])/period
        rsi[i]=50 if g==0 and l==0 else (100 if l==0 else 100-100/(1+g/l))
    return rsi,atr


def pivots(rows, multiplier=1.5, limit=30):
    """ATR reversal ZigZag; candidate extreme distinguished from confirmed points.

    Confirmation uses a later candle CLOSE to avoid inventing intrabar high/low order.
    An outside candle creating a new extreme cannot confirm itself.
    """
    rsi, atr = indicators(rows)
    if len(rows)<20:
        return []
    direction=0
    hi=lo=14
    out=[]
    def point(i,kind,confirmed,known_at):
        return {'t':rows[i]['t'],'price':rows[i]['h' if kind=='H' else 'l'],'kind':kind,'confirmed':confirmed,'confirmed_at':known_at,'rsi':round(float(rsi[i]),2) if np.isfinite(rsi[i]) else None}
    for i in range(15,len(rows)):
        threshold=max(float(atr[i])*multiplier, rows[i]['c']*0.0005)
        if direction==0:
            if rows[i]['h']>rows[hi]['h']: hi=i
            if rows[i]['l']<rows[lo]['l']: lo=i
            if lo<i and rows[i]['c']-rows[lo]['l']>=threshold:
                out.append(point(lo,'L',True,rows[i]['close_t']));direction=1;hi=i
            elif hi<i and rows[hi]['h']-rows[i]['c']>=threshold:
                out.append(point(hi,'H',True,rows[i]['close_t']));direction=-1;lo=i
        elif direction==1:
            if rows[i]['h']>=rows[hi]['h']: hi=i
            if hi<i and rows[hi]['h']-rows[i]['c']>=threshold:
                out.append(point(hi,'H',True,rows[i]['close_t']));direction=-1;lo=i
        else:
            if rows[i]['l']<=rows[lo]['l']: lo=i
            if lo<i and rows[i]['c']-rows[lo]['l']>=threshold:
                out.append(point(lo,'L',True,rows[i]['close_t']));direction=1;hi=i
    if direction:
        out.append(point(hi if direction==1 else lo,'H' if direction==1 else 'L',False,None))
    return out[-limit:] if limit else out


def candidates(points):
    out=[]
    for start in range(max(0,len(points)-12),len(points)-3):
        p=points[start:]
        d=1 if p[0]['kind']=='L' else -1
        q=[x['price']*d for x in p]
        if len(p)>=4 and q[1]>q[0] and q[0]<q[2]<q[1] and q[3]>q[1]:
            out.append({'pattern':'impulse_3_or_ABC_C','direction':'up' if d==1 else 'down','points':p[:4],'note':'3파 진행과 ABC의 C파를 모두 비교. 3파 최단 여부는 5파 길이가 나와야 검증 가능.'})
        if len(p)>=4 and q[1]>q[0] and q[2]<q[1] and q[3]>q[2]:
            out.append({'pattern':'ABC_candidate','direction':'up' if d==1 else 'down','points':p[:4],'retracement_B':round((q[1]-q[2])/(q[1]-q[0]),3),'note':'A/B/C 내부 세부파동과 상위 맥락을 별도 확인해야 함.'})
        if len(p)>=6:
            a=q[:6]
            w=[a[1]-a[0],a[3]-a[2],a[5]-a[4]]
            basic=a[0]<a[2]<a[1] and a[3]>a[1] and a[2]<a[4]<a[3] and a[5]>a[4]
            if basic and a[4]>a[1] and w[1]>=min(w[0],w[2]):
                out.append({'pattern':'impulse_5_candidate','direction':'up' if d==1 else 'down','points':p[:6],'wave_lengths':w,'note':'일반 임펄스 가격 규칙 통과. 내부 구조/degree 확인 필요.'})
            if basic and a[4]<a[1]:
                contracting=w[0]>w[1]>w[2]>0
                expanding=w[0]<w[1]<w[2]
                if contracting or expanding:
                    out.append({'pattern':'diagonal_candidate','direction':'up' if d==1 else 'down','points':p[:6],'shape':'contracting' if contracting else 'expanding','note':'leading(1/A)와 ending(5/C)은 상위 위치 및 세부파동으로 구분. ABCDE 삼각형과 다름.'})
            highs=[x['price'] for x in p[:6] if x['kind']=='H'];lows=[x['price'] for x in p[:6] if x['kind']=='L']
            if len(highs)==3 and len(lows)==3 and highs[0]>highs[1]>highs[2] and lows[0]<lows[1]<lows[2]:
                out.append({'pattern':'triangle_ABCDE_candidate','points':p[:6],'note':'4/B/X 위치 후보. 엔딩 다이아고날과 별도 분류.'})
    return out[-12:]


def divergences(points):
    out=[]
    for kind in ['H','L']:
        ps=[x for x in points if x['kind']==kind and x['rsi'] is not None]
        if len(ps)<2: continue
        a,b=ps[-2:]
        p,r=b['price']-a['price'],b['rsi']-a['rsi']
        label=None
        if kind=='H' and p>0 and r<0: label='regular_bearish'
        if kind=='L' and p<0 and r>0: label='regular_bullish'
        if kind=='H' and p<0 and r>0: label='hidden_bearish'
        if kind=='L' and p>0 and r<0: label='hidden_bullish'
        if label: out.append({'type':label,'points':[a,b],'status':'confirmed_pivots' if b['confirmed'] else 'developing','note':'pivot 확인과 가격 반전 확인은 별도'})
    return out


def volume_profile(rows, bins=72, name='7d', actual=None):
    if not rows and not actual: return None
    if actual:
        lo=min(x[0] for x in actual);hi=max(x[0] for x in actual)
    else:
        lo=min(x['l'] for x in rows);hi=max(x['h'] for x in rows)
    hi=max(hi,lo+max(lo*1e-6,0.01))
    edges=np.linspace(lo,hi,bins+1);vol=np.zeros(bins)
    if actual:
        for p,v in actual:
            idx=min(bins-1,max(0,int((p-lo)/(hi-lo)*bins)));vol[idx]+=v
    else:
        for c in rows:
            a=max(0,min(bins-1,int((c['l']-lo)/(hi-lo)*bins)))
            b=max(a,min(bins-1,int((c['h']-lo)/(hi-lo)*bins)))
            vol[a:b+1]+=c['v']/(b-a+1)
    poc=int(vol.argmax());a=b=poc;cum=vol[poc];total=vol.sum()
    while cum<total*.7 and (a>0 or b<bins-1):
        left=vol[a-1] if a>0 else -1;right=vol[b+1] if b<bins-1 else -1
        if left>=right: a-=1;cum+=vol[a]
        else: b+=1;cum+=vol[b]
    peaks=[i for i in range(1,bins-1) if vol[i]>=vol[i-1] and vol[i]>=vol[i+1]]
    nodes=[]
    for i in sorted(peaks,key=lambda i:vol[i],reverse=True):
        if vol[i]>0 and all(abs(i-x)>3 for x in nodes): nodes.append(i)
        if len(nodes)>=4: break
    return {'name':name,'method':'actual_aggregate_trades_bucketed' if actual else 'OHLCV_uniform_range_approximation','poc':float((edges[poc]+edges[poc+1])/2),'val':float(edges[a]),'vah':float(edges[b+1]),'hvn':[{'low':float(edges[i]),'high':float(edges[i+1]),'volume':float(vol[i])} for i in nodes], 'edges':edges.tolist(),'volume':vol.tolist(),'source_start':rows[0]['t'] if rows else None,'source_end':rows[-1]['close_t'] if rows else None,'base_volume_total':float(total)}


def snapshot(symbol):
    cfg=store.settings();frames={};raw={}
    for tf in cfg['timeframes']:
        rows=store.candles(symbol,tf,2100 if tf=='5m' else 1000)
        if len(rows)<30: raise ValueError('insufficient_'+tf)
        raw[tf]=rows
        rsi,atr=indicators(rows)
        pts=pivots(rows);large=pivots(rows,3)
        frames[tf]={'last_closed':rows[-1], 'rsi14':round(float(rsi[-1]),2),'atr14':round(float(atr[-1]),4),'pivots':pts[-18:],'major_pivots':large[-12:],'candidates':candidates(pts),'divergences':divergences(pts),'recent_candles':rows[-12:]}
        from .ict import detect
        frames[tf]['ict']=detect(rows,tf,atr,pts)
    now=time.time();price=store.get('price:'+symbol, {'price':raw['1m'][-1]['c'],'time':raw['1m'][-1]['close_t']/1000})
    rolling=[x for x in raw['5m'] if x['t']>=(now-7*86400)*1000]
    profiles=[volume_profile(rolling,name='rolling_7d_5m_approx')]
    major=frames['4h']['major_pivots'];anchor=next((x['t'] for x in reversed(major[:-1]) if x['confirmed']),raw['4h'][-120]['t'])
    profiles.append(volume_profile([x for x in raw['4h'] if x['t']>=anchor],name='last_major_4h_swing_approx'))
    with store.db() as c:
        trades=c.execute('SELECT price,SUM(volume) FROM trade_bins WHERE symbol=? AND hour>=? GROUP BY price',(symbol,int(now//3600-23)*3600)).fetchall()
    if trades:
        p=volume_profile([],name='collected_actual_24h',actual=trades);p['coverage']=store.get('trade_coverage:'+symbol,{});profiles.append(p)
    previous=store.latest(symbol)
    snap={'symbol':symbol,'asof':now,'price':price,'frames':frames,'profiles':profiles,'previous':{'id':previous['id'],'created':previous['created'],'result':previous['result']} if previous else None,'rules':'엘리어트 파동 우선: 일봉→4h→1h→15m. 주봉은 배경, 5m/1m은 진입 보조. 지지저항/FVG/OB는 파동 시나리오의 타점 확인용. 일반 캔들/바이낸스 USDT 무기한 체결가격. 마크가격 아님. 시간 UTC ms, 표시는 KST. WXY는 ABC와 동일한 내부 규칙을 강제하지 않음.'}
    from .ict import confluences
    snap['confluences']=confluences(frames,profiles,price['price'])
    return snap,raw


def structural_state(snap):
    key={}
    for tf in ['1d','4h','15m','5m']:
        f=snap['frames'][tf];ps=[p for p in f['pivots'] if p['confirmed']]
        key[tf]=[p['t'] for p in ps[-3:]]
    return key
