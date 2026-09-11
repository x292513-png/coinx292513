import asyncio
import json
import logging
import time
import secrets
from collections import defaultdict
from aiohttp import web,ClientSession,ClientTimeout,WSMsgType
from . import store,telegram
from .analysis import snapshot,structural_state,TF_MS
from .net import connector

log=logging.getLogger('wave.collector')


async def fetch_candles(session,symbol,tf,count,end=None):
    out=[]
    while len(out)<count:
        p={'symbol':symbol,'interval':tf,'limit':min(1000,count-len(out))}
        if end: p['endTime']=end
        for attempt in range(4):
            async with session.get('https://fapi.binance.com/fapi/v1/klines',params=p) as r:
                if r.status in (429,418,500,502,503):
                    await asyncio.sleep(min(30,2**attempt*2));continue
                if r.status!=200: raise RuntimeError('binance_rest_'+str(r.status))
                data=await r.json();break
        else: raise RuntimeError('binance_rest_retries')
        if not isinstance(data,list): raise RuntimeError('binance_invalid_klines')
        now=time.time()*1000
        rows=[[int(x[0]),*map(float,x[1:6]),int(x[6]),int(x[6]<now)] for x in data]
        out=rows+out
        if not data or len(data)<p['limit']: break
        end=int(data[0][0])-1
        await asyncio.sleep(.15)
    return out


async def bootstrap(session):
    cfg=store.settings()
    for symbol in cfg['symbols']:
        for tf,count in cfg['bootstrap_bars'].items():
            old=store.candles(symbol,tf,1,False)
            if old:
                missing=max(3,int((time.time()*1000-old[-1]['t'])/TF_MS[tf])+3)
                count=min(count,missing)
            rows=await fetch_candles(session,symbol,tf,count)
            store.save_candles(symbol,tf,rows)
            if tf=='1m' and rows: store.put('price:'+symbol,{'price':rows[-1][4],'time':time.time(),'source':'rest'})
            log.info('candles_ready symbol=%s tf=%s count=%d',symbol,tf,len(rows))
    store.put('bootstrap_ready',time.time())


