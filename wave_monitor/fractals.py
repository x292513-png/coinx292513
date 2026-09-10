"""Cross-timeframe, duration-normalized historical shape search and motif ledger.

Every closed-bar ending at 24/48/96 bars is indexed, without label hindsight.
Indexes are chunked/memory-mapped. Knowledge is descriptive evidence, not a
trained prediction model; outcomes are kept out of similarity and fingerprints.
"""
import asyncio
import json
import logging
import time
from collections import defaultdict,Counter
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from aiohttp import ClientSession,ClientTimeout
from . import store
from .learning import db,download,ENDPOINTS,contiguous
from .net import connector

NATIVE_FRAMES=['1M','1w','1d','4h','1h','15m']
DERIVED={'30m':('15m',1800000,2),'2h':('1h',7200000,2),'6h':('1h',21600000,6),'8h':('1h',28800000,8),'12h':('1h',43200000,12)}
FRAMES=NATIVE_FRAMES+list(DERIVED)
WINDOWS=[24,48,96]
POINTS=16
CHUNK=4096
VERSION=2
MAX_DISTANCE=.55
log=logging.getLogger('wave.fractals')
BAR=np.dtype([('t','i8'),('end','i8'),('c','f8')])
META=np.dtype([('start','i8'),('end','i8'),('known','i8'),('return_pct','f4'),('max_pct','f4'),('min_pct','f4')])


def root():
    p=store.ROOT/'data/fractals';p.mkdir(parents=True,exist_ok=True);return p


def atomic_json(path,data):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False));tmp.replace(path)


def date(t):return datetime.fromtimestamp(t/1000,timezone.utc).strftime('%Y-%m-%d %H:%M UTC')


def bars(market,symbol,tf):
    c=db()
    try:
        n=c.execute('SELECT COUNT(*) FROM bars WHERE market=? AND symbol=? AND tf=?',(market,symbol,tf)).fetchone()[0]
        it=c.execute('SELECT t,close_t,c FROM bars WHERE market=? AND symbol=? AND tf=? ORDER BY t',(market,symbol,tf))
        return np.fromiter((tuple(r) for r in it),dtype=BAR,count=n)
    finally:c.close()


def resample_history():
    """Construct complete UTC-aligned candles; incomplete/gapped groups excluded."""
    with db() as c:
        for market in ENDPOINTS:
            for symbol in store.settings()['symbols']:
                for tf,(base,period,expected) in DERIVED.items():
                    groups=c.execute('''SELECT CAST(t / ? AS INTEGER)*? AS bucket,MIN(t) AS first,MAX(t) AS last,MAX(h) AS hi,MIN(l) AS lo,SUM(v) AS volume,COUNT(*) AS n,SUM(close_t-t+1) AS span,MAX(close_t) AS ending FROM bars WHERE market=? AND symbol=? AND tf=? GROUP BY bucket HAVING n=? AND span=? AND first=bucket AND ending=bucket+?-1''',(period,period,market,symbol,base,expected,period,period)).fetchall()
                    prices={r['t']:(r['o'],r['c']) for r in c.execute('SELECT t,o,c FROM bars WHERE market=? AND symbol=? AND tf=?',(market,symbol,base))}
                    c.executemany('INSERT OR REPLACE INTO bars VALUES (?,?,?,?,?,?,?,?,?,?)',[(market,symbol,tf,g['bucket'],prices[g['first']][0],g['hi'],g['lo'],prices[g['last']][1],g['volume'],g['ending']) for g in groups])


def features(windows):
    """Interpolate log-price paths to 16 points; invariant to price scale."""
    windows=np.asarray(windows,dtype=float)
    p=np.linspace(0,windows.shape[1]-1,POINTS);lo=np.floor(p).astype(int);hi=np.ceil(p).astype(int);alpha=p-lo
    lp=np.log(windows)
    y=lp[:,lo]*(1-alpha)+lp[:,hi]*alpha
    y-=y[:,0,None]
    scale=lp.std(axis=1)
    return (y/np.maximum(scale[:,None],1e-7)).astype('f4'),scale


