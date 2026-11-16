import os,json
import redis
from fastapi import APIRouter,Depends,HTTPException,Response
from sqlalchemy.exc import IntegrityError
from src.config.database import db
from src.models.entities import User,Claim,Training,Review,Audit,FxBook,FxRate,FxSetting,Conversion
from src.schemas.business import Login,ClaimInput,TrainingInput,ReviewInput,FxBookInput,FxRateInput
from src.middlewares.auth import current,editor,admin
from src.utils.security import verify,token
from src.services.business import audit,dump
from src.controllers.business import ensure_training
from src.controllers.fx import now,lock_settings,draft_book,book_rates,report_or_raise,report_text,serialize_book,freeze_fx
router=APIRouter()
def enqueue(s,r):
 try:redis.Redis.from_url(os.environ['REDIS_URL']).rpush('claim:trainings',r.id)
 except redis.RedisError:
  r.state='failed';r.error='队列暂不可用，请稍后重新提交';s.commit();raise HTTPException(503,r.error)

def freeze(s):
 """Acceptance-time FX basis, frozen into the training row.

 Locks the settings pointer then reads the pointed book and all its rate rows
 with locking reads: acceptance sees either the complete old book or the
 complete new book. Published books are immutable, so what is frozen is always
 one whole book.
 """
 book,rates=freeze_fx(s)
 if book is None:return None,[]
 return book.id,rates

@router.post('/auth/login')
def login(data:Login,s=Depends(db)):
 u=s.query(User).filter_by(email=data.email).first()
 if not u or not verify(data.password,u.password):raise HTTPException(401,'账号或密码错误')
 return {'token':token(u),'user':dump(u)}
@router.get('/me')
def me(u=Depends(current)):return dump(u)
@router.get('/claims')
def claims(u=Depends(current),s=Depends(db)):return [dump(r) for r in s.query(Claim).order_by(Claim.id).all()]
@router.post('/claims')
def create_claim(data:ClaimInput,u=Depends(editor),s=Depends(db)):
 r=Claim(**data.model_dump());s.add(r)
 try:s.commit()
 except IntegrityError:s.rollback();raise HTTPException(409,'报销编号重复')
 audit(s,u,'录入报销 '+r.code);return dump(r)
@router.put('/claims/{i}')
def edit_claim(i:int,data:ClaimInput,u=Depends(editor),s=Depends(db)):
 r=s.get(Claim,i)
 if not r:raise HTTPException(404,'报销样本不存在')
 for k,v in data.model_dump().items():setattr(r,k,v)
 try:s.commit()
 except IntegrityError:s.rollback();raise HTTPException(409,'报销编号重复')
 audit(s,u,'修订报销 '+str(i));return dump(r)
@router.get('/trainings')
def trainings(u=Depends(current),s=Depends(db)):
 out=[]
 for r in s.query(Training).order_by(Training.id.desc()).all():
  item=dump(r);item.pop('fx_rates',None);out.append(item)
 return out
@router.post('/trainings')
def train(data:TrainingInput,u=Depends(editor),s=Depends(db)):
 # Freeze the FX basis before any other read: the settings lock must be the
 # transaction's first statement so the read view is created only after the
 # lock is held (MySQL REPEATABLE READ). Otherwise a publish committing in
 # between could leave the pointer on a book whose rows predate the snapshot.
 book_id,fx_rates=freeze(s)
 rows=[dump(r) for r in s.query(Claim).order_by(Claim.id).all()]
 r=Training(**data.model_dump(),result={'snapshot':rows},fx_book_id=book_id,fx_rates=fx_rates);s.add(r);s.commit()
 enqueue(s,r)
 audit(s,u,'提交训练 '+str(r.id)+('（冻结汇率簿 #'+str(book_id)+'）' if book_id else ''));return dump(r)
