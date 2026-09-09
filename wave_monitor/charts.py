import os
os.environ.setdefault('MPLBACKEND','Agg')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib import font_manager
import numpy as np
from datetime import datetime,timezone,timedelta
from .analysis import indicators


def render(snap, raw, path, result=None):
    fonts=[x.name for x in font_manager.fontManager.ttflist]
    for name in ['Noto Sans CJK KR','Noto Sans CJK JP','NanumGothic']:
        if name in fonts:
            plt.rcParams['font.family']=name;break
    plt.rcParams['axes.unicode_minus']=False
    plt.rcParams.update({'font.size':9,'axes.facecolor':'#101926','figure.facecolor':'#09111c','text.color':'#d9e5ef','axes.labelcolor':'#c4d2dd','xtick.color':'#94a6b8','ytick.color':'#94a6b8','axes.edgecolor':'#2c3d50','grid.color':'#243447'})
    fig=plt.figure(figsize=(18,15),layout='constrained')
    grid=fig.add_gridspec(3,2)
    kst=timezone(timedelta(hours=9))
    asof=datetime.fromtimestamp(snap['asof'],kst).strftime('%Y-%m-%d %H:%M:%S KST')
    headline=(result or {}).get('headline','Top-down structure / measured pivots')
    fig.suptitle(f"{snap['symbol']} PERPETUAL · {asof}\n{headline}",fontsize=16,fontweight='bold')
    for z,tf in enumerate(['1w','1d','4h','15m','5m','1m']):
        sub=grid[z//2,z%2].subgridspec(4,1,hspace=.02)
        ax=fig.add_subplot(sub[:3,0]);rx=fig.add_subplot(sub[3,0],sharex=ax)
        rows=raw[tf][-160:];xmap={c['t']:i for i,c in enumerate(rows)}
        low=min(c['l'] for c in rows);high=max(c['h'] for c in rows)
        for i,c in enumerate(rows):
            color='#41d6b0' if c['c']>=c['o'] else '#ff7c83'
            ax.vlines(i,c['l'],c['h'],color=color,linewidth=.7)
            ax.add_patch(Rectangle((i-.32,min(c['o'],c['c'])),.64,max(abs(c['c']-c['o']),(high-low)*.0007),facecolor=color,edgecolor=color,linewidth=.4))
        points=[p for p in snap['frames'][tf]['pivots'] if p['t'] in xmap]
        ax.plot([xmap[p['t']] for p in points],[p['price'] for p in points],color='#edbf67',lw=.9,alpha=.8)
        for p in points:
            ax.plot(xmap[p['t']],p['price'],marker='o' if p['confirmed'] else 'x',ms=3,color='#edbf67')
        labels=[p for p in (result or {}).get('wave_labels',[]) if p['tf']==tf and p['t'] in xmap]
        for p in labels:
            ax.annotate(p['label'],(xmap[p['t']],p['price']),xytext=(0,8),textcoords='offset points',ha='center',color='#fff6ca',fontsize=10,fontweight='bold')
        profile=snap['profiles'][1 if tf in ['1w','1d','4h'] else 0]
        edges=profile['edges'];v=profile['volume'];mx=max(v) or 1
        for i,value in enumerate(v):
            if low<=edges[i]<=high:
                ax.barh((edges[i]+edges[i+1])/2,value/mx*22,left=len(rows)+1,height=edges[i+1]-edges[i],color='#729be2',alpha=.4)
        for label in ['poc','vah','val']:
            level=profile[label]
            if low<=level<=high:
                ax.axhline(level,color='#8fb0e8',ls='--',lw=.7,alpha=.6)
        ax.text(.985,.97,'VP approx\n'+ '\n'.join(f"{k.upper()} {profile[k]:,.2f}" for k in ['poc','vah','val']),transform=ax.transAxes,ha='right',va='top',fontsize=7,color='#acc9f8',bbox={'facecolor':'#101926','alpha':.85,'edgecolor':'none','pad':3})
        for zone in (result or {}).get('zones',[]):
            if zone['high']>=low and zone['low']<=high:
                ax.axhspan(zone['low'],zone['high'],color='#62d8c1',alpha=.12)
        ict=snap['frames'][tf].get('ict',{}).get('active',[])
        selected=(result or {}).get('ict_watch_ids',[])
        visible=[z for z in ict if z['low']<=high and z['high']>=low]
        visible.sort(key=lambda z:(z['id'] not in selected,abs(z['mid']-rows[-1]['c'])))
        for index,z in enumerate(visible[:3]):
            origin=next((i for i,c in enumerate(rows) if c['close_t']>=z['formed_at']),0)
            color='#8aa8ff' if z['direction']=='bullish' else '#e49e66'
            ax.add_patch(Rectangle((origin,z['low']),len(rows)+1-origin,z['high']-z['low'],facecolor=color,edgecolor=color,alpha=.13,lw=.7))
            ax.hlines(z['mid'],origin,len(rows),color=color,ls=':',lw=.8)
            midlabel='CE' if z['kind']=='FVG' else 'MT'
            ax.text(.01,.97-index*.055,f"{z['kind']} {midlabel} {z['mid']:,.2f}",transform=ax.transAxes,color=color,fontsize=7,va='top',bbox={'facecolor':'#101926','alpha':.75,'edgecolor':'none','pad':1})
        inval=(result or {}).get('invalidation_price')
        if inval and low<=inval<=high: ax.axhline(inval,color='#f28b92',lw=1,ls=':')
        vals,_=indicators(raw[tf]);vals=vals[-len(rows):]
        rx.plot(range(len(rows)),vals,color='#bbabfc',lw=1)
        rx.axhline(70,color='#785b7c',ls='--',lw=.6);rx.axhline(30,color='#526e70',ls='--',lw=.6)
        rx.set_ylim(0,100);rx.set_yticks([30,70]);rx.set_ylabel('RSI14',fontsize=7)
        ticks=np.linspace(0,len(rows)-1,5,dtype=int)
        date_format='%Y/%m' if tf=='1w' else ('%y/%m/%d' if tf=='1d' else '%m/%d\n%H:%M')
        rx.set_xticks(ticks);rx.set_xticklabels([datetime.fromtimestamp(rows[i]['t']/1000,kst).strftime(date_format) for i in ticks],fontsize=7)
        ax.tick_params(labelbottom=False)
        ax.set_xlim(-1,len(rows)+32);ax.grid(alpha=.35);rx.grid(alpha=.25)
        ax.set_title(f"{tf} · closed candles · RSI {snap['frames'][tf]['rsi14']:.1f} · VP approximate",loc='left',fontsize=10)
    fig.text(.5,.002,'Binance futures | KST | Yellow: swing pivots (x: developing) | VP approximate | Blue/orange: bullish/bearish FVG/OB; dotted CE/MT | actual trades separate',ha='center',fontsize=8,color='#8da3b7')
    fig.savefig(path,dpi=115)
    plt.close(fig)
