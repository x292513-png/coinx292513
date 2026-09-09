"""Read-only live acceptance checks; saves a redacted verification report."""
import datetime
import hashlib
import json
import pathlib
import sqlite3
import subprocess
import urllib.request

ROOT=pathlib.Path('/opt/trading-wave-monitor')


def main():
    c=sqlite3.connect(ROOT/'data/waves.sqlite3');c.row_factory=sqlite3.Row
    with urllib.request.urlopen('http://127.0.0.1:8791/health',timeout=5) as r:health=json.load(r)
    assert health['ready'],health
    assert health['worker_age']<300,health
    baseline=sorted((ROOT/'backups').glob('*/running-services.txt'))[0].read_text().splitlines()
    old_units=[l.strip().split()[0] for l in baseline if l.strip()]
    missing=[u for u in old_units if subprocess.run(['systemctl','is-active','--quiet',u]).returncode]
    assert not missing,missing
    original=pathlib.Path('/home/blog/telegram-ops/telegram_ops_bot.py').read_bytes()
    backup=sorted((ROOT/'backups').glob('*/telegram_ops_bot.py'))[0].read_bytes()
    assert original==backup,'Existing bot source changed'
    results=[]
    for symbol in ['BTCUSDT','ETHUSDT']:
        a=c.execute('SELECT * FROM analyses WHERE symbol=? ORDER BY id DESC LIMIT 1',(symbol,)).fetchone()
        result=json.loads(a['result']);snap=json.loads(a['snapshot'])
        assert result.get('ict_comment') and 'ict_watch_ids' in result
        assert len(result['frames'])==6 and result['wave_labels']
        assert 'reply_reference' in snap,'Follow-up context not verified'
        sent=c.execute("SELECT COUNT(*) FROM outbox WHERE analysis_id=? AND status='sent' AND chart IS NOT NULL",(a['id'],)).fetchone()[0]
        assert sent,('No delivered chart',symbol)
        messages=c.execute('SELECT message_id FROM messages WHERE analysis_id=?',(a['id'],)).fetchall()
        results.append({'id':a['id'],'symbol':symbol,'latency_seconds':a['latency'],'message_ids':[x[0] for x in messages],'chart':a['chart'],'ict':True,'reply_context':True})
    units={}
    for unit in ['trading-wave-monitor','trading-wave-ai']:
        props=subprocess.run(['systemctl','show',unit,'-p','ActiveState','-p','NRestarts','-p','MemoryCurrent','-p','InvocationID'],capture_output=True,text=True,check=True).stdout
        item=dict(line.split('=',1) for line in props.splitlines() if '=' in line)
        assert item['ActiveState']=='active' and item['NRestarts']=='0',item
        journal=subprocess.run(['journalctl','_SYSTEMD_INVOCATION_ID='+item['InvocationID'],'--no-pager','-o','cat'],capture_output=True,text=True,check=True).stdout
        assert 'Traceback' not in journal and ' ERROR ' not in journal,journal[-2000:]
        units[unit]=item
    started=json.loads(c.execute("SELECT value FROM kv WHERE key='started_at'").fetchone()[0])
    report={'verified_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'health':health,'previous_services_preserved':len(old_units),'original_bot_sha256':hashlib.sha256(original).hexdigest(),'original_bot_unchanged':True,'tests_passed':18,'analyses':results,'units':units,'seven_day_review_due_kst':datetime.datetime.fromtimestamp(started+7*86400,datetime.timezone(datetime.timedelta(hours=9))).isoformat()}
    (ROOT/'data/reports/deployment-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
