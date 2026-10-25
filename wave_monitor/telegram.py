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


async def send(text, chart=None, reply_id=None, analysis_id=None):
    from .presentation import pages
    r=store.runtime();base={'chat_id':r['chat_id'],'message_thread_id':r['topic_id']}
    if reply_id:
        base['reply_parameters']={'message_id':reply_id,'allow_sending_without_reply':True}
    from .message_links import PATTERN,ensure,linkify,remember
    document=pages(text)
    own=analysis_id if chart else None
    refs={int(m[1]) for page in document for m in PATTERN.finditer(page)}
    urls={}
    for aid in sorted(refs-{own}):
        url=await ensure(aid,call)
        if url:urls[aid]=url
    msgs=[]
    for index,page in enumerate(document):
        page=linkify(page,urls)
        msg=await call('sendMessage',{**base,'text':page,'parse_mode':'HTML','disable_notification':index>0,'link_preview_options':{'is_disabled':True}});msgs.append(msg['message_id'])
        if index==0 and own:remember(own,msg['message_id'])
        store.put('telegram_format_verified',{'message_id':msg['message_id'],'entities':sorted({x['type'] for x in msg.get('entities',[])})})
    if chart:
        # Telegram photo dimensions must sum <= 10000; chart renderer fits comfortably.
        caption='📊 파동 · FVG/OB · 매물대 · RSI'
        if analysis_id:
            from datetime import datetime,timezone,timedelta
            with store.db() as c:a=c.execute('SELECT symbol,snapshot,created FROM analyses WHERE id=?',(analysis_id,)).fetchone()
            if a:
                snap=json.loads(a['snapshot']);asof=snap.get('asof',a['created'])
                stamp=datetime.fromtimestamp(asof,timezone(timedelta(hours=9))).strftime('%m/%d %H:%M KST')
                caption+=f"\n{a['symbol']} · 분석 #{analysis_id}\n차트 기준 {stamp} · 저장된 분석 당시 차트"
        caption+='\n확대해서 보세요. 사진에 답장하여 해당 분석에 질문할 수 있습니다.'
        msg=await call('sendPhoto',{**base,'disable_notification':True,'caption':caption},chart)
        if own and not msgs:remember(own,msg['message_id'])
        msgs.append(msg['message_id'])
    return msgs
