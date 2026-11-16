from datetime import datetime,timezone
from fastapi import HTTPException
from sqlalchemy import select
from src.models.entities import FxBook,FxRate,FxSetting
from src.services.fx import rate_dicts,validate_rates
def now():return datetime.now(timezone.utc).isoformat()
def lock_settings(s):
 """Lock the single settings row; must happen before reading the pointer.

 Every read that follows is a locking read too. InnoDB locking reads always
 observe the latest committed version (not the transaction's REPEATABLE READ
 snapshot, which may predate the lock because the auth dependency already
 queried the user), so acceptance can never pair a new pointer with old rates.
 """
 row=s.execute(select(FxSetting).where(FxSetting.id==1).with_for_update()).scalar_one_or_none()
 if row is None:
  s.add(FxSetting(id=1));s.flush()
  row=s.execute(select(FxSetting).where(FxSetting.id==1).with_for_update()).scalar_one()
 return row
def active_fx(s,locking=False):
 st=s.execute(select(FxSetting).where(FxSetting.id==1).with_for_update()).scalar_one_or_none() if locking else s.get(FxSetting,1)
 if not st or not st.active_book_id:return None,[]
 book=s.get(FxBook,st.active_book_id,with_for_update=locking)
 if not book or book.status!='published':return None,[]
 q=s.query(FxRate).filter_by(book_id=book.id)
 if locking:q=q.with_for_update()
 return book,rate_dicts(q.all())
def freeze_fx(s):
 lock_settings(s)
 return active_fx(s,locking=True)
def lock_book(s,i):
 book=s.get(FxBook,i,with_for_update=True)
 if not book:raise HTTPException(404,'汇率簿不存在')
 return book
def draft_book(s,i):
 book=lock_book(s,i)
 if book.status!='draft':raise HTTPException(409,'已发布或已退役的汇率簿不可修改')
 return book
def book_rates(s,i,locking=False):
 q=s.query(FxRate).filter_by(book_id=i)
 if locking:q=q.with_for_update()
 return rate_dicts(q.all())
def report_or_raise(book,rates):
 report=validate_rates(rates);book.validation=report
 book.validated_at=now() if report['ok'] else None
 return report
def report_text(report):
 if report['ok']:return '校验通过'
 return '汇率簿校验未通过：'+'；'.join(e['message'] for e in report['errors'][:8])+(f'（共 {len(report["errors"])} 项）' if len(report['errors'])>8 else '')
def serialize_book(book):
 return {'id':book.id,'name':book.name,'status':book.status,'note':book.note,'validation':book.validation,'validated_at':book.validated_at,'created':book.created,'published_at':book.published_at}
