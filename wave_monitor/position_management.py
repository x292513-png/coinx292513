"""Forward-only, reviewed paper position management. Never exchange orders."""
import json,time,math
from html import escape
import jsonschema
from . import store
from .presentation import pack

PROMPT='''가상 보유 포지션의 대응을 결정한다. 일봉/4h/1h/15m 파동과 서적 규칙을 우선하고 ICT/채널/피보나치/지표 및 실제 전문팀 보고를 비교한다. 감정이 없다는 이유로 판단이 정확하다고 가정하지 않는다. 현재 열린 포지션의 유지(hold), 일부 축소(reduce), 전량 청산(exit), 추가 진입(add) 중 선택한다. 단순 손실이나 수익 목표 때문에 물타기하지 않는다. add는 가설 유효성과 새 가격 확인 근거를 명시하고 추가 후 평균가/손익비/청산 여유를 평가한다. 전문팀 불완전이면 add 금지. confidence는 통계적 승률이 아니다.
stop_mode=touch는 구조 손절 접촉, close는 stop_tf 확정봉 종가로 가설 무효화를 판단한다. close를 채택하면 꼬리 스윕을 허용하는 파동 근거와 더 바깥 emergency_stop의 가격 근거가 필수다. emergency_stop은 급변/AI 장애 중에도 유지하며 격리 청산 추정선보다 안쪽이어야 한다. 무한 손절 확장 금지: 기존 가설 변경 이유를 명시한다. 새 stop은 현재 가격보다 불리한 방향, tp1/tp2는 유리한 방향 순서다. 이미 무효화된 가설은 exit, 회복을 꾸며 hold/add 금지.
추가 진입/청산은 결과 이후 관측되는 다음 1분봉 시가로 가상 실행한다. add는 지정한 entry_low~entry_high 안에서만 실행되고 추가 가격 기준 TP1 손익비 1.5 이상이어야 한다. add_margin_pct는 현재 실현잔고 대비 새로 배정할 증거금 비율(0~100), free margin 안에서 제한된다. leverage는 기존 포지션 유지. reduce_pct는 현재 잔량의 축소 비율. review_hours는 이번 판단의 유효 보유 연장시간(1~24); 검토 실패하면 기존 보호 규칙을 유지한다. 동일 계획에 대한 반복 검토로 무의미한 추가 진입 금지. reason에 판단 근거, 반대 증거, 무엇이 달라졌는지 간결히 적는다.'''

def schema():
 p={'action':{'type':'string','enum':['hold','reduce','exit','add']},'reason':{'type':'string','minLength':10,'maxLength':800},'stop_mode':{'type':'string','enum':['touch','close']},'stop_tf':{'type':'string','enum':['5m','15m','1h','4h']}}
 for k in ('stop','emergency_stop','tp1','tp2','entry_low','entry_high'):p[k]={'type':'number','exclusiveMinimum':0}
 for k in ('add_margin_pct','reduce_pct'):p[k]={'type':'number','minimum':0,'maximum':100}
 p['review_hours']={'type':'number','minimum':1,'maximum':24}
 return dict(type='object',properties=p,required=list(p),additionalProperties=False)

def positions(symbol):
 from .paper import read_states
 with store.db() as c:return [p for p in read_states(c) if p.get('symbol')==symbol and p.get('status')=='open']

def fingerprint(p):return [p['id'],p['qty'],p['average'],p['stop'],p.get('tp1_done'),p.get('management_revision',0)]

def validate(d,p,price,complete=True):
 from .paper import liquidation_price
 jsonschema.validate(d,schema())
 if not all(math.isfinite(v) for v in d.values() if isinstance(v,(int,float))):raise ValueError('nonfinite_management')
 if d['action']=='exit':return
 s=p['sign']
 if min((price-d['stop'])*s,(d['tp1']-price)*s,(d['tp2']-d['tp1'])*s)<=0:raise ValueError('management_price_order')
 if d['stop_mode']=='close' and (d['stop']-d['emergency_stop'])*s<=0:raise ValueError('emergency_order')
 boundary=d['emergency_stop'] if d['stop_mode']=='close' else d['stop']
 if p.get('margin_mode')=='isolated' and (boundary-liquidation_price(p))*s<=0:raise ValueError('management_beyond_liquidation')
 if d['action']=='add':
  if not complete or p.get('tp1_done') or d['add_margin_pct']<=0:raise ValueError('management_add_not_ready')
  if not d['entry_low']<=price<=d['entry_high']:raise ValueError('management_add_band')
  if (d['tp1']-price)*s/((price-boundary)*s)<1.5:raise ValueError('management_add_rr')
 if d['action']=='reduce' and not 0<d['reduce_pct']<100:raise ValueError('management_reduce_pct')

