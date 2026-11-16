import random,math
from src.config.database import Base,engine,Session
from src.models.entities import User,Claim,FxBook,FxRate,FxSetting

# Deterministic demo FX book: CNY base, date-scoped rates with a EUR<->USD leg
# so a USD claim can be converted via EUR. Rates are illustrative, not market.
DEMO_RATES=[
 ('USD','CNY',7.10,'2026-01-01','2026-06-30'),
 ('USD','CNY',7.25,'2026-07-01','2026-12-31'),
 ('EUR','CNY',7.75,'2026-01-01','2026-06-30'),
 ('EUR','CNY',7.90,'2026-07-01','2026-12-31'),
 ('JPY','CNY',0.0475,'2026-01-01','2026-12-31'),
]
def seed():
 from src.utils.security import hash_password
 Base.metadata.create_all(engine);rng=random.Random(3106)
 with Session() as s:
  for role in ('admin','analyst','viewer'):
   email=role+'@demo.local'
   if not s.query(User).filter_by(email=email).first():s.add(User(email=email,role=role,password=hash_password('Demo123!')))
  # Legacy samples carry no currency/date and are treated as CNY.
  for i in range(300):
   code=f'HX-1115-{i+1:03}';distance=round(rng.uniform(5,800),1);holiday=rng.random()<.25;amount=round(distance*rng.uniform(1.2,5.5)+rng.uniform(50,900),2)
   risk=-4.7+amount/700+1.1*holiday+amount/(distance+1)/8;label=int(rng.random()<1/(1+math.exp(-risk))) if i<260 else None
   if not s.query(Claim).filter_by(code=code).first():s.add(Claim(code=code,amount=amount,distance=distance,holiday=holiday,label=label,currency='CNY',claim_date=None,note='历史人工复核标签；仅用于模拟训练，不连接真实报销'))
  for code,amount,cur,day in [('HX-FX-001',820.00,'USD','2026-03-14'),('HX-FX-002',510.00,'EUR','2026-08-02'),('HX-FX-003',43000.00,'JPY','2026-09-09')]:
   if not s.query(Claim).filter_by(code=code).first():s.add(Claim(code=code,amount=amount,distance=round(amount/8,1),holiday=False,label=None,currency=cur,claim_date=day,note='外币票据演示；按票据日期折算人民币'))
  s.flush()
  if not s.query(FxBook).count():
   book=FxBook(name='2026 年度演示汇率簿',status='published',created='2026-01-01T00:00:00+00:00',published_at='2026-01-01T00:00:00+00:00',note='演示用参考汇率，非真实牌价')
   s.add(book);s.flush()
   for a,b,rate,start,end in DEMO_RATES:s.add(FxRate(book_id=book.id,from_currency=a,to_currency=b,rate=rate,effective_from=start,effective_to=end,created='2026-01-01T00:00:00+00:00'))
   st=s.get(FxSetting,1) or FxSetting(id=1)
   st.active_book_id=book.id;s.add(st)
  s.commit();print({'users':s.query(User).count(),'claims':s.query(Claim).count(),'fx_books':s.query(FxBook).count()})
if __name__=='__main__':seed()
