from pydantic import BaseModel,Field,model_validator
from typing import Optional,Literal
import re
from datetime import date
CURRENCY=re.compile(r'^[A-Z]{3}$')
DATE=re.compile(r'^\d{4}-\d{2}-\d{2}$')
def _valid_date(v,label):
 if not DATE.match(v):raise ValueError(label+'须为 YYYY-MM-DD 格式')
 try:date.fromisoformat(v)
 except ValueError:raise ValueError(label+'不是有效的公历日期')
 return v
class Login(BaseModel):email:str;password:str
class ClaimInput(BaseModel):
 code:str=Field(min_length=1,max_length=60)
 amount:float=Field(ge=0,le=100000,allow_inf_nan=False)
 distance:float=Field(ge=0,le=10000,allow_inf_nan=False)
 holiday:bool=False
 label:Optional[Literal[0,1]]=None
 note:str=Field(default='',max_length=1000)
 currency:str=Field(default='CNY',max_length=10)
 claim_date:Optional[str]=Field(default=None,max_length=20)
 @model_validator(mode='after')
 def check_currency(self):
  self.currency=(self.currency or 'CNY').strip().upper()
  if not CURRENCY.match(self.currency):raise ValueError('币种须为三位字母代码，例如 CNY、USD')
  if self.claim_date:
   self.claim_date=_valid_date(self.claim_date.strip(),'票据日期')
  else:self.claim_date=None
  if self.currency!='CNY' and not self.claim_date:raise ValueError('外币报销必须填写票据日期，用于确定适用汇率')
  return self
class TrainingInput(BaseModel):
 name:str=Field(min_length=2,max_length=100)
 threshold:float=Field(default=.5,ge=.1,le=.9,allow_inf_nan=False)
class ReviewInput(BaseModel):
 decision:Literal['valid','flagged']
 note:str=Field(min_length=6,max_length=2000)
class FxBookInput(BaseModel):
 name:str=Field(min_length=2,max_length=100)
 note:str=Field(default='',max_length=1000)
class FxRateInput(BaseModel):
 from_currency:str=Field(max_length=10)
 to_currency:str=Field(max_length=10)
 rate:float=Field(gt=0,allow_inf_nan=False)
 effective_from:str=Field(max_length=20)
 effective_to:Optional[str]=Field(default=None,max_length=20)
 @model_validator(mode='after')
 def check(self):
  self.from_currency=self.from_currency.strip().upper();self.to_currency=self.to_currency.strip().upper()
  self.effective_from=self.effective_from.strip()
  if not CURRENCY.match(self.from_currency) or not CURRENCY.match(self.to_currency):raise ValueError('币种须为三位字母代码')
  if self.from_currency==self.to_currency:raise ValueError('汇率两端币种不能相同')
  _valid_date(self.effective_from,'生效起始')
  if self.effective_to is not None:
   self.effective_to=self.effective_to.strip() or None
   if self.effective_to:
    _valid_date(self.effective_to,'生效结束')
    if self.effective_to<self.effective_from:raise ValueError('生效结束不能早于生效起始')
  return self
