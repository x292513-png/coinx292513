import json
import time
from datetime import datetime,timezone,timedelta
from . import store


def evaluate(result,price,rows):
    """Paper scenario checkpoints, not actual trades. Same-minute ambiguity preserved."""
    from .engine import is_invalid
    target=(result.get('targets') or [None])[0];bias=result['bias']
    if bias=='neutral' or not target or not result.get('invalidation_price'):
        outcome='not_directional'
    else:
        outcome='no_level_hit'
        for c in rows:
            hit_target=(bias=='bullish' and c['h']>=target) or (bias=='bearish' and c['l']<=target)
            hit_invalid=is_invalid(result,c['l']) or is_invalid(result,c['h'])
            if hit_target and hit_invalid:outcome='same_minute_ambiguous';break
            if hit_target:outcome='target_before_invalidation';break
            if hit_invalid:outcome='invalidation_first';break
    return {'outcome':outcome,'reference_price':price,'last_price':rows[-1]['c'] if rows else None,'max_price':max((x['h'] for x in rows),default=None),'min_price':min((x['l'] for x in rows),default=None),'bars':len(rows),'note':'분석 당시 기준가격 이후 가격경로. 실제 진입/체결/수익률 아님.'}


def report_text():
    start=store.get('started_at',time.time());elapsed=(time.time()-start)/86400
    with store.db() as c:
        total=c.execute('SELECT COUNT(*) FROM analyses').fetchone()[0]
        calls=c.execute('SELECT COUNT(*),SUM(ok) FROM calls').fetchone()
        avg=c.execute('SELECT AVG(latency) FROM analyses').fetchone()[0]
        evs=c.execute('SELECT hours,data FROM evaluations').fetchall()
        events=c.execute('SELECT kind,COUNT(*) n FROM events GROUP BY kind').fetchall()
        rows=c.execute('SELECT symbol,result FROM analyses ORDER BY created').fetchall()
        zones=c.execute('SELECT outcome,COUNT(*) FROM zone_visits WHERE outcome IS NOT NULL GROUP BY outcome').fetchall()
        deliveries=c.execute('SELECT MIN(m.created)-o.created FROM outbox o JOIN messages m ON m.analysis_id=o.analysis_id AND m.created>=o.created WHERE o.status=\'sent\' GROUP BY o.id').fetchall()
        failed_deliveries=c.execute("SELECT COUNT(*) FROM outbox WHERE status!='sent' AND attempts>0").fetchone()[0]
    counts={};flips=0;recounts=0;previous={};prior_labels={}
    for r in rows:
        state=json.loads(r['result'])['bias'];p=previous.get(r['symbol'])
        if p and p!=state:flips+=1
        previous[r['symbol']]=state
        labels={(p['tf'],p['t'],p['price']):p['label'] for p in json.loads(r['result']).get('wave_labels',[])}
        old=prior_labels.get(r['symbol'],{})
        if any(old[k]!=labels[k] for k in old.keys() & labels.keys()):recounts+=1
        prior_labels[r['symbol']]=labels
    for h,d in evs:
        d=json.loads(d);key=f"{h}h {d['outcome']}";counts[key]=counts.get(key,0)+1
    avg_delivery=sum(x[0] for x in deliveries)/len(deliveries) if deliveries else 0
    lines=[f"파동 감시 검증 · {elapsed:.1f}/7일",f"분석 {total}건 / AI 호출 {calls[0]}회 / 성공 {calls[1] or 0}회",f"평균 AI 처리 {avg or 0:.1f}초 / 방향 변경 {flips}회 / 같은 고저점 라벨 변경 {recounts}회",f"평균 발송 대기 {avg_delivery:.1f}초 / 전송 재시도·실패 {failed_deliveries}건",'']
    labels={'target_before_invalidation':'목표 우선 도달','invalidation_first':'무효화 우선','same_minute_ambiguous':'같은 1분봉 내 순서 불명','no_level_hit':'기준 미도달','not_directional':'방향성 평가 제외','data_gap':'데이터 누락으로 평가 보류'}
    for key,n in sorted(counts.items()):
        h,outcome=key.split(' ',1);lines.append(f"{h} · {labels.get(outcome,outcome)}: {n}건")
    if not counts:lines.append('1시간/4시간/24시간 관찰 결과가 쌓이면 여기에 표시됩니다.')
    if zones:
        lines+=['','관심 가격대 진입 후 1시간 반응']
        names={'support_held':'지지 유지','support_broken':'지지 하단 종가 이탈','resistance_rejected':'저항 아래 유지','resistance_broken':'저항 상단 종가 돌파','watch_above':'관심대 위 마감','watch_below':'관심대 아래 마감','inside':'구간 안 마감','data_gap':'데이터 부족'}
        for outcome,n in zones:lines.append(f"{names.get(outcome,outcome)}: {n}건")
    for symbol in store.settings()['symbols']:
        cov=store.get('trade_coverage:'+symbol,{})
        lines.append(f"{symbol} 체결 수집 연결 공백 {len(cov.get('gaps',[]))}회 / 누락 집계 ID {cov.get('missing_aggregate_ids',0)}개")
    lines+=['','알림 지연·누락, 파동 카운팅 변경, 매물대 반응을 당시 기록으로 검토합니다. 확신도는 해석 점수이며 이 보고서는 실제 매매 수익률이 아닙니다.']
    return '\n'.join(lines)


