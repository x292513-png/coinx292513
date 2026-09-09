"""Per-process DNS for Binance; does not alter VPS networking or disable TLS."""
import asyncio
import ipaddress
import json
import socket
import time
import urllib.request
from aiohttp import TCPConnector
from aiohttp.abc import AbstractResolver
from aiohttp.resolver import DefaultResolver


class MarketResolver(AbstractResolver):
    def __init__(self):
        self.default=DefaultResolver();self.cache={}

    async def resolve(self,host,port=0,family=socket.AF_INET):
        if host not in {'fapi.binance.com','fstream.binance.com'}:
            return await self.default.resolve(host,port,family)
        cached=self.cache.get(host)
        if not cached or cached[0]<time.time():
            def lookup():
                request=urllib.request.Request('https://cloudflare-dns.com/dns-query?name='+host+'&type=A',headers={'accept':'application/dns-json'})
                with urllib.request.urlopen(request,timeout=8) as r:body=json.load(r)
                answers=[a for a in body.get('Answer',[]) if a['type']==1 and ipaddress.ip_address(a['data']).is_global]
                if not answers:raise OSError('market_dns_empty')
                return (time.time()+min(300,min(a.get('TTL',60) for a in answers)),[a['data'] for a in answers])
            self.cache[host]=cached=await asyncio.to_thread(lookup)
        return [{'hostname':host,'host':ip,'port':port,'family':socket.AF_INET,'proto':socket.IPPROTO_TCP,'flags':socket.AI_NUMERICHOST} for ip in cached[1]]

    async def close(self):await self.default.close()


def connector():
    return TCPConnector(resolver=MarketResolver(),family=socket.AF_INET,ttl_dns_cache=60)
