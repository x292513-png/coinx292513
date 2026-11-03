"""Same-time closed-candle comparisons; no direction forced onto either asset."""
import numpy as np
from . import store

def context(asof):
    result={}
    for tf in ('1d','4h','1h','15m'):
        data={s:{r['t']:r for r in store.candles(s,tf,100) if r['close_t']<=asof*1000} for s in ('BTCUSDT','ETHUSDT')}
        common=sorted(set(data['BTCUSDT'])&set(data['ETHUSDT']))[-97:]
        if len(common)<4:continue
        prices=[np.array([data[s][t]['c'] for t in common]) for s in data]
        returns=[np.diff(np.log(p)) for p in prices]
        corr=float(np.corrcoef(*returns)[0,1]) if all(np.std(r)>1e-10 for r in returns) else None
        result[tf]={'bars':len(common),'last_close_t':data['BTCUSDT'][common[-1]]['close_t'],'return_correlation':round(corr,3) if corr is not None and np.isfinite(corr) else None,'last_bar_pct':{s:round(float((p[-1]/p[-2]-1)*100),3) for s,p in zip(data,prices)}}
    return result
