"""Fresh REST snapshots and outage episode tracking independent of WebSocket."""
import asyncio
import time
from aiohttp import ClientSession, ClientTimeout
from . import store
from .net import connector


async def refresh_price(session, symbol):
    async with session.get('https://fapi.binance.com/fapi/v2/ticker/price', params={'symbol':symbol}) as response:
        if response.status != 200:
            raise RuntimeError('price_rest_'+str(response.status))
        data=await response.json()
    observed=float(data['time'])/1000
    if not 0 <= time.time()-observed < 30 or float(data['price']) <= 0:
        raise RuntimeError('rest_price_not_fresh')
    price={'price':float(data['price']), 'time':observed, 'source':'rest_ticker'}
    # A response racing a newer stream tick must not move time backwards.
    if observed >= store.get('price:'+symbol,{}).get('time',0):
        store.put('price:'+symbol,price)
    return price


async def refresh_market(symbol):
    from .engine import fetch_candles
    from .analysis import TF_MS
    cfg=store.settings()
    async with ClientSession(connector=connector(),timeout=ClientTimeout(total=15)) as session:
        for tf in cfg['timeframes']:
            old=store.candles(symbol,tf,1,False)
            count=min(cfg['bootstrap_bars'][tf], max(3,int((time.time()*1000-old[-1]['t'])/TF_MS[tf])+3)) if old else cfg['bootstrap_bars'][tf]
            rows=await fetch_candles(session,symbol,tf,count)
            store.save_candles(symbol,tf,rows)
        await refresh_price(session,symbol)
    store.put('request_refresh:'+symbol,time.time())


def refresh_for_analysis(symbol):
    asyncio.run(asyncio.wait_for(refresh_market(symbol),timeout=90))


def track_outage(symbol, now):
    key='data_outage:'+symbol
    state=store.get(key)
    if now-store.get('price:'+symbol,{}).get('time',0)<30:
        if state:store.put(key,None)
        return
    state=state or {'since':now,'notified':False}
    if now-state['since']>=120 and not state['notified'] and not store.get('paused',False):
        store.enqueue_message(symbol+' 시세 연결이 2분 이상 지연되고 있습니다. 보조 조회와 재연결을 시도 중이며, 복구 전에는 오래된 가격으로 분석하지 않습니다.')
        state['notified']=True
    store.put(key,state)


async def price_guard():
    import logging
    while True:
        for symbol in store.settings()['symbols']:
            if time.time()-store.get('price:'+symbol,{}).get('time',0)>15:
                try:
                    async with ClientSession(connector=connector(),timeout=ClientTimeout(total=10)) as session:
                        await refresh_price(session,symbol)
                except Exception as exc:
                    logging.getLogger('wave.collector').warning('price_fallback_failed %s %s',symbol,type(exc).__name__)
            track_outage(symbol,time.time())
        await asyncio.sleep(5)