@router.get('/trainings/{i}')
def detail(i:int,u=Depends(current),s=Depends(db)):return dump(ensure_training(s,i))
@router.post('/trainings/{i}/retry')
def retry(i:int,u=Depends(editor),s=Depends(db)):
 r=ensure_training(s,i)
 if r.state!='failed':raise HTTPException(409,'仅失败的训练可重试')
 r.state='queued';r.error='';s.commit()
 enqueue(s,r)
 audit(s,u,'重试训练 '+str(i)+('（沿用汇率簿 #'+str(r.fx_book_id)+'）' if r.fx_book_id else ''));return dump(r)
@router.get('/trainings/{i}/conversions')
def conversions(i:int,u=Depends(current),s=Depends(db)):
 ensure_training(s,i)
 return [dump(r) for r in s.query(Conversion).filter_by(training_id=i).order_by(Conversion.claim_id).all()]
@router.get('/trainings/{i}/export')
def export(i:int,u=Depends(current),s=Depends(db)):
 r=ensure_training(s,i)
 if r.state!='done':raise HTTPException(409,'仅成功训练可导出')
 payload=dump(r)
 payload['conversions']=[dump(c) for c in s.query(Conversion).filter_by(training_id=i).order_by(Conversion.claim_id).all()]
 return Response(json.dumps(payload,ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="claim-triage-{i}.json"'})
@router.post('/trainings/{i}/reviews')
def generate(i:int,u=Depends(editor),s=Depends(db)):
 r=ensure_training(s,i)
 if r.state!='done':raise HTTPException(409,'训练完成后才能生成复核任务')
 created=0
 for p in r.result['pending']:
  if p['score']>=r.threshold and not s.query(Review).filter_by(training_id=i,claim_id=p['id']).first():s.add(Review(training_id=i,claim_id=p['id'],score=p['score']));created+=1
 s.commit();audit(s,u,'生成风险复核 '+str(i));return {'created':created}
@router.get('/reviews')
def reviews(u=Depends(current),s=Depends(db)):return [dump(r) for r in s.query(Review).order_by(Review.id.desc()).all()]
@router.put('/reviews/{i}')
def review(i:int,data:ReviewInput,u=Depends(editor),s=Depends(db)):
 r=s.get(Review,i)
 if not r:raise HTTPException(404,'复核任务不存在')
 if r.status=='approved':raise HTTPException(409,'已签核复核不可修改')
 r.decision=data.decision;r.note=data.note;s.commit();audit(s,u,'人工复核 '+str(i));return dump(r)
@router.post('/reviews/{i}/approve')
def approve(i:int,u=Depends(admin),s=Depends(db)):
 r=s.get(Review,i)
 if not r:raise HTTPException(404,'复核任务不存在')
 if r.decision=='pending' or r.status!='draft':raise HTTPException(409,'先填写人工判断，且只签核一次')
 r.status='approved';s.commit();audit(s,u,'签核复核 '+str(i));return dump(r)
@router.get('/audits')
def audits(u=Depends(admin),s=Depends(db)):return [dump(r) for r in s.query(Audit).order_by(Audit.id.desc()).limit(100)]

@router.get('/fx/books')
def fx_books(u=Depends(current),s=Depends(db)):
 st=s.get(FxSetting,1);active=st.active_book_id if st else None
 out=[]
 for b in s.query(FxBook).order_by(FxBook.id.desc()).all():
  item=serialize_book(b);item['active']=b.id==active;item['rate_count']=s.query(FxRate).filter_by(book_id=b.id).count();out.append(item)
 return out
@router.post('/fx/books')
def create_book(data:FxBookInput,u=Depends(editor),s=Depends(db)):
 b=FxBook(name=data.name,note=data.note,status='draft',created=now());s.add(b);s.commit();audit(s,u,'新建汇率簿草稿 '+str(b.id));return serialize_book(b)
@router.get('/fx/books/{i}')
def fx_book(i:int,u=Depends(current),s=Depends(db)):
 b=s.get(FxBook,i)
 if not b:raise HTTPException(404,'汇率簿不存在')
 return {**serialize_book(b),'rates':book_rates(s,i)}
@router.put('/fx/books/{i}')
def edit_book(i:int,data:FxBookInput,u=Depends(editor),s=Depends(db)):
 b=draft_book(s,i);b.name=data.name;b.note=data.note;s.commit();audit(s,u,'修订汇率簿 '+str(i));return serialize_book(b)
@router.delete('/fx/books/{i}')
def delete_book(i:int,u=Depends(editor),s=Depends(db)):
 b=draft_book(s,i)
 if s.query(Training).filter_by(fx_book_id=i).first():raise HTTPException(409,'该汇率簿已被训练引用，不能删除')
 s.query(FxRate).filter_by(book_id=i).delete();s.delete(b);s.commit();audit(s,u,'删除汇率簿草稿 '+str(i));return {'deleted':i}
@router.post('/fx/books/{i}/rates')
def add_rate(i:int,data:FxRateInput,u=Depends(editor),s=Depends(db)):
 b=draft_book(s,i)
 r=FxRate(book_id=i,created=now(),**data.model_dump());s.add(r)
 try:s.flush()
 except IntegrityError:s.rollback();raise HTTPException(409,'同一币种对在相同生效起始已有汇率')
 b.validation=None;b.validated_at=None;s.commit();audit(s,u,'新增汇率 '+data.from_currency+'→'+data.to_currency);return dump(r)
@router.put('/fx/books/{i}/rates/{rid}')
def edit_rate(i:int,rid:int,data:FxRateInput,u=Depends(editor),s=Depends(db)):
 b=draft_book(s,i);r=s.get(FxRate,rid)
 if not r or r.book_id!=i:raise HTTPException(404,'汇率不存在')
 for k,v in data.model_dump().items():setattr(r,k,v)
 try:s.flush()
 except IntegrityError:s.rollback();raise HTTPException(409,'同一币种对在相同生效起始已有汇率')
 b.validation=None;b.validated_at=None;s.commit();audit(s,u,'修订汇率 #'+str(rid));return dump(r)
@router.delete('/fx/books/{i}/rates/{rid}')
def delete_rate(i:int,rid:int,u=Depends(editor),s=Depends(db)):
 b=draft_book(s,i);r=s.get(FxRate,rid)
 if not r or r.book_id!=i:raise HTTPException(404,'汇率不存在')
 s.delete(r);b.validation=None;b.validated_at=None;s.commit();audit(s,u,'删除汇率 #'+str(rid));return {'deleted':rid}
@router.post('/fx/books/{i}/validate')
def validate_book(i:int,u=Depends(editor),s=Depends(db)):
 b=draft_book(s,i);rates=book_rates(s,i)
 if not rates:raise HTTPException(422,'汇率簿为空，至少需要一条汇率')
 report=report_or_raise(b,rates);s.commit()
 audit(s,u,'校验汇率簿 '+str(i)+('：通过' if report['ok'] else '：失败'))
 return {**serialize_book(b),'report':report}
@router.post('/fx/books/{i}/publish')
def publish(i:int,u=Depends(editor),s=Depends(db)):
 # Same lock order as acceptance (settings row first, book second) so a
 # concurrent publish and training cannot deadlock or interleave halfway.
 st=lock_settings(s)
 b=draft_book(s,i);rates=book_rates(s,i,locking=True)
 if not rates:raise HTTPException(422,'汇率簿为空，至少需要一条汇率')
 report=report_or_raise(b,rates)
 if not report['ok']:s.commit();raise HTTPException(422,report_text(report))
 old=s.get(FxBook,st.active_book_id) if st.active_book_id else None
 if old and old.id!=b.id:old.status='retired'
 b.status='published';b.published_at=now();st.active_book_id=b.id
 s.commit()
 audit(s,u,'发布汇率簿 '+str(i))
 return {**serialize_book(b),'active':True,'report':report}