async def stream():
    cfg=store.settings();pending={};trade_bins=defaultdict(float);last_ids={s:store.get('agg_id:'+s,-1) for s in cfg['symbols']}
    params=[s.lower()+'@kline_'+tf for s in cfg['symbols'] for tf in cfg['timeframes']]+[s.lower()+'@aggTrade' for s in cfg['symbols']]
    url='wss://fstream.binance.com/market/stream?streams='+'/'.join(params)
    def flush():
        for (s,tf),row in pending.items(): store.save_candles(s,tf,[row])
        pending.clear()
        if trade_bins:
            with store.db() as c:
                c.executemany('INSERT INTO trade_bins VALUES (?,?,?,?) ON CONFLICT(symbol,hour,price) DO UPDATE SET volume=volume+excluded.volume',[(s,h,p,v) for (s,h,p),v in trade_bins.items()])
                for s,a in last_ids.items():c.execute('INSERT OR REPLACE INTO kv VALUES (?,?)',('agg_id:'+s,json.dumps(a)))
            trade_bins.clear()
    while True:
        try:
            async with ClientSession(connector=connector(),timeout=ClientTimeout(total=None,sock_connect=15)) as sess:
                async with sess.ws_connect(url,heartbeat=20,receive_timeout=60,max_msg_size=1024*1024) as ws:
                    store.put('ws_connected',True);store.put('ws_connected_at',time.time());log.info('websocket_connected')
                    for s in cfg['symbols']:
                        cov=store.get('trade_coverage:'+s,{'started':time.time(),'gaps':[]})
                        disconnected=store.get('ws_disconnected_at')
                        if disconnected:cov['gaps']=(cov['gaps']+[{'from':disconnected,'to':time.time()}])[-100:]
                        cov['last_connected']=time.time();store.put('trade_coverage:'+s,cov)
                    last_flush=time.time();last_heartbeat=0
                    async for m in ws:
                        if m.type!=WSMsgType.TEXT:
                            if m.type in (WSMsgType.ERROR,WSMsgType.CLOSED,WSMsgType.CLOSE):break
                            continue
                        d=json.loads(m.data).get('data',{});s=d.get('s')
                        if s not in cfg['symbols']:continue
                        now=time.time()
                        if d.get('e')=='kline':
                            k=d['k'];row=[int(k['t']),float(k['o']),float(k['h']),float(k['l']),float(k['c']),float(k['v']),int(k['T']),int(k['x'])]
                            if k['x']:store.save_candles(s,k['i'],[row])
                            else:pending[(s,k['i'])]=row
                            if k['i']=='1m':store.put('price:'+s,{'price':float(k['c']),'time':d['E']/1000,'source':'websocket'})
                        elif d.get('e')=='aggTrade':
                            a=int(d['a'])
                            if a<=last_ids[s]:continue
                            if last_ids[s]>=0 and a>last_ids[s]+1:
                                cov=store.get('trade_coverage:'+s,{})
                                cov['missing_aggregate_ids']=cov.get('missing_aggregate_ids',0)+(a-last_ids[s]-1)
                                store.put('trade_coverage:'+s,cov)
                            last_ids[s]=a
                            size=cfg['trade_bucket'][s];bucket=round(round(float(d['p'])/size)*size,4)
                            trade_bins[(s,int(d['T']//3600000)*3600,bucket)]+=float(d['q'])
                        if now-last_flush>5:flush();last_flush=now
                        if now-last_heartbeat>10:store.put('ws_last_event',now);last_heartbeat=now
                    flush()
        except asyncio.CancelledError:
            flush();raise
        except Exception as e:
            flush();log.warning('websocket_disconnected %s',type(e).__name__)
        store.put('ws_connected',False);store.put('ws_disconnected_at',time.time())
        await asyncio.sleep(5)


def is_invalid(result,price):
    p=result.get('invalidation_price');side=result.get('invalidation_side')
    return bool(p and ((side=='below' and price<p) or (side=='above' and price>p)))


async def periodic():
    cfg=store.settings();last_scan=0;last_report=0
    while True:
        try:
            now=time.time()
            for symbol in cfg['symbols']:
                p=store.get('price:'+symbol,{});prev=store.latest(symbol)
                fresh=now-p.get('time',0)<30
                if not fresh:
                    if now-store.get('stale_alert:'+symbol,0)>3600:
                        store.enqueue_message(f'{symbol} 실시간 데이터가 지연되어 새 진입 판단을 보류합니다. 연결 복구를 자동 시도 중입니다.');store.put('stale_alert:'+symbol,now)
                    continue
                if prev and is_invalid(prev['result'],p['price']) and store.get('invalidated:'+str(prev['id'])) is None:
                    store.put('invalidated:'+str(prev['id']),now)
                    store.event(symbol,'invalidation',{'analysis_id':prev['id'],'price':p['price']})
                    if not store.get('paused',False) and cfg.get('notification_mode')!='hourly':
                        store.enqueue_message(f"{symbol} 기존 시나리오 무효\n현재 {p['price']:,.2f} / 무효화 기준 {prev['result']['invalidation_price']:,.2f}\n분석 #{prev['id']}의 조건을 이탈했습니다. 새 구조를 확인합니다.",prev['id'])
                        store.queue(symbol,'invalidation')
            if now-last_scan>15:
                for symbol in cfg['symbols']:
                    if now-store.get('price:'+symbol,{}).get('time',0)>30:continue
                    snap,raw=snapshot(symbol);key=structural_state(snap);oldkey=store.get('structure:'+symbol)
                    store.put('structure:'+symbol,key);store.put('scan:'+symbol,now)
                    prev=store.latest(symbol);reason=None
                    price=snap['price']['price'];atr=snap['frames']['5m']['atr14']
                    zones=(prev or {}).get('result',{}).get('zones',[])
                    near=any(z['low']-atr*.5<=price<=z['high']+atr*.5 for z in zones)
                    ict_near=[]
                    for tf in ['4h','15m','5m']:
                        for z in snap['frames'][tf]['ict']['active']:
                            if abs(z['mid']-price)<=atr*.35:
                                ict_near.append(z)
                                seen_key='ict_touch:'+symbol+':'+z['id']
                                if not store.get(seen_key):
                                    store.put(seen_key,now);store.event(symbol,'ict_midpoint_approach',{'zone_id':z['id'],'mid':z['mid'],'price':price})
                                    reason='ict_midpoint_approach'
                    near=near or bool(ict_near)
                    for index,z in enumerate(zones):
                        inside=z['low']<=price<=z['high']
                        visit_key=f"zone_visit:{prev['id']}:{index}" if prev else ''
                        if inside and prev and not store.get(visit_key):
                            store.record_zone_visit(now,symbol,prev['id'],z,price,atr)
                            store.put(visit_key,now)
                    store.put('focus_1m:'+symbol,near)
                    if not prev:reason='initial_top_down'
                    elif key!=structural_state(prev['snapshot']):reason='structure_changed'
                    elif now-prev['created']>cfg['quiet_review_seconds']:reason='scheduled_review'
                    elif near and not store.get('was_near:'+symbol,False):reason='zone_approach'
                    cp=(prev or {}).get('result',{}).get('confirmation_price')
                    side=(prev or {}).get('result',{}).get('bias')
                    if cp:
                        c5=raw['5m'][-1]['c'];confirmed=(side=='bullish' and c5>cp) or (side=='bearish' and c5<cp)
                        if confirmed and not store.get('confirmed:'+str(prev['id']),False):
                            reason='confirmation_close';store.put('confirmed:'+str(prev['id']),True)
                    store.put('was_near:'+symbol,near)
                    store.put('last_15m_close:'+symbol,raw['15m'][-1]['t'])
                    deferred=store.get('deferred_trigger:'+symbol)
                    if reason:store.put('deferred_trigger:'+symbol,{'reason':reason,'time':now})
                    elif deferred and now-deferred['time']<1800:
                        if deferred['reason'] not in ['zone_approach','ict_midpoint_approach'] or near:reason=deferred['reason']
                    if cfg.get('notification_mode')!='hourly' and reason and not store.get('paused',False) and now-store.get('last_auto_attempt:'+symbol,0)>=cfg['auto_min_seconds'] and (not prev or now-prev['created']>=cfg['auto_min_seconds']):
                        job_id=store.queue(symbol,reason)
                        if job_id:
                            store.event(symbol,'analysis_trigger',{'reason':reason,'job_id':job_id})
                            store.put('deferred_trigger:'+symbol,None)
                last_scan=now
            from .cadence import tick
            tick(now)
            if now-last_report>60:
                from .reports import maintenance
                maintenance();last_report=now
            store.put('collector_heartbeat',time.time())
        except Exception as e:
            log.exception('periodic_error %s',type(e).__name__)
        await asyncio.sleep(5)


async def reconcile():
    cfg=store.settings()
    while True:
        try:
            async with ClientSession(connector=connector(),timeout=ClientTimeout(total=20)) as s:
                for symbol in cfg['symbols']:
                    for tf in cfg['timeframes']:
                        old=store.candles(symbol,tf,1,False)
                        count=min(cfg['bootstrap_bars'][tf],max(3,int((time.time()*1000-old[-1]['t'])/TF_MS[tf])+3)) if old else cfg['bootstrap_bars'][tf]
                        rows=await fetch_candles(s,symbol,tf,count);store.save_candles(symbol,tf,rows)
            store.put('rest_reconciled_at',time.time())
        except Exception as e:
            log.warning('rest_reconcile_failed %s; websocket scan continues',type(e).__name__)
        await asyncio.sleep(120)


async def outbox():
    while True:
        with store.db() as c:
            row=c.execute("SELECT * FROM outbox WHERE status='pending' AND attempts<5 ORDER BY id LIMIT 1").fetchone()
        if row:
            try:
                ids=await telegram.send(row['text'],row['chart'],row['reply_id'],row['analysis_id'])
                with store.db() as c:
                    for msgid in ids:c.execute('INSERT OR REPLACE INTO messages VALUES (?,?,?,?)',(msgid,row['analysis_id'],time.time(),'outgoing'))
                    c.execute("UPDATE outbox SET status='sent' WHERE id=?",(row['id'],))
                store.put('last_telegram_delivery',{'time':time.time(),'message_ids':ids})
            except Exception as e:
                with store.db() as c:c.execute('UPDATE outbox SET attempts=attempts+1 WHERE id=?',(row['id'],))
                log.warning('delivery_failed %s',type(e).__name__);await asyncio.sleep(30)
        await asyncio.sleep(2)


async def health(request):
    now=time.time();payload={'service':'trading-wave-monitor','time':now,'ws_connected':store.get('ws_connected'), 'ws_age':now-store.get('ws_last_event',0),'collector_age':now-store.get('collector_heartbeat',0),'worker_age':now-store.get('worker_heartbeat',0),'paused':store.get('paused',False),'symbols':{s:{'price':store.get('price:'+s),'last_scan':store.get('scan:'+s),'focus_1m':store.get('focus_1m:'+s)} for s in store.settings()['symbols']}}
    payload['ready']=bool(payload['ws_connected'] and payload['ws_age']<30 and payload['collector_age']<30 and all(now-(x['last_scan'] or 0)<45 for x in payload['symbols'].values()))
    return web.json_response(payload,status=200 if payload['ready'] else 503)


async def inbox(request):
    r=store.runtime()
    if not secrets.compare_digest(request.headers.get('X-Wave-Key',''),r['bridge_key']):raise web.HTTPForbidden()
    d=await request.json()
    if d.get('user_id')!=r['allowed_user'] or d.get('chat_id')!=r['chat_id'] or d.get('topic_id')!=r['topic_id']:raise web.HTTPForbidden()
    mid=int(d['message_id']);text=str(d.get('text',''))[:6000];reply=d.get('reply_id')
    if store.get('incoming:'+str(mid)):return web.json_response({'ok':True,'duplicate':True})
    store.put('incoming:'+str(mid),time.time())
    if text.strip() in ['/status','상태','상태 확인','/start','도움말']:
        from .reports import status_text
        store.enqueue_message(status_text(),reply_id=mid)
    elif text.strip() in ['/pause','알림 중지']:
        store.put('paused',True);store.enqueue_message('자동 분석과 시황 알림을 중지했어요. 가격 수집과 기록은 계속됩니다. /resume 으로 재개할 수 있어요.',reply_id=mid)
    elif text.strip() in ['/resume','알림 재개']:
        store.put('paused',False);store.enqueue_message('자동 분석과 시황 알림을 재개했어요.',reply_id=mid)
    elif text.strip() in ['/report','검증 보고서']:
        from .reports import report_text
        store.enqueue_message(report_text(),reply_id=mid)
    elif text.strip() in ['/learn','학습 기록','과거 패턴']:
        from .learning import report_text
        store.enqueue_message(report_text(),reply_id=mid)
    elif text.strip() in ['/fractal','프랙탈 기록','프랙탈 지식']:
        from .fractals import report_text
        store.enqueue_message(report_text(),reply_id=mid)
    else:
        ref=None
        if reply:
            with store.db() as c:
                x=c.execute('SELECT analysis_id FROM messages WHERE message_id=?',(reply,)).fetchone()
                if x and x[0]:ref=x[0]
        symbols=[]
        upper=text.upper()
        if any(x in upper for x in ['BTC','비트']):symbols.append('BTCUSDT')
        if any(x in upper for x in ['ETH','이더']):symbols.append('ETHUSDT')
        if not symbols and ref:
            with store.db() as c:
                x=c.execute('SELECT symbol FROM analyses WHERE id=?',(ref,)).fetchone()
                if x:symbols=[x[0]]
        if not symbols:symbols=store.settings()['symbols']
        for s in symbols:store.queue(s,'user_followup','manual',text,mid,ref)
        store.enqueue_message('접수했어요. '+', '.join(symbols)+'의 현재 차트와 이전 분석을 함께 확인할게요.',reply_id=mid)
    return web.json_response({'ok':True})


async def main():
    store.init()
    app=web.Application(client_max_size=20000);app.router.add_get('/health',health);app.router.add_post('/inbox',inbox)
    runner=web.AppRunner(app);await runner.setup();await web.TCPSite(runner,'127.0.0.1',store.settings()['listen_port']).start()
    async with ClientSession(connector=connector(),timeout=ClientTimeout(total=30)) as s:await bootstrap(s)
    await asyncio.gather(stream(),periodic(),outbox(),reconcile())


if __name__=='__main__':
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(name)s %(message)s')
    logging.getLogger('aiohttp.access').setLevel(logging.WARNING)
    asyncio.run(main())
