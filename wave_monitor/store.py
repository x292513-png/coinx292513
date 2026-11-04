import json
import os
import sqlite3
import time
from pathlib import Path

ROOT = Path(os.getenv("WAVE_ROOT", Path(__file__).resolve().parents[1]))


def settings():
    return json.loads((ROOT / "config/settings.json").read_text())


def runtime():
    return json.loads((ROOT / "config/runtime.json").read_text())


def db():
    (ROOT / "data").mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(ROOT / "data/waves.sqlite3", timeout=20)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=20000")
    c.execute("PRAGMA foreign_keys=ON")
    return c


def init():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS candles(symbol TEXT, tf TEXT, t INTEGER, o REAL,h REAL,l REAL,c REAL,v REAL,close_t INTEGER,closed INTEGER, PRIMARY KEY(symbol,tf,t));
        CREATE TABLE IF NOT EXISTS trade_bins(symbol TEXT,hour INTEGER,price REAL,volume REAL, PRIMARY KEY(symbol,hour,price));
        CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY,created REAL,symbol TEXT,reason TEXT,kind TEXT,status TEXT DEFAULT 'pending',question TEXT DEFAULT '',reply_id INTEGER,analysis_ref INTEGER,error TEXT DEFAULT '');
        CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status,created);
        CREATE TABLE IF NOT EXISTS analyses(id INTEGER PRIMARY KEY,job_id INTEGER,created REAL,symbol TEXT,snapshot TEXT,result TEXT,chart TEXT,usage TEXT,latency REAL);
        CREATE TABLE IF NOT EXISTS calls(id INTEGER PRIMARY KEY,started REAL,kind TEXT,job_id INTEGER,ok INTEGER DEFAULT 0,usage TEXT DEFAULT '{}');
        CREATE TABLE IF NOT EXISTS messages(message_id INTEGER PRIMARY KEY,analysis_id INTEGER,created REAL,kind TEXT);
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,created REAL,symbol TEXT,kind TEXT,detail TEXT);
        CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY,created REAL,analysis_id INTEGER,text TEXT,chart TEXT,reply_id INTEGER,status TEXT DEFAULT 'pending',attempts INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS evaluations(analysis_id INTEGER,hours INTEGER,created REAL,data TEXT,PRIMARY KEY(analysis_id,hours));
        CREATE TABLE IF NOT EXISTS zone_visits(id INTEGER PRIMARY KEY,created REAL,symbol TEXT,analysis_id INTEGER,low REAL,high REAL,role TEXT,price REAL,atr REAL,outcome TEXT);
        """)
        if 'topic_id' not in [r['name'] for r in c.execute('PRAGMA table_info(outbox)')]:
            c.execute('ALTER TABLE outbox ADD COLUMN topic_id INTEGER')
    from . import paper
    paper.init()
    if get('started_at') is None:
        put('started_at', time.time())


def get(key, default=None):
    with db() as c:
        r = c.execute('SELECT value FROM kv WHERE key=?', (key,)).fetchone()
    return json.loads(r[0]) if r else default


def put(key, value):
    with db() as c:
        c.execute('INSERT OR REPLACE INTO kv VALUES (?,?)', (key, json.dumps(value, ensure_ascii=False)))


def event(symbol, kind, detail):
    with db() as c:
        c.execute('INSERT INTO events(created,symbol,kind,detail) VALUES (?,?,?,?)', (time.time(), symbol, kind, json.dumps(detail, ensure_ascii=False)))


def candles(symbol, tf, limit=1000, closed=True):
    with db() as c:
        rows = c.execute('SELECT * FROM candles WHERE symbol=? AND tf=?' + (' AND closed=1' if closed else '') + ' ORDER BY t DESC LIMIT ?', (symbol, tf, limit)).fetchall()
    return [dict(r) for r in reversed(rows)]


def save_candles(symbol, tf, rows):
    with db() as c:
        c.executemany('INSERT INTO candles VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(symbol,tf,t) DO UPDATE SET o=excluded.o,h=excluded.h,l=excluded.l,c=excluded.c,v=excluded.v,close_t=excluded.close_t,closed=excluded.closed WHERE excluded.closed>=candles.closed', [(symbol,tf,*r) for r in rows])


def latest(symbol):
    with db() as c:
        r = c.execute('SELECT * FROM analyses WHERE symbol=? ORDER BY id DESC LIMIT 1',(symbol,)).fetchone()
    if not r:
        return None
    r = dict(r)
    for k in ['snapshot','result','usage']:
        r[k] = json.loads(r[k])
    return r


def queue(symbol, reason, kind='auto', question='', reply_id=None, analysis_ref=None):
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        if kind=='auto' and c.execute("SELECT 1 FROM jobs WHERE symbol=? AND kind='auto' AND status IN ('pending','running')",(symbol,)).fetchone():
            return None
        cur = c.execute('INSERT INTO jobs(created,symbol,reason,kind,question,reply_id,analysis_ref) VALUES (?,?,?,?,?,?,?)',(time.time(),symbol,reason,kind,question,reply_id,analysis_ref))
        return cur.lastrowid


def enqueue_message(text, analysis_id=None, chart=None, reply_id=None, topic_id=None):
    with db() as c:
        c.execute('INSERT INTO outbox(created,analysis_id,text,chart,reply_id,topic_id) VALUES (?,?,?,?,?,?)',(time.time(),analysis_id,text,chart,reply_id,topic_id))


def record_zone_visit(created,symbol,analysis_id,zone,price,atr):
    with db() as c:
        c.execute('INSERT INTO zone_visits(created,symbol,analysis_id,low,high,role,price,atr) VALUES (?,?,?,?,?,?,?,?)',(created,symbol,analysis_id,zone['low'],zone['high'],zone['role'],price,atr))