def status_text():
    now=time.time();cfg=store.settings();lines=['파동 트레이딩 상태',f"자동 분석: {'일시중지' if store.get('paused',False) else '실행'}",f"실시간 스트림: {'연결' if store.get('ws_connected') else '재연결 중'} / 마지막 이벤트 {now-store.get('ws_last_event',0):.0f}초 전"]
    for s in cfg['symbols']:
        p=store.get('price:'+s,{});a=store.latest(s)
        lines.append(f"{s}: {p.get('price','대기')} · 데이터 {now-p.get('time',0):.0f}초 전 · 최신 분석 #{a['id'] if a else '-'}")
    from .budget import day_start,reset_label
    day=day_start(now)
    with store.db() as c:
        counts=dict(c.execute('SELECT kind,COUNT(*) FROM calls WHERE started>=? GROUP BY kind',(day,)).fetchall())
        pending=c.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('pending','running')").fetchone()[0]
    lines += [f"오늘 AI: 자동 {counts.get('auto',0)}/{cfg['auto_calls_per_day']} · 질문 {counts.get('manual',0)}/{cfg['manual_calls_per_day']}",f"분석 대기/진행 {pending}건",'', '분석해줘 → BTC·ETH를 지금 기준으로 새 분석 / 비트 분석해줘 / 이더 분석해줘', '/status 상태 · /report 검증 · stop 또는 스탑 중지 · start 재개']
    lines += [f'프로그램 하루 상한 · 종목 합산 / 실패 시도 포함 · Codex 계정 한도와 별개',f'다음 초기화: {reset_label(now)}']
    if cfg.get('notification_mode')=='twice_daily':lines += ['알림: 09:00·21:00 KST BTC·ETH 통합 브리핑 · 5분 2% / 15분 3% / 1시간 4% 급변 예외']
    elif cfg.get('notification_mode')=='hourly':lines += ['알림: 매시 정각 BTC·ETH 통합 브리핑 · 5분 2% / 15분 3% / 1시간 4% 급변 예외']
    updated=store.get('learning_updated_at')
    lines.extend(['',f"과거 사례 갱신: {((now-updated)/3600):.1f}시간 전" if updated else '과거 사례: 첫 수집 준비 중','/learn 과거 패턴 비교 · 과거 수집과 통계 계산은 AI 호출 없음'])
    fractal=store.get('fractal_updated_at')
    lines.extend([f"교차 시간봉 프랙탈 갱신: {(now-fractal)/3600:.1f}시간 전" if fractal else '교차 시간봉 프랙탈: 첫 자료 준비 중','/fractal 반복 패턴 지식'])
    return '\n'.join(lines)