def fingerprint(f):
    # Coarse families, explicitly not claims of identical patterns.
    key=np.sign(np.diff(f[[0,2,4,6,8,10,12,15]])).astype(int)
    key[np.abs(np.diff(f[[0,2,4,6,8,10,12,15]]))<.25]=0
    changes=sum(a*b<0 for a,b in zip(key,key[1:]))
    endpoint=int(np.clip(np.round(f[-1]),-4,4))
    return ''.join({-1:'D',0:'F',1:'U'}[int(x)] for x in key)+':'+str(endpoint),changes


def family_label(key):
    route=[]
    for ch in key.split(':')[0]:
        word={'U':'상승','D':'하락','F':'완만한 구간'}[ch]
        if not route or route[-1]!=word:route.append(word)
    return ' → '.join(route)


def build_dataset(market,symbol,tf,window):
    data=bars(market,symbol,tf);horizon=window//2
    slug=f'{market}-{symbol}-{tf}-{window}';info_path=root()/(slug+'.json')
    if len(data)<window+horizon:return None
    signature=[len(data),int(data[-1]['end']),VERSION]
    if info_path.exists():
        old=json.loads(info_path.read_text())
        if old.get('signature')==signature:return old
    token=f"{int(data[-1]['end'])}-{len(data)}-v{VERSION}";base=slug+'-'+token
    # Files have immutable generation names; the manifest switches only after completion.
    n=len(data)-window-horizon+1
    fp=root()/(base+'-features.npy');mp=root()/(base+'-meta.npy')
    fa=np.lib.format.open_memmap(fp,mode='w+',dtype='f4',shape=(n,POINTS));ma=np.lib.format.open_memmap(mp,mode='w+',dtype=META,shape=(n,))
    gaps=np.r_[0,np.cumsum(data['t'][1:]!=data['end'][:-1]+1)]
    windows=np.lib.stride_tricks.sliding_window_view(data['c'],window)
    future=np.lib.stride_tricks.sliding_window_view(data['c'],horizon)
    occurrences=[];last_end={};prototypes={};key_names={};valid_count=0;last_detection=-window
    for a in range(0,n,CHUNK):
        b=min(n,a+CHUNK);starts=np.arange(a,b);ends=starts+window-1;known=ends+horizon
        f,scale=features(windows[a:b]);valid=(gaps[known]==gaps[starts]) & (scale>1e-7)
        fa[a:b]=f;fa[a:b][~valid]=np.nan
        m=np.zeros(b-a,dtype=META);m['start']=data['t'][starts];m['end']=data['end'][ends];m['known']=data['end'][known]
        m['return_pct']=(data['c'][known]/data['c'][ends]-1)*100
        fw=future[ends+1]
        m['max_pct']=(fw.max(axis=1)/data['c'][ends]-1)*100;m['min_pct']=(fw.min(axis=1)/data['c'][ends]-1)*100;ma[a:b]=m
        valid_count+=int(valid.sum())
        # Shifted windows of the same family are counted once per complete episode.
        diff=np.diff(f[:,[0,2,4,6,8,10,12,15]],axis=1)
        signs=np.sign(diff).astype(int);signs[np.abs(diff)<.25]=0
        turns=np.sum(signs[:,:-1]*signs[:,1:]<0,axis=1)
        codes=((signs+1)*3**np.arange(7)).sum(axis=1)*9+np.clip(np.round(f[:,-1]),-4,4).astype(int)+4
        for j in np.flatnonzero(valid & (turns>=2)):
            if a+j-last_detection<window//2:continue
            key=int(codes[j])
            if int(m[j]['start'])<=last_end.get(key,-1):continue
            proto=prototypes.setdefault(key,f[j].copy())
            distance=float(np.sqrt(np.mean((f[j]-proto)**2)))
            if distance>MAX_DISTANCE:continue
            last_end[key]=int(m[j]['known'])
            last_detection=a+j
            if key not in key_names:key_names[key]=fingerprint(f[j])[0]
            occurrences.append({'family':key_names[key],'start':int(m[j]['start']),'end':int(m[j]['end']),'known':int(m[j]['known']),'return_pct':float(m[j]['return_pct']),'market':market,'tf':tf,'window':window,'prototype':np.round(f[j],3).tolist()})
    fa.flush();ma.flush();del fa,ma
    op=root()/(base+'-occurrences.json');atomic_json(op,occurrences)
    info={'market':market,'symbol':symbol,'tf':tf,'construction':'UTC aggregation from '+DERIVED[tf][0] if tf in DERIVED else 'exchange native','window':window,'horizon':horizon,'rows':len(data),'first':int(data[0]['t']),'last':int(data[-1]['end']),'gaps':int(gaps[-1]),'signature':signature,'indexed_windows':valid_count,'features':fp.name,'meta':mp.name,'occurrences':op.name}
    atomic_json(info_path,info);log.info('fractal_indexed %s windows=%s',slug,valid_count)
    return info


