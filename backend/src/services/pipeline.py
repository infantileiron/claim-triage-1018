from src.models.entities import Conversion
from src.services.analysis import train
from src.services.fx import convert_claims,error_summary

def save_conversions(s,training_id,conversions):
 s.query(Conversion).filter_by(training_id=training_id).delete()
 for c in conversions:
  s.add(Conversion(training_id=training_id,claim_id=c['claim_id'],code=c['code'],currency=c['currency'],
   original_amount=c['original_amount'],claim_date=c['claim_date'],rate=c['rate'],cny_amount=c['cny_amount'],
   chain=c['chain'],path_count=c['path_count'],book_id=c['book_id'],status=c['status'],error=c['error']))

def process(s,row):
 """Convert and train one queued row using its acceptance-time FX snapshot.

 Retries reuse row.fx_rates verbatim, so late back-dated rates or a newly
 published book cannot change conversions, holdout split or scores.
 """
 snapshot=row.result['snapshot'];rates=row.fx_rates or [];book_id=row.fx_book_id
 conversions,errors=convert_claims(snapshot,rates,book_id)
 save_conversions(s,row.id,conversions)
 if errors:
  row.state='failed';row.error=error_summary(errors)
  row.result={**(row.result or {}),'fx':{'book_id':book_id,'conversions_saved':True}}
  return row
 by_id={c['claim_id']:c for c in conversions}
 converted=[{**claim,'cny_amount':by_id[claim['id']]['cny_amount']} for claim in snapshot]
 result=train(converted,row.threshold)
 row.result={**result,'snapshot':snapshot,'fx':{'book_id':book_id,'claim_count':len(conversions),
  'path_rule':'取最短可用路径；多路径折算金额须一致；经中间币种路径同样参与校验','conversions_saved':True}}
 row.state='done';row.error=''
 return row
