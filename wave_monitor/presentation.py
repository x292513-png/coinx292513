"""Telegram HTML documents, split only between complete escaped blocks."""
import json
import textwrap
from datetime import datetime, timezone, timedelta
from html import escape


def units(s):
    return len(s.encode('utf-16-le')) // 2


def quoted(title, text):
    chunks=[]
    # Split raw text before escaping; tags/entities can never straddle messages.
    for chunk in raw_chunks(text):
        body='\n'.join(textwrap.fill(line,100) for line in chunk.splitlines())
        chunks.append('<blockquote expandable><b>'+escape(title)+'</b>\n'+escape(body)+'</blockquote>')
    return chunks


def raw_chunks(text):
    while text:
        n=min(1800,len(text))
        while units(escape(text[:n]))>3100:n=max(1,n*3//4)
        yield text[:n]
        text=text[n:]


def pack(blocks):
    pages=[];page=''
    for block in blocks:
        if units(page+'\n\n'+block)>3800:
            if page:pages.append(page)
            page=block
        else:page+='\n\n'+block if page else block
    if page:pages.append(page)
    return json.dumps({'wave_format':'html-v2','pages':pages},ensure_ascii=False)


def format_analysis(r,snap,aid,reason):
    e=escape
    stamp=datetime.fromtimestamp(snap['asof'],timezone(timedelta(hours=9))).strftime('%m/%d %H:%M')
    direction={'bullish':'🟢 상승 우세','bearish':'🔴 하락 우세','neutral':'🟡 방향 확인 중'}[r['bias']]
    header=f"<b>{e(r['symbol'].replace('USDT',''))} · {direction}</b>\n<b>{e(r['headline'][:140])}</b>\n{stamp} KST · #{aid} · 기준 {snap['price']['price']:,.2f}\n판단 강도 <b>{r['confidence']}/100</b>"
    blocks=[header,'🧭 <b>지금의 판단</b>\n'+e(r['thesis'][:420])]
    blocks+=wave_blocks(r)
    if r.get('answer_to_user'):blocks+=quoted('💬 질문에 대한 답',r['answer_to_user'])
    prices=['📍 <b>중요 가격</b>']
    for z in r['zones']:
        role={'support':'지지','resistance':'저항','watch':'관찰'}[z['role']]
        prices.append(f"• {role} <b>{z['low']:,.2f}–{z['high']:,.2f}</b>\n  {e(z['reason'][:160])}")
    blocks.append('\n'.join(prices))
    invalid=f"{r['invalidation_price']:,.2f} {'하회' if r['invalidation_side']=='below' else '상회'}" if r['invalidation_price'] else '방향 확인 전'
    blocks.append('✅ <b>확인 조건</b>\n'+e(r['confirmation_rule'][:260])+'\n\n⛔ <b>무효화 · '+invalid+'</b> (실시간 가격)\n🎯 목표 후보 '+(', '.join(f'{v:,.2f}' for v in r['targets']) or '미지정'))
    from .trade_plan import format_plan,plan_summary
    plan=plan_summary(r)
    if plan:
        blocks.append(plan)
        if r.get('trade_plan',{}).get('enabled'):
            blocks+=quoted('🛡 진입 순서 · 본전 스탑 · 잔량 홀딩 — 펼쳐 보기',format_plan(r))
    frames='\n\n'.join(f"{f['tf']} · {f['count']}\n{f['evidence']}" for f in r['frames'] if f['status']!='standby')
    blocks+=quoted('🔎 시간봉별 근거 · 펼쳐 보기',frames)
    blocks+=quoted('🧩 ICT · 매물대 · RSI',f"FVG / OB\n{r.get('ict_comment','')}\n\n매물대\n{r['volume_comment']}\n\nRSI\n{r['rsi_comment']}")
    detail=f"대안\n{r['alternative']}\n\n지난 분석에서 달라진 점\n{r['changed_since_previous']}\n\n다음 관찰\n{r['next_watch']}"
    if len(r['thesis'])>420:detail+='\n\n전체 판단\n'+r['thesis']
    blocks+=quoted('↪ 대안과 변화',detail)
    if r.get('learning_comment'):blocks+=quoted('📚 과거 사례와 최근 흐름',r['learning_comment'])
    if r.get('book_comment'):
        blocks+=quoted('📖 적용한 파동 규칙 · 출처',r['book_comment']+'\n\n'+'\n'.join(r.get('book_sources',[])))
    if r.get('fractal_comment'):
        detail=r['fractal_comment']
        for f in r.get('fractal_evidence',[]):
            stamp=lambda t:datetime.fromtimestamp(t/1000,timezone.utc).strftime('%Y/%m/%d %H:%M UTC')
            detail+=f"\n\n현재 {f['query_tf']} ↔ 과거 {f['source_tf']} {f['window_bars']}봉 ({'선물' if f['market']=='futures' else '현물'})\n{stamp(f['start'])} ~ {stamp(f['end'])}\n당시 이후 {f['horizon_bars']}봉 종가 변화 {f['return_pct']:+.3f}% · 모양 거리 {f['distance']:.3f}"
        blocks+=quoted('🔁 다른 시간봉에서 찾은 프랙탈',detail)
    blocks.append(f'<a href="https://www.binance.com/en/futures/{e(r["symbol"])}">바이낸스 차트</a> · <a href="https://www.tradingview.com/chart/?symbol=BINANCE%3A{e(r["symbol"])}.P">TradingView</a>\n이 알림에 답장하면 이어서 분석해요.')
    return pack(blocks)


def pages(text):
    try:
        d=json.loads(text)
        if isinstance(d,dict) and d.get('wave_format')=='html-v2':return d['pages']
    except (ValueError,TypeError):pass
    return [escape(chunk) for chunk in raw_chunks(text)]


def wave_blocks(result):
    views=result.get('wave_view',[])
    if not views:return []
    names={'1d':'일봉','4h':'4시간','1h':'1시간','15m':'15분'}
    kinds={'impulse':'임펄스','abc':'ABC','wxy':'WXY','triangle':'수렴','unclear':'분류 보류'}
    summary=['🌊 <b>엘리어트 파동 · 탑다운</b>']
    details=['모델 시나리오 가중치 · 통계적 적중률 아님']
    for v in views:
        summary.append(f"<b>{names[v['tf']]} · {escape(v['trend'])}</b>\n{escape(v['count'])}")
        weights=' · '.join(f'{kinds[k]} {n}%' for k,n in v['weights'].items())
        details.append(f"{names[v['tf']]} · {v['count']}\n{weights}\n{v['evidence']}")
    return ['\n\n'.join(summary)]+quoted('📊 파동 후보 비중과 근거 — 펼쳐 보기','\n\n'.join(details))
