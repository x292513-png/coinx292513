"""Acceptance check for the historical-context and Telegram format upgrade."""
import datetime
import hashlib
import json
import pathlib
import sqlite3
import subprocess
import urllib.request

ROOT=pathlib.Path('/opt/trading-wave-monitor')


def main():
    c=sqlite3.connect('file:'+str(ROOT/'data/waves.sqlite3')+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
    with urllib.request.urlopen('http://127.0.0.1:8791/health',timeout=5) as r:health=json.load(r)
    assert health['ready']
    baseline=sorted((ROOT/'backups').glob('*/running-services.txt'))[0].read_text().splitlines()
    old_units=[l.strip().split()[0] for l in baseline if l.strip()]
    assert all(subprocess.run(['systemctl','is-active','--quiet',u]).returncode==0 for u in old_units)
    units={}
    for u in ['trading-wave-monitor','trading-wave-ai','trading-wave-learning','telegram-opsbot']:
        raw=subprocess.check_output(['systemctl','show',u,'-p','ActiveState','-p','MemoryCurrent','-p','InvocationID'],text=True)
        p=dict(line.split('=',1) for line in raw.splitlines() if '=' in line)
        assert p['ActiveState']=='active'
        if u!='telegram-opsbot':
            journal=subprocess.check_output(['journalctl','_SYSTEMD_INVOCATION_ID='+p['InvocationID'],'--no-pager','-o','cat'],text=True)
            assert 'Traceback' not in journal and ' ERROR ' not in journal
        units[u]=p
    summary=json.loads((ROOT/'data/learning-summary.json').read_text())
    assert len(summary['sources'])==16
    assert datetime.datetime.now().timestamp()-summary['updated_at']<3600
    format_check=json.loads(c.execute("SELECT value FROM kv WHERE key='telegram_format_verified'").fetchone()[0])
    assert {'bold','expandable_blockquote'}<=set(format_check['entities'])
    analyses=[]
    for symbol in ['BTCUSDT','ETHUSDT']:
        a=c.execute("SELECT * FROM analyses a WHERE symbol=? AND json_extract(snapshot,'$.historical_learning.status')='ready' AND EXISTS (SELECT 1 FROM outbox o WHERE o.analysis_id=a.id AND o.status='sent' AND o.chart IS NOT NULL) ORDER BY id DESC LIMIT 1",(symbol,)).fetchone()
        assert a,('No delivered learning analysis',symbol)
        r=json.loads(a['result']);s=json.loads(a['snapshot'])
        assert r['learning_comment'] and s['historical_learning']['status']=='ready'
        assert not s.get('stale_at_publication')
        sent=c.execute("SELECT text FROM outbox WHERE analysis_id=? AND status='sent' AND chart IS NOT NULL",(a['id'],)).fetchone()
        assert sent and json.loads(sent[0])['wave_format']=='html-v2'
        ids=[x[0] for x in c.execute('SELECT message_id FROM messages WHERE analysis_id=?',(a['id'],))]
        analyses.append({'id':a['id'],'symbol':symbol,'message_ids':ids,'learning_comment':r['learning_comment'],'latency':a['latency']})
    test=subprocess.run([str(ROOT/'.venv/bin/python'),'-m','unittest','discover','-s',str(ROOT/'tests'),'-q'],cwd=ROOT,capture_output=True,text=True)
    assert test.returncode==0,test.stderr
    original=pathlib.Path('/home/blog/telegram-ops/telegram_ops_bot.py')
    initial=sorted((ROOT/'backups').glob('*/telegram_ops_bot.py'))[0]
    report={'verified_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'health_ready':True,'previous_services_active':len(old_units),'units':units,'history_bars':sum(x['bars'] for x in summary['sources'].values()),'history_sources':len(summary['sources']),'telegram_entities':format_check,'analyses':analyses,'tests':test.stderr.split('----------------------------------------------------------------------')[-1].strip(),'original_bot_matches_initial_deployment':original.read_bytes()==initial.read_bytes(),'original_bot_mtime':datetime.datetime.fromtimestamp(original.stat().st_mtime,datetime.timezone.utc).isoformat(),'original_bot_sha256':hashlib.sha256(original.read_bytes()).hexdigest()}
    (ROOT/'data/reports/learning-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
