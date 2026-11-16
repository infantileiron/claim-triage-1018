import os,time,json,logging
from pathlib import Path
import redis
from src.config.database import Session
from src.models.entities import Training
from src.services.pipeline import process
r=redis.Redis.from_url(os.environ['REDIS_URL'])
with Session() as recovery:
 for pending in recovery.query(Training).filter(Training.state.in_(['queued','running'])).all():
  pending.state='queued';r.rpush('claim:trainings',pending.id)
 recovery.commit()
while True:
 Path('/tmp/heartbeat').touch()
 try:
  item=r.blpop('claim:trainings',timeout=3)
  if not item:continue
  with Session() as s:
   row=s.get(Training,int(item[1]))
   if not row or row.state!='queued':continue
   row.state='running';s.commit()
   try:
    process(s,row)
    if row.state=='done':Path('/artifacts/'+str(row.id)+'.json').write_text(json.dumps(row.result,ensure_ascii=False))
   except Exception as e:
    row.state='failed';row.error=str(e)
    row.result={**(row.result or {}),'fx':{'book_id':row.fx_book_id}}
   s.commit()
 except Exception:logging.exception('worker');time.sleep(2)
