"""Advisory plans only: no account access, position tracking or order execution."""
import math

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

def format_plan(result,compact=False):
    p=result.get('trade_plan')
    if not p or not p.get('enabled'):return ''
    validate(p,result['bias'])
    entry=p['entry_high'] if result['bias']=='bullish' else p['entry_low']
    risk=abs(entry-p['stop']);rr=abs(p['tp2']-entry)/risk
    n=85 if compact else 220
    return (f"🛡 조건부 관리 계획 · 미체결 가정\n"
            f"진입 {p['entry_low']:,.2f}–{p['entry_high']:,.2f} · {p['entry_rule'][:n]}\n"
            f"손절 {p['stop']:,.2f} · {p['stop_reason'][:n]}\n"
            f"1차 {p['tp1']:,.2f}에서 {p['take_pct']}% 익절 / 나머지 목표 {p['tp2']:,.2f}\n"
            f"본전 이동: {p['breakeven_rule'][:n]}\n"
            f"홀딩: {p['hold_rule'][:n]}\n"
            f"최종 목표 손익비 {rr:.1f}R (진입 구간 불리한 끝값·비용 전)")
