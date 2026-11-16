import sys,json
sys.path.insert(0,'/workspace/backend')
from src.services.fx import validate_rates,convert_claim,error_summary,convert_claims

fails=[]
def ok(c,l,e=''):
 print(('PASS ' if c else 'FAIL ')+l+((' :: '+str(e)) if e and not c else ''))
 if not c:fails.append(l)

R=[
 {'from_currency':'USD','to_currency':'CNY','rate':7.10,'effective_from':'2026-01-01','effective_to':'2026-06-30'},
 {'from_currency':'USD','to_currency':'CNY','rate':7.25,'effective_from':'2026-07-01','effective_to':'2026-12-31'},
 {'from_currency':'EUR','to_currency':'USD','rate':1.2,'effective_from':'2026-01-01','effective_to':'2026-12-31'},
 {'from_currency':'USD','to_currency':'EUR','rate':0.833333,'effective_from':'2026-01-01','effective_to':'2026-12-31'},
]
# 1. date-scoped rate selection
a=convert_claim({'id':1,'code':'U1','amount':100,'currency':'USD','claim_date':'2026-03-14'},R,1)
b=convert_claim({'id':2,'code':'U2','amount':100,'currency':'USD','claim_date':'2026-08-02'},R,1)
ok(a['cny_amount']==710.0 and b['cny_amount']==725.0,'claim date selects the effective rate',(a['cny_amount'],b['cny_amount']))
ok(a['chain']['path']==['USD','CNY'],'direct path preferred')
# 2. intermediate-currency conversion, consistent with direct
c=convert_claim({'id':3,'code':'E1','amount':100,'currency':'EUR','claim_date':'2026-03-14'},R,1)
ok(c['status']=='ok' and c['chain']['path']==['EUR','USD','CNY'],'intermediate currency route used',c)
ok(abs(c['cny_amount']-100*1.2*7.1)<0.01,'chain product applied',c['cny_amount'])
ok(c['path_count']==1,'single consistent path counted')
# 3. contradictory paths fail with evidence
R2=R+[{'from_currency':'EUR','to_currency':'CNY','rate':7.9,'effective_from':'2026-01-01','effective_to':'2026-12-31'}]
d=convert_claim({'id':4,'code':'E2','amount':100,'currency':'EUR','claim_date':'2026-03-14'},R2,1)
ok(d['status']=='error' and 'EUR→CNY' in d['error'] and 'EUR→USD→CNY' in d['error'],'conflicting routes name both chains',d['error'])
ok(d['path_count']==2,'both priced paths counted',d['path_count'])
# 4. missing rate
e=convert_claim({'id':5,'code':'G1','amount':100,'currency':'GBP','claim_date':'2026-03-14'},R,1)
ok(e['status']=='error' and 'GBP→CNY' in e['error'] and '2026-03-14' in e['error'],'missing rate cites pair and date',e['error'])
# 5. expired rate on the claim date must not be used
f=convert_claim({'id':6,'code':'U3','amount':100,'currency':'USD','claim_date':'2027-03-14'},R,1)
ok(f['status']=='error','rate outside every interval is missing',f['error'])
g=convert_claim({'id':7,'code':'U4','amount':100,'currency':'USD','claim_date':'2026-06-30'},R,1)
ok(g['cny_amount']==710.0,'inclusive effective_to boundary')
h=convert_claim({'id':8,'code':'U5','amount':100,'currency':'USD','claim_date':'2026-07-01'},R,1)
ok(h['cny_amount']==725.0,'inclusive effective_from boundary')
# 6. no book at all
i=convert_claim({'id':9,'code':'U6','amount':100,'currency':'USD','claim_date':'2026-03-14'},[],None)
ok(i['status']=='error' and '汇率簿' in i['error'],'no published book fails clearly',i['error'])
# 7. legacy CNY ignores book requirement
j=convert_claim({'id':10,'code':'OLD','amount':88,'currency':None,'claim_date':None},[],None)
ok(j['status']=='ok' and j['rate']==1.0 and j['cny_amount']==88,'legacy row treated as CNY')
# 8. missing claim date for foreign currency
k=convert_claim({'id':11,'code':'U7','amount':100,'currency':'USD','claim_date':None},R,1)
ok(k['status']=='error' and '票据日期' in k['error'],'foreign claim without date fails')
# 9. error summary names tickets and basis for training failure
res,errs=convert_claims([{'id':12,'code':'BAD1','amount':10,'currency':'GBP','claim_date':'2026-01-01'},{'id':13,'code':'OK','amount':10,'currency':'CNY','claim_date':None}],R,1)
summary=error_summary(errs)
ok('BAD1' in summary and 'GBP' in summary and '2026-01-01' in summary,'summary cites ticket, currency and date',summary)
ok(len(res)==2 and errs[0]['claim_id']==12,'per-ticket records retained on failure')
# 10. validation: overlap (including infinite intervals), cycles, bad values
ov=validate_rates([{'from_currency':'USD','to_currency':'CNY','rate':7,'effective_from':'2026-01-01','effective_to':'2026-03-01'},{'from_currency':'USD','to_currency':'CNY','rate':7,'effective_from':'2026-03-01','effective_to':None},{'from_currency':'USD','to_currency':'CNY','rate':7,'effective_from':'2026-05-01','effective_to':None}])
ok(sum(1 for x in ov['errors'] if x['type']=='overlap')>=1,'overlap incl. infinite interval detected',ov['errors'])
cy=validate_rates([{'from_currency':'USD','to_currency':'EUR','rate':0.9,'effective_from':'2026-01-01','effective_to':None},{'from_currency':'EUR','to_currency':'USD','rate':1.2,'effective_from':'2026-01-01','effective_to':None}])
ok(not cy['ok'] and any(x['type']=='cycle' for x in cy['errors']),'cycle conflict detected',cy['errors'])
fine=validate_rates(R)
ok(fine['ok'],'reciprocal-rounded book passes cycle check',fine['errors'])
bad=validate_rates([{'from_currency':'USD','to_currency':'USD','rate':1,'effective_from':'2026-01-01','effective_to':None},{'from_currency':'USD','to_currency':'CNY','rate':-1,'effective_from':'2026-02-30','effective_to':'2026-01-01'}])
kinds={x['type'] for x in bad['errors']}
ok({'currency','rate','date'} <= kinds,'invalid currency/rate/date reported',bad['errors'])
print(json.dumps({'failed':fails},ensure_ascii=False))
