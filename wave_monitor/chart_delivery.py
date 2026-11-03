"""Deliver the exact saved chart behind a briefing, without another AI call."""
from pathlib import Path
import re
from . import store


def enqueue_charts(ids,reply_id=None):
    sent=0
    for aid in dict.fromkeys(ids):
        with store.db() as c:
            a=c.execute('SELECT id,symbol,chart FROM analyses WHERE id=?',(aid,)).fetchone()
        if a and a['chart'] and Path(a['chart']).is_file():
            store.enqueue_message('',analysis_id=a['id'],chart=a['chart'],reply_id=reply_id);sent+=1
        elif a:
            store.enqueue_message(a['symbol']+'의 저장된 차트 파일을 찾지 못했습니다. 분석 번호 #'+str(aid),reply_id=reply_id)
    return sent


def handle(text,reply,mid):
    from .focused_reply import is_full_request
    if is_full_request(text):return False
    q=''.join(text.lower().split())
    if not (any(x in q for x in ['사진','이미지','그림']) and any(x in q for x in ['줘','보내','없','왜','다시','주세요'])):return False
    symbols=[]
    if any(x in q for x in ['비트','btc']):symbols.append('BTCUSDT')
    if any(x in q for x in ['이더','eth']):symbols.append('ETHUSDT')
    ids=[]
    if reply and not symbols:
        with store.db() as c:
            row=c.execute('SELECT analysis_id FROM messages WHERE message_id=?',(reply,)).fetchone()
        if row and row[0]:ids=[row[0]]
    if not ids and not symbols:ids=store.get('last_briefing_analyses',[])
    if not ids:
        for symbol in symbols or store.settings()['symbols']:
            a=store.latest(symbol)
            if a:ids.append(a['id'])
    if not enqueue_charts(ids,mid):
        store.enqueue_message('전송할 저장된 분석 차트가 아직 없습니다. 비트 분석 또는 이더 분석을 요청해 주세요.',reply_id=mid)
    return True
