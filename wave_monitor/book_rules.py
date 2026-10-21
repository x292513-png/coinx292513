"""Reviewed book knowledge and narrowly scoped, point-based price checks.

This is not a complete Elliott/NEoWave parser. A passing endpoint test never
proves the internal subdivisions or future post-pattern confirmation.
"""
import json
import math
import re
from . import store

READING_TOPICS = {
    'impulse': ('impulse', '임펄스', '충격', '연장', '교대', '3파'),
    'abc': ('abc', 'zigzag', '지그재그', 'flat', '플랫', '조정'),
    'triangle': ('triangle', '삼각', '수렴', '확산'),
    'diagonal': ('diagonal', '다이아', 'terminal', '터미널', '엔딩', '리딩'),
    'wxy': ('wxy', 'complex', '복합', '숨은', '숨겨진', '집약'),
    'harmonic': ('harmonic', '하모닉', 'gartley', 'crab', 'butterfly', 'shark', 'cypher', 'bat', 'prz'),
}

def reading_context(snap):
    """Use reviewed reasoning, not raw OCR, in every analysis; bound token cost.

    The always-on protocol covers the full decision sequence. Supplemental
    sections are selected from all six reading records using current candidates
    and the question. Selection is retrieval, not proof a pattern is present.
    """
    root=store.ROOT/'knowledge/full-reading'
    protocol=(root/'analysis-protocol.md').read_text()
    query=str(snap.get('question','')).lower()+' '+ ' '.join(
        str(c.get('pattern','')).lower()
        for f in snap.get('frames',{}).values() for c in f.get('candidates',[]))
    topics=[k for k,terms in READING_TOPICS.items() if any(t in query for t in terms)]
    if not topics:topics=['impulse','abc','wxy']
    sections=[]
    for path in sorted(root.glob('0[1-6]-*.md')):
        for part in re.split(r'(?m)^## ',path.read_text())[1:]:
            heading,_,body=part.partition('\n')
            if path.name.startswith('06-') and 'harmonic' not in topics:continue
            lower=(heading+' '+body).lower()
            score=sum(sum(min(lower.count(t),3) for t in READING_TOPICS[k]) for k in topics)
            score+=sum(5 for k in topics if any(t in heading.lower() for t in READING_TOPICS[k]))
            if score:sections.append((score,path.name,heading,body.strip()))
    sections.sort(key=lambda x:(-x[0],x[1],x[2]))
    chosen=[];counts={}
    for score,name,heading,body in sections:
        if counts.get(name,0)>=2:continue
        item={'record':name,'section':heading,'text':body}
        if len(json.dumps(chosen+[item],ensure_ascii=False))>8000:continue
        chosen.append(item);counts[name]=counts.get(name,0)+1
        if len(chosen)>=6:break
    return {'protocol':protocol,'relevant_sections':chosen,'retrieval_topics':topics,
            'scope':'전체 제공 내용 정독을 판단 절차와 관련 독서 기록으로 반영. 자동 규칙 판정이나 검증 승률과는 구별.',
            'source_gap':'Balan 제공 DOCX와 대체 Google 문서 모두 후반 본문/도표 누락. 누락 부분은 근거로 사용하지 않음.'}

def load():
    return json.loads((store.ROOT/'knowledge/book-rules.json').read_text())

