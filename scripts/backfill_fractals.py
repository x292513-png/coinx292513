"""One-time/resumable expansion, using the existing isolated market reader."""
import asyncio
import logging
from aiohttp import ClientSession,ClientTimeout
from wave_monitor.learning import download
from wave_monitor.net import connector
from wave_monitor import store

async def main():
    async with ClientSession(connector=connector(),timeout=ClientTimeout(total=35)) as s:
        for market in ['futures','spot']:
            for symbol in store.settings()['symbols']:
                for tf in ['1h','15m']:await download(s,market,symbol,tf)

if __name__=='__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
