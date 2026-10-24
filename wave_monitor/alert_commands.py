"""Persist explicit sharp-move alert requests before any language-model routing."""
import re
from . import store


def rules_for(symbol):
    return store.get('sharp_rules:'+symbol,store.settings()['sharp_move_rules'])


def handle(text,mid):
    compact=''.join(text.lower().split())
    if not (any(x in compact for x in ['급등','급락','급변']) and any(x in compact for x in ['알려','알림','브리핑','통지'])):return False
    if not any(x in compact for x in ['해줘','해주세요','보내','알려','설정','켜']):return False
    minutes=re.search(r'(\d+)분',compact);percent=re.search(r'(\d+(?:\.\d+)?)%',compact)
    if not minutes or not percent:
        store.enqueue_message('급변 알림의 시간과 변동률을 적어 주세요. 예: 5분 안에 2% 이상 급등락하면 알려줘.',reply_id=mid)
        return True
    window=int(minutes[1]);threshold=float(percent[1])
    if window not in [5,15,60] or not 0<threshold<=100:
        store.enqueue_message('현재 급변 감시는 5분·15분·60분 기준을 지원합니다. 변동률은 0% 초과로 지정해 주세요.',reply_id=mid)
        return True
    symbols=[]
    if any(x in compact for x in ['비트','btc']):symbols.append('BTCUSDT')
    if any(x in compact for x in ['이더','eth']):symbols.append('ETHUSDT')
    if not symbols:symbols=store.settings()['symbols']
    for symbol in symbols:
        rules=[r for r in rules_for(symbol) if r[0]!=window]+[[window,threshold]]
        store.put('sharp_rules:'+symbol,sorted(rules))
    store.put('paused',False)
    store.enqueue_message(', '.join(symbols)+f' 급등락 알림을 적용했습니다.\n\n최근 약 {window}분 기준 가격 대비 +{threshold:g}% 이상 또는 -{threshold:g}% 이하로 움직이면 자동으로 짧게 브리핑합니다. 봉 마감을 기다리지 않고 약 5초 간격으로 확인합니다.\n\n같은 움직임의 중복 알림은 제한합니다. 급변 알림은 AI 분석 완료를 기다리지 않습니다.',reply_id=mid)
    return True
