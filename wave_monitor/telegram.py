import json
import aiohttp
from . import store


async def call(method, payload, file=None):
    r=store.runtime()
    url='https://api.telegram.org/bot'+r['telegram_token']+'/'+method
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=35)) as s:
        if file:
            data=aiohttp.FormData()
            for k,v in payload.items(): data.add_field(k,json.dumps(v) if isinstance(v,(bool,dict,list)) else str(v))
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
    from .presentation import pages
    r=store.runtime();base={'chat_id':r['chat_id'],'message_thread_id':r['topic_id']}
    if reply_id:
        base['reply_parameters']={'message_id':reply_id,'allow_sending_without_reply':True}
    msgs=[]
    for index,page in enumerate(pages(text)):
        msg=await call('sendMessage',{**base,'text':page,'parse_mode':'HTML','disable_notification':index>0,'link_preview_options':{'is_disabled':True}});msgs.append(msg['message_id'])
        store.put('telegram_format_verified',{'message_id':msg['message_id'],'entities':sorted({x['type'] for x in msg.get('entities',[])})})
    if chart:
        # Telegram photo dimensions must sum <= 10000; chart renderer fits comfortably.
        msg=await call('sendPhoto',{'chat_id':r['chat_id'],'message_thread_id':r['topic_id'],'disable_notification':True,'caption':'📊 파동 · FVG/OB · 매물대 · RSI\n확대해서 보세요. 이 차트에 답장해도 분석을 이어갑니다.'},chart);msgs.append(msg['message_id'])
    return msgs
