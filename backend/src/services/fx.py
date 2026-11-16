import re
from collections import defaultdict
from datetime import date
BASE='CNY'
CURRENCY_RE=re.compile(r'^[A-Z]{3}$')
PATH_LIMIT=1000
AMOUNT_TOLERANCE=0.005   # half a cent: rounding noise is not a contradiction
CYCLE_TOLERANCE=1e-3     # rounded reciprocal rates; gross conflicts still fail

def norm_currency(x):
 return (x or '').strip().upper()

def parse_date(x):
 if not isinstance(x,str) or not re.match(r'^\d{4}-\d{2}-\d{2}$',x):raise ValueError('日期须为 YYYY-MM-DD 格式')
 try:return date.fromisoformat(x)
 except ValueError:raise ValueError('日期不是有效的公历日期')

def rate_dicts(rows):
 """ORM rows or dicts -> plain dicts in a deterministic order."""
 out=[]
 for r in rows or []:
  if isinstance(r,dict):out.append({k:r.get(k) for k in ('id','from_currency','to_currency','rate','effective_from','effective_to')})
  else:out.append({'id':r.id,'from_currency':r.from_currency,'to_currency':r.to_currency,'rate':r.rate,'effective_from':r.effective_from,'effective_to':r.effective_to})
 return sorted(out,key=lambda r:(r['from_currency'],r['to_currency'],r['effective_from']))

def active(r,day):
 return r['effective_from']<=day and (not r.get('effective_to') or day<=r['effective_to'])

def graph_on(rates,day):
 g=defaultdict(list)
 for r in rates:
  if active(r,day):g[r['from_currency']].append(r)
 for edges in g.values():edges.sort(key=lambda r:r['to_currency'])
 return g

def enumerate_paths(rates,source,target,day,limit=PATH_LIMIT):
 """All simple directed paths, with a truncation flag.

 The shortest path is reported as the applied chain; every other path is priced
 too so that contradictory routes fail instead of silently passing. If the
 graph is too dense to enumerate, the caller must fail rather than guess.
 """
 g=graph_on(rates,day)
 paths=[];truncated=False
 def walk(node,visited,currencies,legs,product):
  nonlocal truncated
  for edge in g.get(node,[]):
   nxt=edge['to_currency']
   if nxt in visited:continue
   if len(paths)>=limit:truncated=True;return
   legs2=legs+[{'from':edge['from_currency'],'to':nxt,'rate':edge['rate']}]
   prod2=product*edge['rate']
   if nxt==target:paths.append((currencies+[nxt],legs2,prod2))
   else:walk(nxt,visited|{nxt},currencies+[nxt],legs2,prod2)
 walk(source,{source},[source],[],1.0)
 paths.sort(key=lambda p:(len(p[0]),p[0]))
 return paths,truncated

def convert_claim(claim,rates,book_id=None):
 """Return one conversion record; status 'ok' or 'error'.

 CNY and legacy samples (no currency) use rate 1 without needing a book.
 Foreign claims are converted by claim_date's effective rates, optionally via
 intermediate currencies. Any missing route or conflicting priced route is an
 error naming the ticket and the evidence.
 """
 cur=norm_currency(claim.get('currency') or BASE);amount=claim.get('amount');day=claim.get('claim_date')
 out={'claim_id':claim.get('id'),'code':claim.get('code'),'currency':cur,'original_amount':amount,
      'claim_date':day,'rate':None,'cny_amount':None,'chain':None,'path_count':0,'book_id':book_id,'status':'ok','error':''}
 if cur==BASE:
  out.update(rate=1.0,cny_amount=amount,path_count=1,chain={'path':[BASE],'legs':[],'rate':1.0})
  return out
 if not day:
  out.update(status='error',error='外币票据缺少票据日期，无法确定适用汇率');return out
 try:parse_date(day)
 except ValueError as e:out.update(status='error',error=f'票据日期无效（{day}）：{e}');return out
 try:amount=float(amount)
 except (TypeError,ValueError):out.update(status='error',error='原金额无效');return out
 if book_id is None:
  out.update(status='error',error=f'缺少已发布汇率簿，无法折算 {cur}→{BASE}（票据日期 {day}）');return out
 paths,truncated=enumerate_paths(rates,cur,BASE,day)
 if truncated:
  out.update(status='error',error=f'{cur}→{BASE} 在 {day} 的可用换算路径超过 {PATH_LIMIT} 条，无法逐一核对，请简化汇率簿后再训练')
  return out
 if not paths:
  out.update(status='error',error=f'缺少 {cur}→{BASE} 在 {day} 的有效汇率（直接及经中间币种均无可用路径）');return out
 priced=[(p[0],p[1],p[2],amount*p[2]) for p in paths]
 first=priced[0]
 clashes=[p for p in priced[1:] if abs(p[3]-first[3])>AMOUNT_TOLERANCE]
 if clashes:
  detail='；'.join(f"{'→'.join(p[0])} 汇率 {p[2]:.6g} 折算 {p[3]:.2f} {BASE}" for p in priced)
  out.update(status='error',path_count=len(priced),error=f'多条可用路径折算金额矛盾：{detail}')
  return out
 path,legs,product,raw=first
 out.update(rate=product,cny_amount=round(raw,2),path_count=len(priced),chain={'path':path,'legs':legs,'rate':product})
 return out

