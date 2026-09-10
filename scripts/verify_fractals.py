"""Live acceptance checks for cross-timeframe memory and its delivered analyses."""
import datetime
import json
import pathlib
import sqlite3
import subprocess
import time
import urllib.request

ROOT=pathlib.Path('/opt/trading-wave-monitor')

def main():
    with urllib.request.urlopen('http://127.0.0.1:8791/health',timeout=5) as response:health=json.load(response)
    assert health['ready']
    index=json.loads((ROOT/'data/fractals/index.json').read_text())
    assert index['version']==2 and index['sources']==44
    assert len({d['tf'] for d in index['datasets']})==11
    assert {d['window'] for d in index['datasets']}=={24,48,96}
    assert time.time()-index['updated_at']<10800
    knowledge=json.loads((ROOT/'data/knowledge/fractal-knowledge.json').read_text())
    assert (ROOT/'data/knowledge/fractal-knowledge.md').stat().st_size>500
    assert all(s['repeated_families']>0 for s in knowledge['symbols'].values())
    baseline=sorted((ROOT/'backups').glob('*/running-services.txt'))[0].read_text().splitlines()
    previous=[l.strip().split()[0] for l in baseline if l.strip()]
    assert all(subprocess.run(['systemctl','is-active','--quiet',u]).returncode==0 for u in previous)
    units={}
    for u in ['trading-wave-monitor','trading-wave-ai','trading-wave-learning','trading-wave-fractals','telegram-opsbot']:
        text=subprocess.check_output(['systemctl','show',u,'-p','ActiveState','-p','MemoryCurrent','-p','InvocationID'],text=True)
        units[u]=dict(x.split('=',1) for x in text.splitlines() if '=' in x)
        assert units[u]['ActiveState']=='active'
        if u=='trading-wave-fractals':
            journal=subprocess.check_output(['journalctl','_SYSTEMD_INVOCATION_ID='+units[u]['InvocationID'],'-o','cat','--no-pager'],text=True)
            assert 'Traceback' not in journal and ' ERROR ' not in journal
    c=sqlite3.connect('file:'+str(ROOT/'data/waves.sqlite3')+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
    outputs=[]
    for symbol in ['BTCUSDT','ETHUSDT']:
        a=c.execute("SELECT * FROM analyses a WHERE symbol=? AND json_extract(snapshot,'$.fractal_memory.status')='ready' AND EXISTS (SELECT 1 FROM outbox o WHERE o.analysis_id=a.id AND o.status='sent' AND o.chart IS NOT NULL) ORDER BY id DESC LIMIT 1",(symbol,)).fetchone()
        assert a,('No delivered fractal analysis',symbol)
        s=json.loads(a['snapshot']);r=json.loads(a['result'])
        assert r['fractal_comment'] and r['fractal_example_ids'] and r['fractal_evidence']
        assert s['analysis_principles'] and s['recent_dialogue']
        valid={e['id'] for q in s['fractal_memory']['queries'].values() for e in q['examples']}
        assert all(x in valid for x in r['fractal_example_ids'])
        for e in r['fractal_evidence']:
            assert e['source_tf']!=e['query_tf']
            assert e['known']<s['fractal_memory']['queries'][e['query_tf']]['query_start']
        ids=[x[0] for x in c.execute('SELECT message_id FROM messages WHERE analysis_id=?',(a['id'],))]
        outputs.append({'id':a['id'],'symbol':symbol,'message_ids':ids,'fractal_comment':r['fractal_comment'],'evidence':r['fractal_evidence'],'recent_dialogue_turns':len(s['recent_dialogue'])})
    fmt=json.loads(c.execute("SELECT value FROM kv WHERE key='telegram_format_verified'").fetchone()[0])
    assert 'expandable_blockquote' in fmt['entities']
    report={'verified_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'ready':True,'native_bars':index['native_bars'],'derived_bars':index['derived_bars'],'windows':index['total_windows'],'timeframes':sorted({d['tf'] for d in index['datasets']}),'sources':index['sources'],'previous_services_active':len(previous),'units':units,'knowledge_families':{s:v['repeated_families'] for s,v in knowledge['symbols'].items()},'analyses':outputs,'telegram_entities':fmt}
    (ROOT/'data/reports/fractal-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