def maintenance():
    now=time.time()
    with store.db() as c:
        rows=c.execute('SELECT * FROM analyses WHERE created>?',(now-8*86400,)).fetchall()
        for r in rows:
            for h in [1,4,24]:
                end=r['created']+h*3600
                if end>now or c.execute('SELECT 1 FROM evaluations WHERE analysis_id=? AND hours=?',(r['id'],h)).fetchone():continue
                candles=[dict(x) for x in c.execute("SELECT * FROM candles WHERE symbol=? AND tf='1m' AND closed=1 AND t>=? AND close_t<=? ORDER BY t",(r['symbol'],r['created']*1000,end*1000)).fetchall()]
                snap=json.loads(r['snapshot']);result=json.loads(r['result'])
                data=evaluate(result,snap.get('publication_price',snap['price'])['price'],candles)
                if snap.get('stale_at_publication'):data['outcome']='not_directional'
                if len(candles)<h*60-2:data['outcome']='data_gap'
                c.execute('INSERT INTO evaluations VALUES (?,?,?,?)',(r['id'],h,now,json.dumps(data)))
        cutoff=(now-store.settings()['retention_days']*86400)*1000
        c.execute("DELETE FROM candles WHERE tf IN ('1m','5m','15m') AND t<?",(cutoff,))
        c.execute('DELETE FROM trade_bins WHERE hour<?',(now-8*86400,))
        c.execute('DELETE FROM events WHERE created<?',(now-45*86400,))
        visits=c.execute('SELECT * FROM zone_visits WHERE outcome IS NULL AND created<?',(now-3600,)).fetchall()
        for v in visits:
            candles=c.execute("SELECT c FROM candles WHERE symbol=? AND tf='1m' AND closed=1 AND t>=? AND close_t<=? ORDER BY t",(v['symbol'],v['created']*1000,(v['created']+3600)*1000)).fetchall()
            if len(candles)<58:outcome='data_gap'
            else:
                close=candles[-1][0]
                if v['role']=='support':outcome='support_held' if close>=v['low'] else 'support_broken'
                elif v['role']=='resistance':outcome='resistance_rejected' if close<=v['high'] else 'resistance_broken'
                else:outcome='watch_above' if close>v['high'] else ('watch_below' if close<v['low'] else 'inside')
            c.execute('UPDATE zone_visits SET outcome=? WHERE id=?',(outcome,v['id']))
    day=datetime.fromtimestamp(now,timezone(timedelta(hours=9))).strftime('%Y-%m-%d')
    reports=store.ROOT/'data/reports';reports.mkdir(exist_ok=True)
    if store.get('daily_report_day')!=day and now-store.get('started_at',now)>3600:
        text=report_text();(reports/(day+'.txt')).write_text(text)
        if not __import__('wave_monitor.cadence',fromlist=['enabled']).enabled():store.enqueue_message(text)
        store.put('daily_report_day',day)
    if now-store.get('started_at',now)>=7*86400 and not store.get('seven_day_report_sent'):
        text='일주일 검증 기간이 끝났어요. 감시는 계속됩니다.\n\n'+report_text()
        (reports/'seven-day-review.txt').write_text(text)
        if not __import__('wave_monitor.cadence',fromlist=['enabled']).enabled():store.enqueue_message(text)
        store.put('seven_day_report_sent',now)
    # Limit chart and transient model files without deleting durable analyses.
    for folder,days in [('charts',14),('ai',2)]:
        p=store.ROOT/'data'/folder
        if p.exists():
            for f in p.iterdir():
                if f.is_file() and now-f.stat().st_mtime>days*86400:f.unlink()