def convert_claims(claims,rates,book_id=None):
 results=[convert_claim(c,rates or [],book_id) for c in claims]
 return results,[r for r in results if r['status']!='ok']

def error_summary(errors):
 if not errors:return ''
 shown=errors[:20]
 text='汇率折算失败 '+str(len(errors))+' 笔：'+'；'.join(f"{e['code']}（{e['claim_date'] or '无票据日期'}，{e['currency']}）：{e['error']}" for e in shown)
 if len(errors)>20:text+='；其余 '+str(len(errors)-20)+' 笔见换算明细'
 return text

def _overlaps(rates):
 errors=[];pairs=defaultdict(list)
 for r in rates:pairs[(r['from_currency'],r['to_currency'])].append(r)
 for (a,b),rows in sorted(pairs.items()):
  rows=sorted(rows,key=lambda r:r['effective_from'])
  reach=None;reach_row=None;infinite=False
  for r in rows:
   if reach_row is not None and (infinite or r['effective_from']<=reach):
    end=reach_row.get('effective_to') or '无限期'
    errors.append({'type':'overlap','message':f'汇率区间交叠：{a}→{b} 的 {reach_row["effective_from"]}~{end} 与 {r["effective_from"]}~{r.get("effective_to") or "无限期"}'})
   end=r.get('effective_to')
   if end is None:infinite=True;reach_row=r
   elif not infinite and (reach is None or end>reach):reach=end;reach_row=r
 return errors

def _canon(cycle):
 body=cycle[:-1];i=min(range(len(body)),key=lambda k:body[k])
 return tuple(body[i:]+body[:i])

def _cycle_conflicts(rates):
 dates=sorted({r['effective_from'] for r in rates}|{r['effective_to'] for r in rates if r.get('effective_to')})
 errors=[];seen=set()
 for day in dates:
  g=graph_on(rates,day);found={}
  def dfs(start,node,path,product):
   for edge in g.get(node,[]):
    nxt=edge['to_currency']
    if nxt==start and len(path)>=2:
     p=product*edge['rate']
     if abs(p-1)>CYCLE_TOLERANCE:
      cyc=path+[start];key=(_canon(cyc),day)
      if key not in seen:seen.add(key);found[key]=(cyc,p)
    elif nxt not in path:dfs(start,nxt,path+[nxt],product*edge['rate'])
    if len(found)>=PATH_LIMIT:return
  for start in sorted(g):dfs(start,start,[start],1.0)
  for key in sorted(found,key=str):
   cyc,p=found[key]
   errors.append({'type':'cycle','date':day,'cycle':cyc,'product':p,
                  'message':f'循环汇率冲突：{"→".join(cyc)} 在 {day} 的汇率乘积为 {p:.8g}，偏离 1 超过 {CYCLE_TOLERANCE:g}'})
 return errors

def validate_rates(rates):
 rates=rate_dicts(rates);errors=[]
 for r in rates:
  a=norm_currency(r.get('from_currency'));b=norm_currency(r.get('to_currency'))
  if not CURRENCY_RE.match(a or '') or not CURRENCY_RE.match(b or ''):errors.append({'type':'currency','message':f'币种须为三位字母代码：{r.get("from_currency")}→{r.get("to_currency")}'})
  elif a==b:errors.append({'type':'currency','message':f'汇率两端币种不能相同：{a}'})
  rate=r.get('rate')
  if not isinstance(rate,(int,float)) or isinstance(rate,bool) or not (rate>0) or rate in (float('inf'),float('-inf')) or rate!=rate:errors.append({'type':'rate','message':f'{a}→{b} 的汇率须为正数'})
  try:parse_date(r.get('effective_from'))
  except ValueError as e:errors.append({'type':'date','message':f'{a}→{b} 生效起始：{e}'})
  if r.get('effective_to'):
   try:
    parse_date(r['effective_to'])
    if r.get('effective_from') and r['effective_to']<r['effective_from']:errors.append({'type':'date','message':f'{a}→{b} 的失效日期早于生效日期'})
   except ValueError as e:errors.append({'type':'date','message':f'{a}→{b} 生效结束：{e}'})
 if not errors:
  errors.extend(_overlaps(rates));errors.extend(_cycle_conflicts(rates))
 return {'ok':not errors,'errors':errors,'rate_count':len(rates),
         'checked_dates':sorted({r['effective_from'] for r in rates}|{r['effective_to'] for r in rates if r.get('effective_to')})}