def finish(job,snap,runner):
 ps=positions(job['symbol'])
 if not ps:return 'canceled'
 p=ps[0]
 reviewed=snap.get('open_positions',[])
 if not reviewed or fingerprint(reviewed[0])!=fingerprint(p):return 'canceled'
 if snap['team_review']['status']!='complete':return 'canceled'
 snap['open_positions']=ps
 from .worker import compact_input
 with store.db() as c:cid=c.execute('INSERT INTO calls(started,kind,job_id) VALUES (?,?,?)',(time.time(),job['kind'],job['id'])).lastrowid
 d,usage,latency=runner(PROMPT+'\n'+json.dumps(compact_input(snap),ensure_ascii=False),None,job['id'],[],[],custom_schema=schema())
 complete=snap['team_review']['status']=='complete'
 mark=store.get('price:'+job['symbol'],{})
 if time.time()-mark.get('time',0)>30:raise ValueError('management_stale_price')
 validate(d,p,mark['price'],complete)
 now=time.time()
 record=dict(job_id=job['id'],created=now,expires=now+300,expected=fingerprint(p),decision=d,team_complete=complete)
 with store.db() as c:
  c.execute('BEGIN IMMEDIATE')
  row=c.execute('SELECT state FROM paper_plans WHERE id=?',(p['id'],)).fetchone();current=json.loads(row[0]) if row else {}
  if current.get('status')!='open' or fingerprint(current)!=fingerprint(p):return 'canceled'
  current['pending_management']=record
  c.execute('UPDATE paper_plans SET state=? WHERE id=?',(json.dumps(current,ensure_ascii=False),p['id']))
  c.execute('UPDATE calls SET ok=1,usage=? WHERE id=?',(json.dumps(usage),cid))
  c.execute('INSERT OR REPLACE INTO kv VALUES (?,?)',('management_review:'+str(job['id']),json.dumps(record,ensure_ascii=False)))
 return 'done'

def apply(c,p,b):
 """Apply a fresh review only at an observed future minute open."""
 r=p.get('pending_management')
 if not r or b['t']/1000<r['created']:return
 p.pop('pending_management',None)
 if b['t']/1000>r['expires'] or fingerprint(p)!=r['expected']:return
 from . import paper
 d=r['decision'];price=b['o']
 try:validate(d,p,price,r['team_complete'])
 except (ValueError,jsonschema.ValidationError):return
 action=d['action'];now=b['t']/1000
 if action=='add':
  used=sum(paper.reserve(x)[0] for x in paper.read_states(c))
  margin=min(paper.account(c)*d['add_margin_pct']/100,max(0,paper.account(c)-used))
  qty=margin*p.get('leverage',1)/price
  if qty<=0:return
  new=dict(p,average=(p['average']*p['qty']+price*qty)/(p['qty']+qty),qty=p['qty']+qty)
  try:validate(d,new,price,r['team_complete'])
  except (ValueError,jsonschema.ValidationError):return
  p.update(average=new['average'],qty=new['qty'],added=True,add_amount=0,add_armed=None)
  original=p.get('reason');p['reason']=d['reason']
  paper.event(c,p,now,'add',price,qty,detail='team_review_add')
  p['reason']=original
 if action in ('exit','reduce'):
  # exit_qty records at bar close by default; this action executes at its open.
  fill=dict(b,close_t=b['t'])
  paper.exit_qty(c,p,fill,p['qty']*(1 if action=='exit' else d['reduce_pct']/100),price,'review_exit' if action=='exit' else 'review_reduce',d['reason'])
 if p['status']=='open':
  p.update(stop=d['stop'],tp1=d['tp1'],tp2=d['tp2'],stop_mode=d['stop_mode'],stop_tf=d['stop_tf'],emergency_stop=d['emergency_stop'],management_since=now,hold_hours=(now-p['entry_time'])/3600+d['review_hours'],add_amount=0,add_armed=None)
 p['management_revision']=p.get('management_revision',0)+1
 paper.event(c,p,now,'management',price,detail=json.dumps(d,ensure_ascii=False))
 row=c.execute("SELECT value FROM kv WHERE key='paper_topic_id'").fetchone()
 if row:
  title={'hold':'유지','reduce':'일부 청산','exit':'전량 청산','add':'추가 진입'}[action]
  protection=(f"구조 기준 {d['stop']:,.2f} · {d['stop_tf']} 종가 확인\n비상 청산선 {d['emergency_stop']:,.2f}" if d['stop_mode']=='close' else f"구조 손절 {d['stop']:,.2f}") if action!='exit' else ''
  text=pack([f"🧭 <b>가상 포지션 대응 · {escape(p['symbol'])} {title}</b>",f"판단 적용 가격 {price:,.2f} USDT",escape(d['reason']),protection])
  c.execute('INSERT INTO outbox(created,text,topic_id) VALUES (?,?,?)',(time.time(),text,json.loads(row[0])))

def close_stop(c,p,b):
 """Emergency wick protection, otherwise only completed thesis-timeframe close."""
 if p.get('stop_mode')!='close':return None
 s=p['sign'];emergency=p['emergency_stop']
 if (b['l']<=emergency if s==1 else b['h']>=emergency):return min(emergency,b['o']) if s==1 else max(emergency,b['o'])
 row=c.execute('SELECT c FROM candles WHERE symbol=? AND tf=? AND closed=1 AND close_t>? AND close_t<=? ORDER BY close_t DESC LIMIT 1',(p['symbol'],p['stop_tf'],p['management_since']*1000,b['close_t'])).fetchone()
 if row and (row[0]-p['stop'])*s<=0:return b['c']
 return None
