from sqlalchemy import Column,Integer,String,Float,JSON,Text,ForeignKey,Boolean,UniqueConstraint
from src.config.database import Base
class User(Base):
 __tablename__='users'
 id=Column(Integer,primary_key=True);email=Column(String(100),unique=True);password=Column(String(200));role=Column(String(20))
class Claim(Base):
 __tablename__='claims'
 id=Column(Integer,primary_key=True);code=Column(String(60),unique=True,nullable=False)
 amount=Column(Float);distance=Column(Float);holiday=Column(Boolean);label=Column(Integer,nullable=True);note=Column(Text,default='')
 currency=Column(String(3),nullable=False,default='CNY',server_default='CNY')
 claim_date=Column(String(10),nullable=True)
class FxBook(Base):
 __tablename__='fx_books'
 id=Column(Integer,primary_key=True);name=Column(String(100),nullable=False);status=Column(String(20),default='draft')
 note=Column(Text,default='');validation=Column(JSON,nullable=True);validated_at=Column(String(40),nullable=True)
 created=Column(String(40),default='');published_at=Column(String(40),nullable=True)
class FxRate(Base):
 __tablename__='fx_rates'
 __table_args__=(UniqueConstraint('book_id','from_currency','to_currency','effective_from',name='uq_fx_rate_from'),)
 id=Column(Integer,primary_key=True);book_id=Column(Integer,ForeignKey('fx_books.id'),nullable=False)
 from_currency=Column(String(3),nullable=False);to_currency=Column(String(3),nullable=False);rate=Column(Float,nullable=False)
 effective_from=Column(String(10),nullable=False);effective_to=Column(String(10),nullable=True);created=Column(String(40),default='')
class FxSetting(Base):
 __tablename__='fx_settings'
 id=Column(Integer,primary_key=True);active_book_id=Column(Integer,nullable=True)
class Training(Base):
 __tablename__='trainings'
 id=Column(Integer,primary_key=True);name=Column(String(100));threshold=Column(Float);state=Column(String(20),default='queued');result=Column(JSON);error=Column(Text,default='')
 fx_book_id=Column(Integer,nullable=True);fx_rates=Column(JSON,nullable=True)
class Conversion(Base):
 __tablename__='conversions'
 __table_args__=(UniqueConstraint('training_id','claim_id',name='uq_conversion_claim'),)
 id=Column(Integer,primary_key=True);training_id=Column(Integer,ForeignKey('trainings.id'),nullable=False)
 claim_id=Column(Integer,nullable=False);code=Column(String(60));currency=Column(String(3));original_amount=Column(Float)
 claim_date=Column(String(10),nullable=True);rate=Column(Float,nullable=True);cny_amount=Column(Float,nullable=True)
 chain=Column(JSON,nullable=True);path_count=Column(Integer,default=1);book_id=Column(Integer,nullable=True)
 status=Column(String(10),default='ok');error=Column(Text,default='')
class Review(Base):
 __tablename__='reviews'
 __table_args__=(UniqueConstraint('training_id','claim_id',name='uq_review_source'),)
 id=Column(Integer,primary_key=True);training_id=Column(Integer,ForeignKey('trainings.id'));claim_id=Column(Integer,ForeignKey('claims.id'));score=Column(Float);decision=Column(String(30),default='pending');note=Column(Text,default='');status=Column(String(20),default='draft')
class Audit(Base):
 __tablename__='audits'
 id=Column(Integer,primary_key=True);actor=Column(String(100));action=Column(String(200));created=Column(String(40))
