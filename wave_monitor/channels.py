"""Anchored linear-price geometry; candidates, not proven Elliott counts."""

def line(a,b,t):
    return a['price']+(b['price']-a['price'])*(t-a['t'])/(b['t']-a['t'])

def channel_candidates(tf,points,rows,degree='swing'):
    if not rows:return []
    bar=rows[-1];now=bar['close_t'];out=[]
    points=sorted([p for p in points if p.get('confirmed') and p['t']<=now and (p.get('confirmed_at') or p['t'])<=now],key=lambda p:p['t'])[-12:]
    for kind in ('L','H'):
        same=[p for p in points if p['kind']==kind]
        if len(same)<2:continue
        a,b=same[-2:]
        if b['t']<=a['t']:continue
        opposite=[p for p in points if a['t']<p['t']<b['t'] and p['kind']!=kind]
        if not opposite:continue
        anchor=max(opposite,key=lambda p:abs(p['price']-line(a,b,p['t'])))
        offset=anchor['price']-line(a,b,anchor['t'])
        if kind=='L' and offset<=0 or kind=='H' and offset>=0:continue
        base=line(a,b,now);lower=min(base,base+offset);upper=max(base,base+offset)
        if lower<=0:continue
        formed=max(p.get('confirmed_at') or p['t'] for p in (a,b,anchor))
        post=[r for r in rows if r['t']>=formed]
        prior=[]
        for r in post:
            y=line(a,b,r['close_t']);lo=min(y,y+offset);hi=max(y,y+offset)
            prior.append('above' if r['c']>hi else 'below' if r['c']<lo else 'inside')
        status='above' if bar['c']>upper else 'below' if bar['c']<lower else 'inside'
        out.append({'id':f"{tf}:channel:{degree}:{a['t']}:{b['t']}:{anchor['t']}",'kind':'channel','tf':tf,'degree':degree,'scale':'linear_price','baseline':[a,b],'parallel_anchor':anchor,'offset':offset,'price':(lower+upper)/2,'lower':lower,'upper':upper,'mid':(lower+upper)/2,'asof':now,'formed_at':formed,'status':status,'close':bar['c'],'post_formation_closes':len(post),'outside_closes':sum(x!='inside' for x in prior),'lower_close_projection_overlaps_last_range':bar['l']<=lower<=bar['h'],'upper_close_projection_overlaps_last_range':bar['l']<=upper<=bar['h'],'note':'two same-side confirmed pivots plus intervening opposite pivot; linear parallel candidate, not a validated Elliott channel or independent support proof'})
    return out