def distinct(episodes):
    """Greedy earliest finishing episodes; overlap across markets/TFs counts once."""
    chosen=[];last=-1
    for e in sorted(episodes,key=lambda x:x['known']):
        if e['start']>last:chosen.append(e);last=e['known']
    return chosen


def publish_knowledge(index):
    knowledge={'version':VERSION,'updated_at':index['updated_at'],'symbols':{},'method':'16 log-price points normalized by window variation; every ending over 24/48/96 bars; coarse shape families with prototype RMS <=0.55; no mirror; nonoverlapping calendar episodes across TFs/markets; descriptive counts, not probabilities'}
    for symbol in store.settings()['symbols']:
        groups=defaultdict(list)
        for d in index['datasets']:
            if d['symbol']!=symbol:continue
            for e in json.loads((root()/d['occurrences']).read_text()):groups[e['family']].append(e)
        ranked=[]
        for key,episodes in groups.items():
            # All examples in a family must also be close to a common representative.
            ref=np.array(episodes[0]['prototype'])
            close=[e for e in episodes if float(np.sqrt(np.mean((np.array(e['prototype'])-ref)**2)))<=MAX_DISTANCE]
            picked=distinct(close)
            if len(picked)<3:continue
            recent=[e for e in picked if e['end']>=int((index['updated_at']-90*86400)*1000)]
            returns=[e['return_pct'] for e in picked]
            ranked.append({'family':key,'n':len(picked),'recent_90d_n':len(recent),'timeframes':dict(Counter(e['tf'] for e in picked)),'median_followthrough_pct':round(float(np.median(returns)),3),'up_n':sum(x>0 for x in returns),'prototype':ref.tolist(),'examples':[{k:v for k,v in e.items() if k!='prototype'} for e in (picked[:1]+picked[-2:])]})
        ranked.sort(key=lambda x:x['n'],reverse=True)
        knowledge['symbols'][symbol]={'repeated_families':len(ranked),'top_repeated':ranked[:30],'recent_active':sorted(ranked,key=lambda x:x['recent_90d_n'],reverse=True)[:10]}
    dest=store.ROOT/'data/knowledge';dest.mkdir(exist_ok=True)
    atomic_json(dest/'fractal-knowledge.json',knowledge)
    lines=['# 프랙탈 관찰 지식', '',f"갱신: {date(int(index['updated_at']*1000))}",f"원시 봉 {index['native_bars']:,}개 · 합성 봉 {index['derived_bars']:,}개 · 비교 창 {index['total_windows']:,}개",'', '월봉·주봉·일봉·12시간·8시간·6시간·4시간·2시간·1시간·30분·15분봉을 24/48/96봉 길이로 비교한다. 30분·2/6/8/12시간봉은 확정된 원시 봉을 UTC 기준으로 합성한다. 모든 봉 종료점을 검사하고 시간 공백을 가로지르는 창은 제외한다. 모양과 가격 크기/길이를 정규화하되 상하 반전은 적용하지 않는다.','', '다음은 근사 모양군의 빈도다. 같은 기간의 현물·선물·다른 시간봉은 한 사건으로 묶었다. 후속 가격은 각 사례 시간봉의 패턴 길이 절반 뒤 종가이며 서로 실제 경과시간이 다르므로 수익성이나 미래 확률로 사용하지 않는다.','']
    for symbol,d in knowledge['symbols'].items():
        lines += [f'## {symbol}',f"반복 모양군 {d['repeated_families']:,}개",'']
        for f in d['top_repeated'][:15]:
            lines += [f"### {family_label(f['family'])}",f"모양군 ID: {f['family']}",f"중복 제외 {f['n']}회 · 최근 90일 {f['recent_90d_n']}회 · 시간봉 {f['timeframes']}",f"후속 종가 상승 {f['up_n']}회 · 변화율 중앙값 {f['median_followthrough_pct']}% (개별 시간봉 기준)"]
            for e in f['examples']:lines.append(f"- {e['market']} {e['tf']} {e['window']}봉: {date(e['start'])} ~ {date(e['end'])}; 관찰 종료 {date(e['known'])}; 이후 {e['return_pct']:.3f}%")
            lines.append('')
    tmp=dest/'fractal-knowledge.tmp';tmp.write_text('\n'.join(lines));tmp.replace(dest/'fractal-knowledge.md')
    return knowledge


