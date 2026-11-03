"""Illustrative 100-equity-unit plans, fixed 1x notional, no account/order access."""
import math
import re
TF={'1d':'일봉','4h':'4시간봉','1h':'1시간봉','15m':'15분봉','5m':'5분봉','1m':'1분봉'}
# Explicit operating assumptions, not calibrated probabilities or actual broker costs.
COST_RATE=.002

def limits(result):
    direction='상승' if result['bias']=='bullish' else '하락'
    views={v['tf']:v['trend'] for v in result.get('wave_view',[])}
    opposing='하락' if direction=='상승' else '상승'
    if views.get('1d')==opposing and views.get('4h')==opposing:return 'countertrend',30,.5
    if all(views.get(tf)==direction for tf in ('1d','4h','1h','15m')):return 'aligned',100,1.
    return 'mixed',50,.75

def metrics(plan,bias):
    p=plan['position_plan'];initial=p['initial_units'];add=p['add_units'];entry=plan['entry_preferred']
    worst=plan['entry_high'] if bias=='bullish' else plan['entry_low']
    stages=[(initial,entry)]+([(add,p['add_price'])] if add else [])
    total=initial+add;qty=sum(n/price for n,price in stages)
    loss=lambda n,price:n*abs(plan['stop']/price-1)+n*COST_RATE
    return {'initial_units':initial,'add_units':add,'total_units':total,'reserve_units':round(100-total,2),'average_entry':total/qty if qty else None,'initial_stop_loss_units':loss(initial,worst),'full_stop_loss_units':loss(initial,worst)+(loss(add,p['add_price']) if add else 0),'cost_rate':COST_RATE}

def prepare(result):
    plan=result.get('trade_plan',{});p=plan.get('position_plan')
    if not p:return # legacy reports remain readable, without invented sizes
    if not plan.get('enabled'):
        p.update(initial_units=0,add_units=0,add_price=None,risk_budget_units=0);return
    for key in ('thesis_timeframe','entry_timeframe','stop_timeframe'):
        if p.get(key) not in TF:raise ValueError('invalid_position_timeframe')
    if not all(p.get(k,'').strip() for k in ('alignment_reason','allocation_reason','add_condition','cancel_add_condition')):raise ValueError('incomplete_position_reason')
    # Keep qualitative rationale; all numerical sizing/PnL is rendered from code.
    original=p['allocation_reason']
    qualitative=[s for s in re.split(r'(?<=[.!?])\s+',original) if not re.search(r'\d',s)]
    if len(qualitative)<len(re.split(r'(?<=[.!?])\s+',original)):
        p['allocation_reason']=' '.join(qualitative) or p['alignment_reason']
    for key in ('initial_units','add_units','risk_budget_units'):
        value=p[key]
        if not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:raise ValueError('invalid_position_units')
    if not p['initial_units'] or not p['risk_budget_units']:raise ValueError('zero_enabled_allocation')
    if p['add_units']:
        a=p['add_price'];stop=plan['stop'];entry=plan['entry_preferred']
        if not isinstance(a,(int,float)) or not math.isfinite(a):raise ValueError('invalid_add_price')
        # Planned retracement entry only. Never add after invalidation or widen stop.
        if not (stop<a<entry if result['bias']=='bullish' else entry<a<stop):raise ValueError('add_beyond_stop_or_not_pullback')
    else:p['add_price']=None
    regime,max_units,max_risk=limits(result)
    p['regime']=regime;p['risk_budget_units']=min(p['risk_budget_units'],max_risk)
    total=p['initial_units']+p['add_units']
    scale=min(1,max_units/total)
    loss=metrics(plan,result['bias'])['full_stop_loss_units']
    if loss>0:scale=min(scale,p['risk_budget_units']/loss)
    p['adjusted_by_risk_limit']=scale<1
    p['initial_units']=math.floor(p['initial_units']*scale*100)/100
    p['add_units']=math.floor(p['add_units']*scale*100)/100
    if not p['add_units']:p['add_price']=None
    if p['initial_units']<=0:raise ValueError('allocation_too_small')
    p['calculation']=metrics(plan,result['bias'])

