import os
os.environ['JWT_SECRET']='test-secret'
os.environ['SEED_DEMO']='true'
os.environ.setdefault('REDIS_URL','redis://localhost:6379/0')
os.environ.setdefault('DATABASE_URL','sqlite+pysqlite:////tmp/fxtest/api.db')
import sys,json,time,threading,importlib
sys.path.insert(0,'/workspace/backend')
if os.path.exists('/tmp/fxtest/api.db'):os.remove('/tmp/fxtest/api.db')
import fakeredis
import redis as redismod
fake=fakeredis.FakeServer()
redismod.Redis.from_url=lambda *a,**k: fakeredis.FakeRedis(server=fake)
from fastapi.testclient import TestClient
from src.main import app
from src.config.database import Session
from src.models.entities import Training,FxBook,FxRate,FxSetting,Claim,Conversion
from src.services.pipeline import process
import scripts.seed_demo
import src.routes.api as api_routes
api_routes.redis.Redis.from_url=redismod.Redis.from_url
OUT={}
def ok(cond,label,extra=''):
 print(('PASS ' if cond else 'FAIL ')+label+((' :: '+str(extra)) if extra and not cond else ''))
 if not cond:OUT.setdefault('failed',[]).append(label+str(extra))

with TestClient(app) as c:
 def login(email):
  r=c.post('/auth/login',json={'email':email,'password':'Demo123!'});return {'Authorization':'Bearer '+r.json()['token']}
 A=login('admin@demo.local');AN=login('analyst@demo.local');V=login('viewer@demo.local')
 claims=c.get('/claims',headers=A).json()
 ok(len(claims)==300+3,'seed loads 300 legacy + 3 FX claims',len(claims))
 legacy=[x for x in claims if x['code'].startswith('HX-1115-')]
 ok(all(x['currency']=='CNY' and x['claim_date'] is None for x in legacy),'legacy samples are CNY with no date')
 books=c.get('/fx/books',headers=A).json()
 ok(len(books)==1 and books[0]['active'] and books[0]['status']=='published','seeded book is active/published',books)
 # 1. viewer cannot write FX
 ok(c.post('/fx/books',headers=V,json={'name':'no'}).status_code==403,'viewer cannot create FX book')
 # 2. create draft book with a return leg (EUR/USD), a middle-currency route, and an overlap -> validation fails
 b=c.post('/fx/books',headers=AN,json={'name':'2027 测试汇率簿','note':'t'}).json();bid=b['id']
 ok(b['status']=='draft','draft created')
 def add(rate):
  return c.post(f'/fx/books/{bid}/rates',headers=AN,json=rate)
 r=add({'from_currency':'usd','to_currency':'cny','rate':7.2,'effective_from':'2027-01-01','effective_to':'2027-06-30'})
 ok(r.status_code==200 and r.json()['from_currency']=='USD','rate normalized to uppercase',r.text)
 add({'from_currency':'USD','to_currency':'CNY','rate':7.3,'effective_from':'2027-06-15','effective_to':'2027-12-31'})
 add({'from_currency':'USD','to_currency':'EUR','rate':0.93,'effective_from':'2027-01-01','effective_to':'2027-12-31'})
 add({'from_currency':'EUR','to_currency':'CNY','rate':7.8,'effective_from':'2027-01-01','effective_to':'2027-12-31'})
 val=c.post(f'/fx/books/{bid}/validate',headers=AN).json()
 kinds={e['type'] for e in val['report']['errors']}
 ok(not val['report']['ok'] and 'overlap' in kinds,'overlap区间交叠 detected',val['report'])
 # cycle: USD->EUR->CNY and CNY->USD would conflict; add USD/EUR reciprocals making product != 1
 add({'from_currency':'EUR','to_currency':'USD','rate':1.2,'effective_from':'2027-01-01','effective_to':'2027-12-31'})
 val=c.post(f'/fx/books/{bid}/validate',headers=AN).json()
 kinds={e['type'] for e in val['report']['errors']}
 ok('cycle' in kinds,'cycle汇率冲突 detected',val['report']['errors'])
 pub=c.post(f'/fx/books/{bid}/publish',headers=AN)
 ok(pub.status_code==422 and '校验未通过' in pub.json()['detail'],'publish blocked until validation passes',pub.text)
 # fix: remove overlapping + conflicting rows, keep consistent triangular rates
 for rate in c.get(f'/fx/books/{bid}',headers=A).json()['rates']:
  c.delete(f"/fx/books/{bid}/rates/{rate['id']}",headers=AN)
 add({'from_currency':'USD','to_currency':'CNY','rate':7.2,'effective_from':'2027-01-01','effective_to':None})
 add({'from_currency':'USD','to_currency':'EUR','rate':0.9,'effective_from':'2027-01-01','effective_to':None})
 add({'from_currency':'EUR','to_currency':'CNY','rate':8.0,'effective_from':'2027-01-01','effective_to':None})
 # cover the seeded 2026 foreign tickets as well (thin, no cross edges)
 add({'from_currency':'USD','to_currency':'CNY','rate':7.0,'effective_from':'2026-01-01','effective_to':'2026-12-31'})
 add({'from_currency':'EUR','to_currency':'CNY','rate':7.6,'effective_from':'2026-01-01','effective_to':'2026-12-31'})
 add({'from_currency':'JPY','to_currency':'CNY','rate':0.05,'effective_from':'2026-01-01','effective_to':'2026-12-31'})
 val=c.post(f'/fx/books/{bid}/validate',headers=AN).json()
 ok(val['report']['ok'],'consistent book validates',val['report'])
 # published books immutable
 c.post(f'/fx/books/{bid}/publish',headers=AN)
 ok(c.get(f'/fx/books/{bid}',headers=A).json()['status']=='published','book published')
 ok(add({'from_currency':'GBP','to_currency':'CNY','rate':9,'effective_from':'2027-01-01'}).status_code==409,'published book rejects rate edits')
 ok(c.put(f'/fx/books/{bid}',headers=AN,json={'name':'改名'}).status_code==409,'published book rejects edits')
 ok(c.post(f'/fx/books/{bid}/validate',headers=AN).status_code==409,'published book cannot be revalidated as draft')

 # 2b. draft rate edit/delete and draft book delete
 b_del=c.post('/fx/books',headers=AN,json={'name':'可删草稿','note':''}).json()
 rr=c.post(f"/fx/books/{b_del['id']}/rates",headers=AN,json={'from_currency':'USD','to_currency':'CNY','rate':7,'effective_from':'2027-01-01'}).json()
 ed=c.put(f"/fx/books/{b_del['id']}/rates/{rr['id']}",headers=AN,json={'from_currency':'USD','to_currency':'CNY','rate':7.4,'effective_from':'2027-01-01','effective_to':'2027-12-31'})
 ok(ed.status_code==200 and ed.json()['rate']==7.4 and ed.json()['effective_to']=='2027-12-31','draft rate editable')
 detail=c.get(f"/fx/books/{b_del['id']}",headers=A).json()
 ok(detail['validation'] is None,'editing a rate clears prior validation')
 ok(c.delete(f"/fx/books/{b_del['id']}/rates/{rr['id']}",headers=AN).status_code==200,'draft rate deletable')
 ok(c.delete(f"/fx/books/{b_del['id']}",headers=AN).status_code==200,'unreferenced draft deletable')
 ok(c.delete(f"/fx/books/{bid}",headers=AN).status_code==409,'published book not deletable')

 # 3. claims API validates currency/date
 bad=c.post('/claims',headers=AN,json={'code':'X-1','amount':10,'distance':1,'currency':'USD'})
 ok(bad.status_code==422,'foreign claim requires claim_date',bad.text)
 bad=c.post('/claims',headers=AN,json={'code':'X-2','amount':10,'distance':1,'currency':'US'})
 ok(bad.status_code==422,'currency must be 3 letters')
 claim=c.post('/claims',headers=AN,json={'code':'HX-FX-101','amount':100,'distance':10,'currency':'USD','claim_date':'2027-03-01','label':1}).json()
 ok(claim['currency']=='USD','claim stores currency')
 # 4. training freezes FX and converts via chain
 t=c.post('/trainings',headers=AN,json={'name':'FX 基线','threshold':0.5}).json()
 ok(t['fx_book_id']==bid,'training freezes active book id',t['fx_book_id'])
 ok(len(t['fx_rates'])==6,'training freezes complete rate rows',len(t['fx_rates']))
 with Session() as s:
  row=s.get(Training,t['id']);process(s,row);s.commit()
 d=c.get(f"/trainings/{t['id']}",headers=A).json()
 ok(d['state']=='done','training done',d.get('error'))
 conv=c.get(f"/trainings/{t['id']}/conversions",headers=A).json()
 by={x['code']:x for x in conv}
 ok(len(conv)==304,'conversion row per claim',len(conv))
 ok(by['HX-FX-101']['cny_amount']==720.0,'USD converted by date rate',by['HX-FX-101'])
 ok(by['HX-FX-101']['original_amount']==100 and by['HX-FX-101']['chain']['path']==['USD','CNY'],'original amount + chain stored',by['HX-FX-101'])
 ok(by['HX-1115-001']['rate']==1.0 and by['HX-1115-001']['chain']['path']==['CNY'],'legacy CNY rate 1')
 ok(all(x['status']=='ok' for x in conv),'all conversions ok')
 exp=c.get(f"/trainings/{t['id']}/export",headers=A).json()
 ok(len(exp['conversions'])==304,'export includes conversions')
 # 5. late back-dated rate does not change accepted training
 b2=c.post('/fx/books',headers=AN,json={'name':'补发历史','note':''}).json()
 c.post(f"/fx/books/{b2['id']}/rates",headers=AN,json={'from_currency':'USD','to_currency':'CNY','rate':9.9,'effective_from':'2026-01-01'})
 c.post(f"/fx/books/{b2['id']}/publish",headers=AN)
 d2=c.get(f"/trainings/{t['id']}",headers=A).json()
 ok(d2['result']['holdout']==d['result']['holdout'],'later published book does not alter accepted scores')
 conv2={x['code']:x for x in c.get(f"/trainings/{t['id']}/conversions",headers=A).json()}
 ok(conv2['HX-FX-101']['cny_amount']==720.0,'later back-dated rate does not alter conversion')
 # new training uses the new book
 t2=c.post('/trainings',headers=AN,json={'name':'新簿基线','threshold':0.5}).json()
 ok(t2['fx_book_id']==b2['id'],'new training takes newly published book')
 # 6. missing route -> failure naming ticket and basis
 c.post('/claims',headers=AN,json={'code':'HX-FX-GBP','amount':50,'distance':5,'currency':'GBP','claim_date':'2027-05-01','label':0})
 t3=c.post('/trainings',headers=AN,json={'name':'缺汇率','threshold':0.5}).json()
 with Session() as s:
  row=s.get(Training,t3['id']);process(s,row);s.commit()
 d3=c.get(f"/trainings/{t3['id']}",headers=A).json()
 ok(d3['state']=='failed' and 'HX-FX-GBP' in d3['error'] and 'GBP→CNY' in d3['error'],'missing rate fails naming ticket+basis',d3.get('error'))
 conv3={x['code']:x for x in c.get(f"/trainings/{t3['id']}/conversions",headers=A).json()}
 ok(conv3['HX-FX-GBP']['status']=='error' and len(conv3)>300,'failed conversion still recorded per ticket')
 # 7. retry reuses acceptance basis, not the new published book
 rt=c.post(f"/trainings/{t3['id']}/retry",headers=AN).json()
 ok(rt['fx_book_id']==b2['id'],'retry keeps acceptance-time book')
 with Session() as s:
  row=s.get(Training,t3['id']);process(s,row);s.commit()
 ok(c.get(f"/trainings/{t3['id']}",headers=A).json()['state']=='failed','retry without fixing rate still fails')
 # 8. contradictory multi-path amounts -> failure with evidence
 c.post('/claims',headers=AN,json={'code':'HX-FX-EUR','amount':100,'distance':10,'currency':'EUR','claim_date':'2027-03-01','label':1})
 b3=c.post('/fx/books',headers=AN,json={'name':'矛盾簿','note':''}).json()
 # USD->CNY 7.2, USD->EUR 0.9, EUR->CNY 8.0 => 7.2 vs 7.2 consistent; then break USD->CNY to 7.5
 c.post(f"/fx/books/{b3['id']}/rates",headers=AN,json={'from_currency':'USD','to_currency':'CNY','rate':7.5,'effective_from':'2027-01-01'})
 c.post(f"/fx/books/{b3['id']}/rates",headers=AN,json={'from_currency':'USD','to_currency':'EUR','rate':0.9,'effective_from':'2027-01-01'})
 c.post(f"/fx/books/{b3['id']}/rates",headers=AN,json={'from_currency':'EUR','to_currency':'CNY','rate':8.0,'effective_from':'2027-01-01'})
 pub3=c.post(f"/fx/books/{b3['id']}/publish",headers=AN)
 ok(pub3.status_code==200,'book with consistent cycles but contradictory claim routes publishes')
 t4=c.post('/trainings',headers=AN,json={'name':'多路径矛盾','threshold':0.5}).json()
 with Session() as s:
  row=s.get(Training,t4['id']);process(s,row);s.commit()
 d4=c.get(f"/trainings/{t4['id']}",headers=A).json()
 ok(d4['state']=='failed' and 'USD→CNY' in d4['error'] and 'USD→EUR→CNY' in d4['error'],'multi-path contradiction fails with both routes',d4.get('error'))
 conv4={x['code']:x for x in c.get(f"/trainings/{t4['id']}/conversions",headers=A).json()}
 ok(conv4['HX-FX-101']['status']=='error' and conv4['HX-FX-101']['path_count']==2,'conflicting claim keeps both path count + error')
 # 9. publish race: acceptance sees complete old or complete new book
 b4=c.post('/fx/books',headers=AN,json={'name':'并发新簿','note':''}).json()
 c.post(f"/fx/books/{b4['id']}/rates",headers=AN,json={'from_currency':'USD','to_currency':'CNY','rate':6.5,'effective_from':'2027-01-01'})
 c.post(f"/fx/books/{b4['id']}/rates",headers=AN,json={'from_currency':'EUR','to_currency':'CNY','rate':7.0,'effective_from':'2027-01-01'})
 c.post(f"/fx/books/{b4['id']}/validate",headers=AN)
 results=[]
 def publish():results.append(('publish',c.post(f"/fx/books/{b4['id']}/publish",headers=AN).status_code))
 def train():results.append(('train',c.post('/trainings',headers=AN,json={'name':'并发训练','threshold':0.5}).json()))
 th=[threading.Thread(target=publish),threading.Thread(target=train)]
 [x.start() for x in th];[x.join() for x in th]
 tid=[v for k,v in results if k=='train'][0]['id']
 tt=c.get(f'/trainings/{tid}',headers=A).json()
 active_id=[x['id'] for x in c.get('/fx/books',headers=A).json() if x['active']][0]
 old_rates={r['from_currency']:r['rate'] for r in c.get(f"/fx/books/{b3['id']}",headers=A).json()['rates']}
 new_rates={r['from_currency']:r['rate'] for r in c.get(f"/fx/books/{b4['id']}",headers=A).json()['rates']}
 snap={r['from_currency']:r['rate'] for r in tt['fx_rates']}
 ok(snap in (old_rates,new_rates) and set(snap)==set(old_rates|new_rates),'race snapshot is exactly one complete book, never a mix',tt['fx_rates'])
 ok(tt['fx_book_id'] in (b3['id'],b4['id']),'race snapshot points at a real book',tt['fx_book_id'])
 ok(tt['fx_book_id']==b4['id'] or active_id==b4['id'],'race: accept either took new book or completed before publish',(tt['fx_book_id'],active_id))
 # only one published book at a time
 pub_books=[x for x in c.get('/fx/books',headers=A).json() if x['status']=='published']
 ok(len(pub_books)==1,'exactly one published book',len(pub_books))
 # 10. failed requires retry endpoint; retries reuse frozen basis
 ok(c.post('/trainings/'+str(t['id'])+'/retry',headers=AN).status_code==409,'retry only for failed')
 # 11. worker artifact: process via pipeline and confirm the run wrote no half-state
with Session() as s:
 row=s.get(Training,t['id'])
 ok(row.state=='done' and row.result['fx']['conversions_saved'] is True,'result records conversions persisted')
 ok(row.result['fx']['book_id']==bid,'result records the frozen book')
 # 12. viewers can read conversions and export but not mutate
 ok(c.get(f"/trainings/{t['id']}/conversions",headers=V).status_code==200,'viewer reads conversions')
 ok(c.post(f"/fx/books/{bid}/publish",headers=V).status_code==403,'viewer cannot publish')
 # 13. unauthenticated access rejected
 ok(c.get('/fx/books').status_code==401,'FX endpoints require auth')
print(json.dumps({'failed':OUT.get('failed',[])},ensure_ascii=False))
