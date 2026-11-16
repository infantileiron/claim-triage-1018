import os
os.environ['JWT_SECRET']='test-secret'
os.environ['SEED_DEMO']='false'
os.environ['REDIS_URL']='redis://localhost:6379/0'
os.environ['DATABASE_URL']='sqlite+pysqlite:////tmp/fxtest/race.db'
import sys,json,itertools,threading,time
sys.path.insert(0,'/workspace/backend')
for p in ('/tmp/fxtest/race.db',):
 if os.path.exists(p):os.remove(p)
import fakeredis,redis as redismod
fake=fakeredis.FakeServer()
redismod.Redis.from_url=lambda *a,**k:fakeredis.FakeRedis(server=fake)
from fastapi.testclient import TestClient
from src.main import app
from src.config.database import Session,engine
from src.models.entities import FxBook,FxRate,FxSetting,Training,Claim,User,Conversion
from src.services.pipeline import process
from src.controllers import fx as fxctl
import src.routes.api as routes
fails=[]
def ok(c,l,e=''):
 print(('PASS ' if c else 'FAIL ')+l+((' :: '+str(e)) if e and not c else ''))
 if not c:fails.append(l)
def headers(c,email='analyst@demo.local'):
 t=c.post('/auth/login',json={'email':email,'password':'Demo123!'}).json()['token']
 return {'Authorization':'Bearer '+t}

def make_book(s,name,rates,status='draft'):
 b=FxBook(name=name,status=status,created=fxctl.now());s.add(b);s.flush()
 for a,t,r,f,e in rates:
  s.add(FxRate(book_id=b.id,from_currency=a,to_currency=t,rate=r,effective_from=f,effective_to=e,created=fxctl.now()))
 s.flush();return b

