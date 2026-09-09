"""Create the dedicated topic and install attributable systemd units."""
import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from wave_monitor import store,telegram


async def main():
    cfg=store.runtime()
    me=await telegram.call('getMe',{})
    chat=await telegram.call('getChat',{'chat_id':cfg['chat_id']})
    if not chat.get('is_forum'):raise RuntimeError('configured_chat_is_not_forum')
    if not cfg['topic_id']:
        topic=await telegram.call('createForumTopic',{'chat_id':cfg['chat_id'],'name':'파동 트레이딩 · BTC / ETH','icon_color':7322096})
        cfg['topic_id']=topic['message_thread_id']
        path=store.ROOT/'config/runtime.json';path.write_text(json.dumps(cfg));path.chmod(0o640)
        print('created_dedicated_topic',cfg['topic_id'])
    store.init()
    for unit in ['trading-wave-monitor.service','trading-wave-ai.service']:
        shutil.copy2(store.ROOT/'systemd'/unit,Path('/etc/systemd/system')/unit)
    drop=Path('/etc/systemd/system/telegram-opsbot.service.d');drop.mkdir(exist_ok=True)
    (drop/'90-trading-wave.conf').write_text('[Service]\nExecStart=\nExecStart=/usr/bin/python3 /opt/trading-wave-monitor/integration/telegram_bridge.py\n')
    # SQLite and WAL must be shared by the two dedicated runtime processes.
    import grp
    gid=grp.getgrnam('tradewave').gr_gid
    for p in (store.ROOT/'data').iterdir():
        if p.is_file():os.chown(p,0,gid);p.chmod(0o660)
    subprocess.run(['systemctl','daemon-reload'],check=True)
    subprocess.run(['systemctl','enable','--now','trading-wave-monitor.service'],check=True)
    subprocess.run(['systemctl','restart','telegram-opsbot.service'],check=True)
    print('collector_and_bridge_started; AI worker waits for verified bootstrap')


if __name__=='__main__':asyncio.run(main())
