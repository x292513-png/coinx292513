"""Run as root on VPS after source upload. Idempotent; no secret output."""
import grp
import json
import os
import pwd
import secrets
import shutil
import subprocess
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path('/opt/trading-wave-monitor')


def main():
    try:pwd.getpwnam('tradewave')
    except KeyError:subprocess.run(['useradd','--system','--home-dir',str(ROOT),'--shell','/usr/sbin/nologin','tradewave'],check=True)
    subprocess.run(['usermod','-a','-G','tradewave','blog'],check=True)
    gid=grp.getgrnam('tradewave').gr_gid
    for name in ['data','data/charts','data/ai','data/reports','data/matplotlib']:
        p=ROOT/name;p.mkdir(parents=True,exist_ok=True);os.chown(p,0,gid);p.chmod(0o2770)
    (ROOT/'backups').mkdir(exist_ok=True);(ROOT/'backups').chmod(0o700)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup=ROOT/'backups'/stamp;backup.mkdir()
    for p in ['/etc/systemd/system/telegram-opsbot.service','/home/blog/telegram-ops/telegram_ops_bot.py']:
        shutil.copy2(p,backup/Path(p).name)
    (backup/'running-services.txt').write_text(subprocess.run(['systemctl','list-units','--type=service','--state=running','--no-pager','--no-legend'],capture_output=True,text=True).stdout)
    runtime=ROOT/'config/runtime.json'
    if not runtime.exists():
        from dotenv import dotenv_values
        env=dotenv_values('/home/blog/blog/.env')
        data={'telegram_token':env['TELEGRAM_BOT_TOKEN'],'chat_id':int(env['TELEGRAM_GROUP_ID']),'allowed_user':int(env['TELEGRAM_ALLOWED_USER']),'topic_id':None,'bridge_key':secrets.token_hex(32)}
        runtime.write_text(json.dumps(data))
    os.chown(runtime,0,gid);runtime.chmod(0o640)
    if not (ROOT/'.venv/bin/python').exists():subprocess.run(['python3','-m','venv',str(ROOT/'.venv')],check=True)
    print(json.dumps({'root':str(ROOT),'backup':str(backup),'runtime_config_ready':True}))


if __name__=='__main__':main()