def build():
    resample_history()
    datasets=[]
    for market in ENDPOINTS:
        for symbol in store.settings()['symbols']:
            for tf in FRAMES:
                for window in WINDOWS:
                    d=build_dataset(market,symbol,tf,window)
                    if d:datasets.append(d)
    by_source={f"{d['market']}:{d['symbol']}:{d['tf']}":d['rows'] for d in datasets}
    native=sum(n for k,n in by_source.items() if k.split(':')[-1] in NATIVE_FRAMES)
    index={'updated_at':time.time(),'version':VERSION,'datasets':datasets,'total_bars':sum(by_source.values()),'native_bars':native,'derived_bars':sum(by_source.values())-native,'total_windows':sum(d['indexed_windows'] for d in datasets),'sources':len(by_source)}
    publish_knowledge(index)
    atomic_json(root()/'index.json',index)
    store.put('fractal_updated_at',index['updated_at']);store.put('fractal_error',None)
    # Completed analyses retain evidence in SQLite; old index generations need
    # only cover in-flight reads, not accumulate an entire new archive hourly.
    used={d[k] for d in datasets for k in ['features','meta','occurrences']}
    for p in root().iterdir():
        if p.name not in used and (p.suffix=='.npy' or p.name.endswith('-occurrences.json')) and time.time()-p.stat().st_mtime>7200:p.unlink()
    log.info('fractal_ready bars=%s windows=%s sources=%s',index['total_bars'],index['total_windows'],index['sources'])
    return index