with TestClient(app) as c:
 with Session() as s:
  for role in ('admin','analyst','viewer'):
   s.add(User(email=role+'@demo.local',role=role,password=__import__('src.utils.security',fromlist=['x']).hash_password('Demo123!')))
  for i in range(60):
   s.add(Claim(code=f'R-{i:03}',amount=100+i,distance=10,holiday=False,label=i%2,currency='CNY',claim_date=None))
  s.add(Claim(code='R-USD',amount=100,distance=10,holiday=False,label=1,currency='USD',claim_date='2027-03-01'))
  old=make_book(s,'旧簿',[('USD','CNY',7.0,'2027-01-01',None)],'published')
  new=make_book(s,'新簿',[('USD','CNY',9.0,'2027-01-01',None),('EUR','CNY',8.0,'2027-01-01',None)])
  st=s.get(FxSetting,1) or FxSetting(id=1)
  st.active_book_id=old.id;s.add(st);s.commit();old_id,new_id=old.id,new.id
 A=headers(c)

 # Deterministic interleaving: the train transaction holds the settings lock while
 # publish commits between its pointer read and its rate read.
 import src.routes.api as routesmod
 real_freeze=routesmod.freeze
 def freeze_then_publish(s):
  book_id,rates=real_freeze(s)
  # publish a different book in a separate connection while we still hold the lock
  with Session() as other:
   st=other.get(FxSetting,1)
   ob=other.get(FxBook,new_id);st.active_book_id=new_id
   old=other.get(FxBook,book_id);old.status='retired';ob.status='published'
   other.commit()
  return book_id,rates
 routesmod.freeze=freeze_then_publish
 if True:
  t=c.post('/trainings',headers=A,json={'name':'交错受理','threshold':0.5}).json()
  snap={r['from_currency']:r['rate'] for r in t['fx_rates']}
  ok(t['fx_book_id']==old_id,'interleaved accept keeps the book it locked',t['fx_book_id'])
  ok(snap=={'USD':7.0},'interleaved accept keeps that whole book, not the newer rates',t['fx_rates'])
 routesmod.freeze=real_freeze

 # Sequential reads after publish see the new book entirely.
 t2=c.post('/trainings',headers=A,json={'name':'新簿受理','threshold':0.5}).json()
 ok({r['from_currency']:r['rate'] for r in t2['fx_rates']}=={'USD':9.0,'EUR':8.0},'later accept sees complete new book')
 ok(t2['fx_book_id']==new_id,'later accept points at new book')

 # Worker path: conversions persisted, artifact written, and late mutations do not matter.
 for tid,frozen in ((t['id'],{'USD':7.0}),(t2['id'],{'USD':9.0,'EUR':8.0})):
  with Session() as s:
   row=s.get(Training,tid);process(s,row);s.commit()
  d=c.get(f'/trainings/{tid}',headers=A).json()
  ok(d['state']=='done',f'training {tid} done via pipeline',d.get('error'))
  conv=c.get(f'/trainings/{tid}/conversions',headers=A).json()
  usd=[x for x in conv if x['code']=='R-USD'][0]
  ok(usd['cny_amount']==round(100*frozen['USD'],2),f'training {tid} uses its frozen USD rate',usd)
  ok(len(conv)==d['result']['fx']['claim_count'],'conversion rows count matches fx metadata')
  ok(all(x['original_amount'] is not None for x in conv),'original amounts preserved for every claim')
 # publish yet another book and re-run: frozen snapshot unchanged
 with Session() as s:
  third=make_book(s,'第三簿',[('USD','CNY',5.0,'2027-01-01',None)],'published')
  st=s.get(FxSetting,1);s.get(FxBook,st.active_book_id).status='retired';st.active_book_id=third.id;s.commit()
 with Session() as s:
  row=s.get(Training,t2['id']);process(s,row);s.commit()
 usd=[x for x in c.get(f"/trainings/{t2['id']}/conversions",headers=A).json() if x['code']=='R-USD'][0]
 ok(usd['cny_amount']==900.0,'reprocessing an accepted training keeps its rate')
 # retry path uses identical frozen data -> identical scores
 with Session() as s:
  row=s.get(Training,t2['id']);row.state='queued';s.commit()
 with Session() as s:
  row=s.get(Training,t2['id']);r1=process(s,row);s.commit();sc1=[p['score'] for p in r1.result['holdout']]
 with Session() as s:
  row=s.get(Training,t2['id']);row.state='queued';s.commit()
 with Session() as s:
  row=s.get(Training,t2['id']);r2=process(s,row);s.commit();sc2=[p['score'] for p in r2.result['holdout']]
 ok(sc1==sc2,'retry produces identical scores')

 # Schema migration from a pre-FX database
 import sqlite3
 mig='/tmp/fxtest/legacy.db'
 if os.path.exists(mig):os.remove(mig)
 con=sqlite3.connect(mig)
 con.executescript('''CREATE TABLE claims(id INTEGER PRIMARY KEY, code VARCHAR(60), amount FLOAT, distance FLOAT, holiday BOOLEAN, label INTEGER, note TEXT);
 INSERT INTO claims(code,amount,distance,holiday,label,note) VALUES ('OLD-1',100,10,0,1,'');
 CREATE TABLE trainings(id INTEGER PRIMARY KEY, name VARCHAR(100), threshold FLOAT, state VARCHAR(20), result JSON, error TEXT);''')
 con.commit();con.close()
 from sqlalchemy import create_engine,text
 from src.config.schema import ensure_schema
 e2=create_engine('sqlite:///'+mig);ensure_schema(e2);ensure_schema(e2)
 with e2.connect() as cc:
  cols={r[1] for r in cc.execute(text('PRAGMA table_info(claims)'))}
  row=cc.execute(text('SELECT currency,claim_date FROM claims WHERE code=\'OLD-1\'')).one()
  tcols={r[1] for r in cc.execute(text('PRAGMA table_info(trainings)'))}
 ok('currency' in cols and 'claim_date' in cols and row[0]=='CNY' and row[1] is None,'legacy schema upgraded, old sample -> CNY')
 ok('fx_book_id' in tcols and 'fx_rates' in tcols,'legacy trainings gain FX columns')
print(json.dumps({'failed':fails},ensure_ascii=False))
