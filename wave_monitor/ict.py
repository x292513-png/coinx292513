"""Causal ICT FVG/CE and explicit rule-based order-block candidates.

FVG geometry follows the three-candle wick gap. Displacement/structure filters
are implementation choices, not a claim to encode every discretionary ICT rule.
"""
import numpy as np


def lifecycle(zone, future):
    touched=mid_t=filled=invalid=None
    for c in future:
        if touched is None and c['l']<=zone['high'] and c['h']>=zone['low']:touched=c['t']
        if mid_t is None and c['l']<=zone['mid']<=c['h']:mid_t=c['t']
        far=(c['l']<=zone['low']) if zone['direction']=='bullish' else (c['h']>=zone['high'])
        if filled is None and far:filled=c['t']
        broken=(c['c']<zone['low']) if zone['direction']=='bullish' else (c['c']>zone['high'])
        if broken:invalid=c['close_t'];break
    status='invalidated' if invalid is not None else ('filled' if filled is not None else ('midpoint_touched' if mid_t is not None else ('partially_touched' if touched is not None else 'untouched')))
    return {**zone,'status':status,'first_touch':touched,'midpoint_touch':mid_t,'filled_at':filled,'invalidated_at':invalid}


def detect(rows,tf,atr,points=()):
    zones=[];seen_ob=set()
    start=max(2,len(rows)-600)
    for i in range(start,len(rows)):
        a,b,c=rows[i-2:i+1]
        av=float(atr[i-1]) if np.isfinite(atr[i-1]) else b['h']-b['l']
        if av<=0:continue
        if a['h']<c['l']:
            direction='bullish';lo,hi=a['h'],c['l']
        elif a['l']>c['h']:
            direction='bearish';lo,hi=c['h'],a['l']
        else:continue
        if hi-lo<max(av*.1,c['c']*.00002):continue
        body=abs(b['c']-b['o'])
        strong=body>=av*.8 and ((direction=='bullish' and b['c']>b['o']) or (direction=='bearish' and b['c']<b['o']))
        zone={'id':f"{tf}:FVG:{c['t']}",'tf':tf,'kind':'FVG','direction':direction,'low':lo,'high':hi,'mid':(lo+hi)/2,'origin_t':a['t'],'formed_at':c['close_t'],'displacement':strong,'body_atr':round(body/av,2),'candle_times':[a['t'],b['t'],c['t']]}
        zones.append(lifecycle(zone,rows[i+1:]))
        if not strong or i<8:continue
        prior=rows[max(0,i-6):i-1]
        local_break=b['c']>max(r['h'] for r in prior) if direction=='bullish' else b['c']<min(r['l'] for r in prior)
        structural=[p for p in points if p['confirmed'] and p['confirmed_at']<=b['close_t'] and p['t']<b['t'] and p['kind']==('H' if direction=='bullish' else 'L')]
        mss=bool(structural and ((b['c']>structural[-1]['price']) if direction=='bullish' else (b['c']<structural[-1]['price'])))
        if not (local_break or mss):continue
        index=next((j for j in range(i-2,max(-1,i-10),-1) if (rows[j]['c']<rows[j]['o'] if direction=='bullish' else rows[j]['c']>rows[j]['o'])),None)
        if index is None:continue
        ob=rows[index];key=f"{tf}:OB:{ob['t']}:{direction}"
        if key in seen_ob:continue
        seen_ob.add(key)
        item={'id':key,'tf':tf,'kind':'OB','direction':direction,'low':ob['l'],'high':ob['h'],'mid':(ob['o']+ob['c'])/2,'range_mid':(ob['h']+ob['l'])/2,'body_low':min(ob['o'],ob['c']),'body_high':max(ob['o'],ob['c']),'origin_t':ob['t'],'formed_at':c['close_t'],'displacement':True,'body_atr':round(body/av,2),'local_range_break':local_break,'confirmed_pivot_break':mss,'linked_fvg':zone['id'],'definition':'last_opposite_candle_before_displacement_with_FVG_and_structure_or_5bar_break; full wick bounds, body midpoint'}
        zones.append(lifecycle(item,rows[i+1:]))
    price=rows[-1]['c']
    active=[z for z in zones if z['status'] not in ['filled','invalidated']]
    active.sort(key=lambda z:abs(z['mid']-price))
    recent_dead=sorted([z for z in zones if z['status'] in ['filled','invalidated']],key=lambda z:z['formed_at'],reverse=True)
    return {'active':active[:10],'recent_completed':recent_dead[:3],'definitions':{'FVG':'bullish: candle1.high < candle3.low; bearish: candle1.low > candle3.high; CE=(low+high)/2. Formed only after candle3 closes.','OB':'strict rule-based candidate: opposite candle before >=0.8 ATR displacement, FVG and confirmed swing or previous five-bar range close break. Wick range plus body midpoint (MT).','status':'touch / midpoint / full wick fill / closing beyond far boundary tracked separately; formed candle does not count as retest.'}}


def confluences(frames,profiles,price):
    out=[]
    for tf in ['1d','4h','15m','5m']:
        ict=frames[tf].get('ict',{})
        for z in ict.get('active',[]):
            overlaps=[]
            for p in profiles:
                for h in p['hvn']:
                    if max(z['low'],h['low'])<=min(z['high'],h['high']):overlaps.append(p['name']+' HVN')
                if z['low']<=p['poc']<=z['high']:overlaps.append(p['name']+' POC')
            for other_tf in ['1d','4h','15m','5m']:
                for other in frames[other_tf].get('ict',{}).get('active',[]):
                    if other['id']!=z['id'] and other['direction']==z['direction'] and other['kind']!=z['kind'] and max(z['low'],other['low'])<=min(z['high'],other['high']):overlaps.append(other['id'])
            if overlaps:out.append({'id':z['id'],'tf':tf,'kind':z['kind'],'direction':z['direction'],'low':z['low'],'high':z['high'],'mid':z['mid'],'overlaps':list(dict.fromkeys(overlaps))[:6],'distance_pct':round(abs(z['mid']-price)/price*100,3)})
    return sorted(out,key=lambda z:z['distance_pct'])[:12]