def summary(result):
    plan=result.get('trade_plan',{});p=plan.get('position_plan')
    if not p:return ''
    if not plan.get('enabled'):
        return (f"판단 {TF[p['thesis_timeframe']]} · 진입 확인 {TF[p['entry_timeframe']]} · 손절 구조 {TF[p['stop_timeframe']]}\n"
                "100유닛 가정: 현재 진입 0 · 추가 0 · 예비 100")
    m=metrics(plan,result['bias'])
    regime={'aligned':'네 기준봉 방향 일치','countertrend':'상위 추세 반대의 단기 매매','mixed':'시간봉 방향 혼재 · 조건 확인형'}[p['regime']]
    return (f"🧭 매매 성격: {regime}\n"
            f"판단 {TF[p['thesis_timeframe']]} → 진입 확인 {TF[p['entry_timeframe']]} → 손절 근거 {TF[p['stop_timeframe']]}\n"
            f"💰 100유닛 가정: 최초 {m['initial_units']:g} + 추가 {m['add_units']:g} · 예비 {m['reserve_units']:g}\n"
            f"전량 체결 후 손절 시 예상 손실 {m['full_stop_loss_units']:.2f}유닛 / 계획 한도 {p['risk_budget_units']:g} (진입범위 불리한 끝값)\n"
            "총자금 100 · 1배 포지션 금액 기준 · 확신도는 승률 아님")

def detail(result):
    plan=result.get('trade_plan',{});p=plan.get('position_plan')
    if not p or not plan.get('enabled'):return ''
    m=metrics(plan,result['bias'])
    lines=[summary(result),'시간봉을 이렇게 연결한 이유: '+p['alignment_reason'],'내가 이 비중을 택한 이유: '+p['allocation_reason']]
    if p['adjusted_by_risk_limit']:lines.append('제안 비중은 총 손실 한도 및 시간봉 불일치 제한에 맞춰 축소했습니다.')
    if p['add_units']:
        lines += [f"추가 {p['add_units']:g}유닛 후보 가격 {p['add_price']:,.2f}\n조건: {p['add_condition']}",f"선호 진입가와 추가 가격 모두 체결 시 평균가 {m['average_entry']:,.2f} (가격별 수량으로 계산)"]
    else:lines.append('추가 진입 없음: '+p['add_condition'])
    lines += ['추가 진입 취소: '+p['cancel_add_condition'],f"최초만 체결 후 손절 {m['initial_stop_loss_units']:.2f}유닛 / 모두 체결 후 손절 {m['full_stop_loss_units']:.2f}유닛",'추가 진입은 가격 도달만으로 실행하지 않습니다. 확인 조건 충족 전 대기하며, 최초 손절을 넓히거나 손절 후 물타기하지 않습니다.','계산 가정: 총자금 100, 선형 USDT 계약, 레버리지 1배 상당 금액. 왕복 수수료·슬리피지 합계 0.20%를 가정했으며 실제 비용·펀딩·급격한 체결 미끄러짐은 다를 수 있습니다. 표시 손실은 보장 상한이 아닙니다.','비중 상한은 검증된 승률 공식이 아닌 운영 규칙입니다: 네 기준봉 일치 최대 100/위험 1유닛, 혼재 최대 50/위험 0.75유닛, 일봉·4시간 역추세 최대 30/위험 0.5유닛.']
    lines.append('BTC·ETH는 각각 단독 진입을 가정한 계획입니다. 둘을 동시에 거래하면 같은 총자금 100과 합산 손실예산 1유닛을 나눠 써야 하며, 실제 보유 포지션은 이 서비스가 조회하지 않습니다.')
    return '\n\n'.join(lines)
