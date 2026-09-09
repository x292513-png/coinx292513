import json
import aiohttp
from . import store


async def call(method, payload, file=None):
    r=store.runtime()
    url='https://api.telegram.org/bot'+r['telegram_token']+'/'+method
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=35)) as s:
        if file:
            data=aiohttp.FormData()
            for k,v in payload.items(): data.add_field(k,str(v))
            with open(file,'rb') as f:
                data.add_field('photo',f,filename='wave-chart.png',content_type='image/png')
                async with s.post(url,data=data) as response: body=await response.json()
        else:
            async with s.post(url,json=payload) as response: body=await response.json()
    if not body.get('ok'):
        # Never log request URLs or tokens.
        raise RuntimeError('telegram_'+str(body.get('error_code'))+'_'+str(body.get('description',''))[:120])
    return body['result']


async def send(text, chart=None, reply_id=None):
    r=store.runtime();base={'chat_id':r['chat_id'],'message_thread_id':r['topic_id']}
    if reply_id:
        base['reply_parameters']={'message_id':reply_id,'allow_sending_without_reply':True}
    msgs=[]
    for start in range(0,len(text),3800):
        msg=await call('sendMessage',{**base,'text':text[start:start+3800],'link_preview_options':{'is_disabled':True}});msgs.append(msg['message_id'])
    if chart:
        # Telegram photo dimensions must sum <= 10000; chart renderer fits comfortably.
        msg=await call('sendPhoto',{'chat_id':r['chat_id'],'message_thread_id':r['topic_id'],'caption':'파동·매물대·RSI 자동 차트 · 알림에 답장하면 같은 분석을 이어갑니다.'},chart);msgs.append(msg['message_id'])
    return msgs