def impulse_price_check(points,asof_ms):
    if len(points)!=6:return {'status':'insufficient_points','failed_rules':[]}
    if any(not isinstance(p.get('price'),(int,float)) or not math.isfinite(p['price']) or p['price']<=0 for p in points):
        return {'status':'invalid_input','failed_rules':[]}
    if any(not isinstance(p.get('t'),(int,float)) or p['t']>asof_ms for p in points) or any(a['t']>=b['t'] for a,b in zip(points,points[1:])):
        return {'status':'invalid_time_order','failed_rules':[]}
    if any(p.get('confirmed') and (p.get('confirmed_at') is None or p['confirmed_at']>asof_ms) for p in points):
        return {'status':'confirmation_not_known_at_asof','failed_rules':[]}
    kinds=[p.get('kind') for p in points]
    if kinds not in [['L','H','L','H','L','H'],['H','L','H','L','H','L']]:
        return {'status':'invalid_pivot_order','failed_rules':[]}
    direction=1 if kinds[0]=='L' else -1
    q=[p['price']*direction for p in points]
    lengths=[abs(b-a) for a,b in zip(q,q[1:])]
    if any(v<=0 for v in lengths):return {'status':'zero_length_segment','failed_rules':[]}
    failed=[]
    if q[2]<=q[0]:failed.append('EW01')
    if q[4]<=q[1]:failed.append('EW03')
    if q[3]<=q[1]:failed.append('NE01')
    # A developing fifth wave may grow; do not certify or reject its final length.
    completed=all(p.get('confirmed') for p in points)
    if completed and lengths[2]<min(lengths[0],lengths[4]):failed.append('EW02')
    if any((q[i+1]-q[i])*(1 if i%2==0 else -1)<=0 for i in range(5)):
        return {'status':'invalid_segment_direction','failed_rules':[]}
    motive=sorted([lengths[0],lengths[2],lengths[4]],reverse=True)
    return {'status':'ordinary_impulse_price_rejected' if failed else ('price_checks_passed_internal_structure_unverified' if completed else 'developing_not_confirmed'),
            'failed_rules':failed,'completed_pivots':completed,
            'ratios':{'wave2_retrace':round(lengths[1]/lengths[0],4),'wave4_retrace':round(lengths[3]/lengths[2],4),'largest_to_second_motive':round(motive[0]/motive[1],4)},
            'not_tested':['internal_5_3_5_3_5','same_degree','intrasegment_extremes','full_neely_monowaves','neely_extension_exceptions','post_pattern_confirmation'],
            'scope':'이 여섯 끝점을 0~5로 가정한 일반 임펄스 가격 검사. 전체 시장/다이아고날 판정 아님.'}

def context(snap):
    library=load()
    tags={'core'}
    question=str(snap.get('question','')).lower()
    if any(x in question for x in ['하모닉','harmonic','gartley','bat']):tags.add('harmonic')
    checks={}
    for tf in ['1d','4h','1h','15m']:
        f=snap.get('frames',{}).get(tf,{})
        for c in f.get('candidates',[]):
            name=c.get('pattern','').lower()
            for tag in ['impulse','abc','triangle','diagonal','wxy']:
                if tag in name:tags.add(tag)
        pts=f.get('major_pivots',[])
        if len(pts)>=6:
            chosen=pts[-6:]
            checks[tf]={'hypothesis':'최근 여섯 주요 피벗을 0~5로 가정',
                        'anchors':[{'t':p['t'],'price':p['price'],'kind':p['kind']} for p in chosen],
                        **impulse_price_check(chosen,snap['asof']*1000)}
    # Always include ordinary/corrective distinctions and Neely confirmation.
    tags.update(['abc','wxy'])
    mandatory=[r for r in library['rules'] if 'core' in r['tags']]
    extra=[r for r in library['rules'] if r not in mandatory and tags.intersection(r['tags'])]
    extra.sort(key=lambda r:0 if 'harmonic' in tags and 'harmonic' in r['tags'] else 1)
    selected=mandatory+extra
    cards=[]
    for r in selected:
        source=library['sources'][r['source']]
        card={k:r[k] for k in ['id','framework','kind','text']}
        card['source']=source['title']+' · '+r['locator']
        if r.get('cross_reference'):card['cross_reference']=r['cross_reference']
        if len(json.dumps(cards+[card],ensure_ascii=False))>11000:break
        cards.append(card)
    return {'version':library['version'],'status':'full_reading_reasoning_with_partial_numeric_checks',
            'rules':cards,'point_checks':checks,
            'reading':reading_context(snap),
            'limits':'제공된 본문/도표는 정독했으나 Balan 원본 누락은 남아 있다. 미확인 OCR 숫자를 강제 규칙으로 사용하지 않는다. 전체 NEoWave 자동 검증/승률 개선을 완료했다고 표현하지 않는다. 가중치는 주관적이며 책의 빈도를 실측 승률로 쓰지 않는다.'}

def citations(rule_ids):
    library=load();rules={r['id']:r for r in library['rules']}
    if len(rule_ids)>4 or len(set(rule_ids))!=len(rule_ids) or any(i not in rules for i in rule_ids):raise ValueError('ungrounded_book_rule')
    return [library['sources'][rules[i]['source']]['title']+' · '+rules[i]['locator']+' ['+i+']' for i in rule_ids]
