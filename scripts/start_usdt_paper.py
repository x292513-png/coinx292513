"""One-time, idempotent account migration. Stop execution services before running."""
import time
from wave_monitor import store,paper
store.init()
print('new_account_created',paper.start_usdt_account(time.time()))
with store.db() as c:print('account',paper.account_spec(c),'balance',paper.account(c))