def match_context(symbol,raw,asof,focus_1m=False):
    path=root()/'index.json'
    if not path.exists():return {'status':'building'}
    index=json.loads(path.read_text());queries={}
    for tf in ['1M','1w','1d','4h','1h','15m','5m']+(['1m'] if focus_1m else []):
        rows=raw.get(tf)
        if tf=='1h' and raw.get('5m'):
            groups=defaultdict(list)
            for r in raw['5m']:groups[r['t']//3600000*3600000].append(r)
            hourly=[{'t':t,'close_t':g[-1]['close_t'],'c':g[-1]['c']} for t,g in sorted(groups.items()) if len(g)==12 and g[0]['t']==t and g[-1]['close_t']==t+3600000-1 and contiguous(g)]
            if len(hourly)>=24:rows=hourly[-48:]
        if rows is None:
            c=db()
            try:rows=[dict(x) for x in reversed(c.execute('SELECT t,close_t,c FROM bars WHERE market=? AND symbol=? AND tf=? ORDER BY t DESC LIMIT 48',('futures',symbol,tf)).fetchall())]
            finally:c.close()
        if len(rows)<24 or not contiguous(rows[-48:]):continue
        rows=rows[-48:];f,scale=features([[r['c'] for r in rows]])
        if scale[0]<=1e-7:continue
        queries[tf]={'feature':f[0],'start':rows[0]['t'],'end':rows[-1]['close_t'],'window':len(rows),'matches':[]}
    for d in index['datasets']:
        if d['symbol']!=symbol:continue
        fa=np.load(root()/d['features'],mmap_mode='r');ma=np.load(root()/d['meta'],mmap_mode='r')
        for a in range(0,len(fa),CHUNK):
            f=np.asarray(fa[a:a+CHUNK]);m=ma[a:a+CHUNK]
            for tf,q in queries.items():
                if tf==d['tf']:continue
                delta=f-q['feature'];dist=np.sqrt(np.mean(delta*delta,axis=1))
                valid=np.isfinite(dist) & (dist<=MAX_DISTANCE) & (m['known']<min(q['start'],asof*1000))
                ids=np.flatnonzero(valid)
                if not len(ids):continue
                best=ids[np.argsort(dist[ids])[:12]]
                for j in best:
                    q['matches'].append({'id':f"{tf}:{d['market']}:{d['tf']}:{d['window']}:{int(m[j]['start'])}",'source_tf':d['tf'],'source_construction':d.get('construction','exchange native'),'market':d['market'],'window_bars':d['window'],'horizon_bars':d['horizon'],'start':int(m[j]['start']),'end':int(m[j]['end']),'known':int(m[j]['known']),'distance':round(float(dist[j]),4),'return_pct':round(float(m[j]['return_pct']),3),'max_close_return_pct':round(float(m[j]['max_pct']),3),'min_close_return_pct':round(float(m[j]['min_pct']),3)})
            # Keep a bounded candidate pool, with temporal diversity before truncation.
        del fa,ma
        for q in queries.values():q['matches']=diverse_nearest(q['matches'],40)
    out={'status':'ready' if asof-index['updated_at']<3*3600 else 'stale','updated_at':index['updated_at'],'scanned_windows':index['total_windows'],'queries':{},'interpretation':'RMS shape distance, not odds. Cross-TF only; calendar overlaps removed; horizons measured in source bars. No mirrored patterns.'}
    for tf,q in queries.items():
        picks=diverse_nearest(q['matches'],6)
        out['queries'][tf]={'query_start':q['start'],'query_end':q['end'],'query_window_bars':q['window'],'n':len(picks),'examples':picks[:3],'small_sample':len(picks)<20}
    kp=store.ROOT/'data/knowledge/fractal-knowledge.json'
    if kp.exists():
        knowledge=json.loads(kp.read_text()).get('symbols',{}).get(symbol,{})
        out['recurring_families']=[{k:v for k,v in f.items() if k not in ['prototype','examples']} for f in knowledge.get('top_repeated',[])[:3]]
    return out


def diverse_nearest(matches,limit):
    selected=[]
    for e in sorted(matches,key=lambda x:x['distance']):
        if any(not(e['known']<p['start'] or e['start']>p['known']) for p in selected):continue
        selected.append(e)
        if len(selected)>=limit:break
    return selected


def report_text():
    from .presentation import pack,quoted
    path=store.ROOT/'data/knowledge/fractal-knowledge.json'
    if not path.exists():return '🔁 교차 시간봉 프랙탈 자료를 준비 중이에요. 완료 후 /fractal 로 확인할 수 있어요.'
    d=json.loads(path.read_text());index=json.loads((root()/'index.json').read_text())
    blocks=[f"🔁 <b>프랙탈 관찰 지식</b>\n{date(int(d['updated_at']*1000))}\n원시·합성 봉 {index['total_bars']:,}개 · 비교 창 {index['total_windows']:,}개\n월봉부터 15분까지 11종 시간봉을 서로 비교합니다."]
    for symbol,s in d['symbols'].items():
        lines=[f"반복 모양군 {s['repeated_families']:,}개"]
        for f in s['top_repeated'][:5]:
            lines.append(f"\n{family_label(f['family'])}\n중복 제외 {f['n']}회 / 최근 90일 {f['recent_90d_n']}회\n발견 시간봉: {', '.join(f['timeframes'])}")
            for e in f['examples'][-1:]:lines.append(f"최근 사례: {e['market']} {e['tf']} {date(e['end'])}")
        blocks+=quoted(symbol+' · 많이 반복된 모양군', '\n'.join(lines))
    blocks.append('서로 닮은 움직임을 묶은 기록이며 파동의 확정 카운팅은 아닙니다. 같은 시기의 중복 사례를 제거했고, 빈도 자체를 예측 확률로 쓰지 않습니다. 현재와 닮은 개별 사례는 BTC 분석 / ETH 분석으로 확인해요.')
    return pack(blocks)


async def main():
    while True:
        try:
            async with ClientSession(connector=connector(),timeout=ClientTimeout(total=35)) as s:
                for market in ENDPOINTS:
                    for symbol in store.settings()['symbols']:
                        for tf in NATIVE_FRAMES:await download(s,market,symbol,tf)
            await asyncio.to_thread(build)
        except Exception as e:
            log.exception('fractal_refresh_failed');store.put('fractal_error',{'time':time.time(),'type':type(e).__name__})
        await asyncio.sleep(3600)


if __name__=='__main__':
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    asyncio.run(main())
