"""Closed-candle context, not standalone orders or calibrated probabilities."""
import math
import statistics


def measure(rows):
    rows=[r for r in rows if r.get('closed',True)][-120:]
    if len(rows)<21:return {'status':'insufficient_closed_candles'}
    closes=[float(r['c']) for r in rows]
    def bands(end):
        sample=closes[end-20:end];mid=statistics.mean(sample);sd=statistics.pstdev(sample)
        lower,upper=mid-2*sd,mid+2*sd
        return dict(mid=mid,lower=lower,upper=upper,bandwidth_pct=(upper-lower)/mid*100 if mid else None,percent_b=(closes[end-1]-lower)/(upper-lower) if upper>lower else None)
    current,previous=bands(len(rows)),bands(len(rows)-1)
    reentry='none'
    if closes[-2]<previous['lower'] and current['lower']<=closes[-1]<=current['upper']:reentry='from_below'
    elif closes[-2]>previous['upper'] and current['lower']<=closes[-1]<=current['upper']:reentry='from_above'
    raw=[]
    for i in range(len(rows)):
        if i<13:raw.append(None);continue
        window=rows[i-13:i+1];lo=min(r['l'] for r in window);hi=max(r['h'] for r in window)
        raw.append(100*(closes[i]-lo)/(hi-lo) if hi>lo else None)
    def sma3(values):
        return [statistics.mean(values[i-2:i+1]) if i>=2 and all(v is not None for v in values[i-2:i+1]) else None for i in range(len(values))]
    k=sma3(raw);d=sma3(k);cross='none'
    if all(v is not None for v in [k[-2],d[-2],k[-1],d[-1]]):
        if k[-2]<=d[-2] and k[-1]>d[-1]:cross='bullish'
        elif k[-2]>=d[-2] and k[-1]<d[-1]:cross='bearish'
    out={'status':'closed_candles','asof':rows[-1]['close_t'],
         'bollinger':dict(settings='SMA20 close +/- 2 population standard deviations',**current,previous=previous,reentry=reentry),
         'stochastic':dict(settings='14,3,3 SMA; price stochastic, not StochRSI',k=k[-1],d=d[-1],previous_k=k[-2],previous_d=d[-2],cross=cross)}
    def clean(value):
        if isinstance(value,float):return round(value,6) if math.isfinite(value) else None
        if isinstance(value,dict):return {key:clean(v) for key,v in value.items()}
        return value
    return clean(out)
