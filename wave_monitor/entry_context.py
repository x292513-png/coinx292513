"""Explicit numeric evidence for price confluence, never an inferred win rate."""

def measured_levels(snap,raw):
    levels=[]
    for tf in ('1d','4h','1h','15m'):
        rows=raw.get(tf,[])
        for n in (100,200):
            if len(rows)>=n:
                levels.append({'id':f'{tf}:SMA{n}','kind':'moving_average','tf':tf,'price':sum(r['c'] for r in rows[-n:])/n,'period':n,'method':'closed-candle SMA','asof':rows[-1]['close_t']})
        points=[p for p in snap['frames'].get(tf,{}).get('pivots',[]) if p.get('confirmed')]
        if len(points)<2:continue
        # Several explicit anchor candidates; model must justify the selected degree.
        ends=[points[-1]]
        if tf=='1d':
            high=max((p for p in points if p['kind']=='H'),key=lambda p:p['price'],default=None)
            if high and high!=ends[0]:ends.append(high)
        for end in ends:
            for start in [p for p in points if p['t']<end['t'] and p['kind']!=end['kind']][-6:]:
                if (end['price']-start['price'])*(1 if end['kind']=='H' else -1)<=0:continue
                for ratio in (.382,.5,.618,.786):
                    levels.append({'id':f"{tf}:fib:{start['t']}:{end['t']}:{ratio}",'kind':'retracement','tf':tf,'price':end['price']+(start['price']-end['price'])*ratio,'ratio':ratio,'start':start,'end':end,'note':'anchor candidate only, not a validated impulse'})
    return {'levels':levels,'interpretation':'SMA and Fibonacci are measured price references, not independent proof or a win probability. A touch must be checked against candles. Do not claim EMA, a different degree, or a completed reversal from these values.'}

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
        else:details.append(f"측정: {m['tf']} {m['start']['price']:,.2f} → {m['end']['price']:,.2f}의 {m['ratio']} 되돌림 = {m['price']:,.2f}")
    blocks+=quoted('🧩 시나리오별 근거 · 진입 확인 · 실패 조건', '\n\n'.join(details))
    return blocks
