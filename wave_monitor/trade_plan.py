"""Advisory plans only: no account access, position tracking or order execution."""
import math

def plan_summary(result):
    """Price landmarks only; detailed conditions belong in a disclosure."""
    from html import escape
    p=result.get('trade_plan')
    if not p:return ''
    from .allocation import summary
    context=summary(result)
    if not p.get('enabled'):return '🕰 <b>진입 대기</b>\n'+escape(p.get('reason','현재 진입 조건 확인 중'))+('\n\n'+escape(context) if context else '')
    validate(p,result['bias'])
    preferred=p.get('entry_preferred')
    entry=f'{preferred:,.2f}' if preferred is not None else f"{p['entry_low']:,.2f}–{p['entry_high']:,.2f}"
    side='롱' if result['bias']=='bullish' else '숏'
    mode=p.get('paper_execution',{}).get('mode')
    execution={'market':'확인된 근거로 다음 1분봉 시가 진입 검토','close_then_market':'확인봉 이후 다음 1분봉 시가 진입 · 지정가 재방문 불필요','limit':'활성 지정가 계획','close_then_limit':'확인봉 이후 지정가 계획'}.get(mode,'조건 확인 후 진입')
    return '\n\n'.join(([escape(context)] if context else [])+[
        f'📌 <b>{side} 진입 기준 · {entry}</b>\n허용 구간 {p["entry_low"]:,.2f}–{p["entry_high"]:,.2f}\n{execution} · 아래 진입 순서 참고',
        f'⛔ <b>최초 손절 · {p["stop"]:,.2f}</b>',
        f'🎯 <b>1차 익절 · {p["tp1"]:,.2f}</b>\n{p["take_pct"]}% 정리',
        f'🏁 <b>잔량 목표 · {p["tp2"]:,.2f}</b>\n나머지 {100-p["take_pct"]}% · 홀딩 조건은 아래 펼쳐 보기'])

def validate(plan,bias):
    if not plan['enabled']:return
    keys=['entry_low','entry_high','stop','tp1','tp2']
    if any(not isinstance(plan[k],(int,float)) or not math.isfinite(plan[k]) or plan[k]<=0 for k in keys):raise ValueError('invalid_plan_prices')
    lo,hi,stop,t1,t2=(plan[k] for k in keys)
    if lo>hi or bias=='neutral':raise ValueError('invalid_plan_direction')
    if not 0<plan['take_pct']<100:raise ValueError('invalid_partial_exit')
    if bias=='bullish' and not stop<lo<=hi<t1<t2:raise ValueError('invalid_long_plan')
    if bias=='bearish' and not t2<t1<lo<=hi<stop:raise ValueError('invalid_short_plan')
    if not all(plan[k].strip() for k in ['entry_rule','stop_reason','breakeven_rule','hold_rule']):raise ValueError('incomplete_plan_rules')
    if 'entry_preferred' in plan:
        preferred=plan['entry_preferred']
        if not isinstance(preferred,(int,float)) or not math.isfinite(preferred) or not lo<=preferred<=hi:raise ValueError('preferred_entry_outside_zone')
        holding=plan.get('holding_invalidation')
        if not isinstance(holding,(int,float)) or not math.isfinite(holding) or holding<=0:raise ValueError('invalid_holding_line')
        if bias=='bullish' and not stop<=holding<t2:raise ValueError('holding_line_beyond_stop')
        if bias=='bearish' and not t2<holding<=stop:raise ValueError('holding_line_beyond_stop')
        if plan.get('holding_timeframe') not in ['15m','1h','4h','1d']:raise ValueError('invalid_holding_timeframe')
        if not all(plan.get(k,'').strip() for k in ['entry_reason','tp1_reason','holding_exit_rule','review_rule','expected_horizon']):raise ValueError('incomplete_detailed_plan')

def format_plan(result,compact=False):
    p=result.get('trade_plan')
    if not p:return ''
    if not p.get('enabled'):
        return '🕰 진입 대기\n'+p.get('reason','현재 진입 조건 확인 중')[:(160 if compact else 600)]
    validate(p,result['bias'])
    entry=p['entry_high'] if result['bias']=='bullish' else p['entry_low']
    risk=abs(entry-p['stop']);rr1=abs(p['tp1']-entry)/risk;rr=abs(p['tp2']-entry)/risk
    preferred=p.get('entry_preferred')
    entry_text=f"진입 기준 {preferred:,.2f}" if preferred is not None else '진입 구간'
    lines=['🛡 내가 선택한 관리 계획 · 미체결 가정',f"{entry_text} / 범위 {p['entry_low']:,.2f}–{p['entry_high']:,.2f}",f"최초 손절 {p['stop']:,.2f}",f"1차 익절 {p['tp1']:,.2f} · {p['take_pct']}% 정리",f"잔량 {100-p['take_pct']}% · 다음 목표 {p['tp2']:,.2f}"]
    n=85 if compact else 220
    lines.append('진입 순서: '+p['entry_rule'][:n])
    lines.append('본전 스탑 이동: '+p['breakeven_rule'][:n])
    if p.get('holding_invalidation') is not None:
        lines.append(f"잔량 정리 기준 {p['holding_invalidation']:,.2f} · {p['holding_timeframe']}")
        lines.append('정리 조건: '+p['holding_exit_rule'][:n])
    lines.append('홀딩: '+p['hold_rule'][:n])
    if p.get('expected_horizon'):lines.append('관찰 기간: '+p['expected_horizon'][:n])
    if p.get('review_rule'):lines.append('시간 경과 시 재검토: '+p['review_rule'][:n])
    lines.append(f'손익비 1차 {rr1:.1f}R / 최종 {rr:.1f}R (진입 구간 불리한 끝값·비용 전)')
    if not compact:
        for label,key in [('내가 이 자리를 선택한 이유','reason'),('진입선 근거','entry_reason'),('손절선 근거','stop_reason'),('1차 익절 근거','tp1_reason')]:
            if p.get(key):lines.extend(['',label+'\n'+p[key][:600]])
    from .allocation import detail
    allocation=detail(result)
    if allocation:lines.extend(['',allocation])
    return '\n\n'.join(lines)
