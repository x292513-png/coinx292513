"""Resolve analysis references to durable Telegram report messages."""
import json
import re
import time
from html.parser import HTMLParser
from . import store

PATTERN = re.compile(r"(?<![\w/])#([0-9]+)(?![0-9])")

def message_url(message_id):
    r=store.runtime();chat=str(r['chat_id'])
    if not chat.startswith('-100'):return None
    topic=str(r.get('topic_id') or '')
    return 'https://t.me/c/'+chat[4:]+'/'+(topic+'/' if topic else '')+str(message_id)

def remember(aid,mid):
    store.put('analysis_message:'+str(aid),mid)
    with store.db() as c:
        c.execute('INSERT OR IGNORE INTO messages VALUES (?,?,?,?)',(mid,aid,time.time(),'analysis'))

def existing(aid):
    mid=store.get('analysis_message:'+str(aid))
    if mid:return mid
    # Legacy originals were sent with a chart. Invalidation-only messages are not originals.
    with store.db() as c:
        row=c.execute("SELECT m.message_id FROM messages m WHERE m.analysis_id=? AND EXISTS (SELECT 1 FROM outbox o WHERE o.analysis_id=m.analysis_id AND o.chart IS NOT NULL AND o.status='sent' AND o.created<=m.created) ORDER BY m.created,m.message_id LIMIT 1",(aid,)).fetchone()
    if row:remember(aid,row[0]);return row[0]

class Linker(HTMLParser):
    def __init__(self,urls):
        super().__init__(convert_charrefs=False);self.urls=urls;self.parts=[];self.blocked=0
    def handle_starttag(self,tag,attrs):
        self.parts.append(self.get_starttag_text())
        if tag in ('a','code','pre'):self.blocked+=1
    def handle_endtag(self,tag):
        self.parts.append('</'+tag+'>')
        if tag in ('a','code','pre'):self.blocked=max(0,self.blocked-1)
    def handle_data(self,data):
        def replace(m):
            url=self.urls.get(int(m[1]))
            return '<a href="'+url+'">'+m[0]+'</a>' if url else m[0]
        self.parts.append(data if self.blocked else PATTERN.sub(replace,data))
    def handle_entityref(self,name):self.parts.append('&'+name+';')
    def handle_charref(self,name):self.parts.append('&#'+name+';')

def linkify(page,urls):
    parser=Linker(urls);parser.feed(page);parser.close();return ''.join(parser.parts)

async def ensure(aid,call):
    mid=existing(aid)
    if mid:return message_url(mid)
    with store.db() as c:row=c.execute('SELECT * FROM analyses WHERE id=?',(aid,)).fetchone()
    if not row:return None
    from .presentation import format_analysis,pages
    r=store.runtime()
    report=pages(format_analysis(json.loads(row['result']),json.loads(row['snapshot']),aid,'archive'))
    # This archive preserves the original timestamp and interpretation, without a new AI call.
    notice='📚 <b>저장된 과거 분석 복원 · 현재 진입 신호 아님</b>\n당시 자동 알림에서 생략된 본문입니다. 아래 시각의 판단을 보존했습니다.'
    for index,page in enumerate(report):
        msg=await call('sendMessage',{'chat_id':r['chat_id'],'message_thread_id':r['topic_id'],'text':notice+'\n\n'+page if index==0 else page,'parse_mode':'HTML','disable_notification':True,'link_preview_options':{'is_disabled':True}})
        with store.db() as c:c.execute('INSERT OR IGNORE INTO messages VALUES (?,?,?,?)',(msg['message_id'],aid,time.time(),'archive'))
        if index==0:mid=msg['message_id']
    remember(aid,mid)
    return message_url(mid)
