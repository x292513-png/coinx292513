"""Load the existing bot unchanged; route only the dedicated trading topic."""
import asyncio
import importlib.util
import json
import logging
import sys
import urllib.request
from pathlib import Path

ROOT=Path('/opt/trading-wave-monitor')
ORIGINAL=Path('/home/blog/telegram-ops/telegram_ops_bot.py')


def forward(payload):
    cfg=json.loads((ROOT/'config/runtime.json').read_text())
    req=urllib.request.Request('http://127.0.0.1:8791/inbox',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','X-Wave-Key':cfg['bridge_key']},method='POST')
    with urllib.request.urlopen(req,timeout=8) as r:return json.load(r)


def install(bot):
    original=bot.handle_text
    async def routed(update,context):
        msg=update.effective_message
        try:cfg=json.loads((ROOT/'config/runtime.json').read_text())
        except (OSError,ValueError):return await original(update,context)
        topic=msg.message_thread_id if msg and msg.is_topic_message else None
        topics={cfg['topic_id']}
        if cfg.get('paper_topic_id') is not None:topics.add(cfg['paper_topic_id'])
        if topic not in topics or update.effective_chat.id!=cfg['chat_id']:
            return await original(update,context)
        if update.effective_user.id!=cfg['allowed_user']:return
        reply=getattr(msg,'reply_to_message',None)
        payload={'user_id':update.effective_user.id,'chat_id':update.effective_chat.id,'topic_id':topic,'message_id':msg.message_id,'text':msg.text or '', 'reply_id':reply.message_id if reply else None}
        try:await asyncio.to_thread(forward,payload)
        except Exception as e:
            logging.warning('wave_bridge_unavailable %s',type(e).__name__)
            await msg.reply_text('파동 감시 연결을 잠시 확인하고 있어요. 조금 뒤 다시 보내주세요.',message_thread_id=topic)
    bot.handle_text=routed


def main():
    sys.path.insert(0,str(ORIGINAL.parent))
    spec=importlib.util.spec_from_file_location('existing_telegram_ops',ORIGINAL)
    bot=importlib.util.module_from_spec(spec);spec.loader.exec_module(bot)
    install(bot);bot.main()


if __name__=='__main__':main()
