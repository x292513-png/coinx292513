"""Explicit numeric evidence for price confluence, never an inferred win rate."""

def measured_levels(snap,raw):
    levels=[]
    for tf in ('1d','4h','1h','15m','5m'):
        rows=raw.get(tf,[])
        for n in (100,200):
            if len(rows)>=n:
                levels.append({'id':f'{tf}:SMA{n}','kind':'moving_average','tf':tf,'price':sum(r['c'] for r in rows[-n:])/n,'period':n,'method':'closed-candle SMA','asof':rows[-1]['close_t']})
        now=rows[-1]['close_t'] if rows else float('inf')
        points=sorted([p for p in snap['frames'].get(tf,{}).get('pivots',[]) if p.get('confirmed') and (p.get('confirmed_at') or p['t'])<=now],key=lambda p:p['t'])
        if len(points)<2:continue
        # Several explicit anchor candidates; model must justify the selected degree.
        ends=points[-2:]
        high=max((p for p in points[-12:] if p['kind']=='H'),key=lambda p:p['price'],default=None)
        if high and high not in ends:ends.append(high)
        for end in ends:
            for start in [p for p in points if p['t']<end['t'] and p['kind']!=end['kind']][-3:]:
                if (end['price']-start['price'])*(1 if end['kind']=='H' else -1)<=0:continue
                for ratio in (.236,.382,.5,.618,.786,.886,1.0,1.13,1.272,1.618):
                    levels.append({'id':f"{tf}:fib:{start['t']}:{end['t']}:{ratio}",'kind':'retracement' if ratio<=1 else 'retracement_extension','tf':tf,'price':end['price']+(start['price']-end['price'])*ratio,'ratio':ratio,'start':start,'end':end,'note':'anchor candidate only, not a validated impulse'})
    from .channels import channel_candidates
    for tf in ('1d','4h','1h','15m','5m'):
        frame=snap['frames'].get(tf,{})
        seen=set()
        for degree,key in [('swing','pivots'),('major','major_pivots')]:
            for channel in channel_candidates(tf,frame.get(key,[]),raw.get(tf,[]),degree):
                geometry=tuple(p['t'] for p in channel['baseline'])+(channel['parallel_anchor']['t'],)
                if geometry not in seen:levels.append(channel);seen.add(geometry)
    return {'levels':levels,'interpretation':'SMA, Fibonacci and linear parallel channel candidates are measured references, not independent proof or win probabilities. Channel values/status refer to latest closed candle time. Candle range overlap with a close-projected boundary is not proof of a touch or reversal. Fib ratios above 1 extend past the starting anchor, not a three-point ABC projection.'}

def display(result):
    from html import escape
    from .presentation import quoted
    logic=result.get('entry_logic')
    if not logic:return []
    blocks=['🎯 <b>이 진입이 성립하는 공통 근거</b>\n'+escape(logic['shared_path'])]
    details=[]
    for s in logic['supporting_scenarios']:
        details.append(s['scenario']+'\n진입 근거: '+s['why_same_entry']+'\n청산·홀딩 차이: '+s['exit_difference'])
    details += ['가격대의 중첩 근거\n'+logic['confluence'],'진입 확인\n'+logic['trigger'],'공통 판단이 깨지는 경우\n'+logic['failure_case']]
    for m in logic.get('measured_evidence',[]):
        if m['kind']=='moving_average':details.append(f"측정: {m['tf']} 확정봉 SMA{m['period']} = {m['price']:,.2f}")
        elif m['kind']=='channel':
            state={'inside':'내부','above':'상단 밖','below':'하단 밖'}[m['status']]
            details.append(f"채널 후보: {m['tf']} · 확정봉 {state}\n하단 {m['lower']:,.2f} / 중앙 {m['mid']:,.2f} / 상단 {m['upper']:,.2f}\n기준점 {m['baseline'][0]['price']:,.2f} → {m['baseline'][1]['price']:,.2f}, 평행점 {m['parallel_anchor']['price']:,.2f} · 선형 가격")
        else:details.append(f"측정: {m['tf']} {m['start']['price']:,.2f} → {m['end']['price']:,.2f}의 {m['ratio']} {'되돌림' if m['ratio']<=1 else '기점 너머 확장'} = {m['price']:,.2f}")
    blocks+=quoted('🧩 시나리오별 근거 · 진입 확인 · 실패 조건', '\n\n'.join(details))
    return blocks
