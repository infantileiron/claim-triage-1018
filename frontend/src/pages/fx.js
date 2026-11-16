import {state} from '../stores/session.js';import {esc} from '../utils/html.js';import {badge} from '../components/common/status.js';import {field} from '../components/common/fields.js';import {table} from '../components/common/table.js';
const fmt=(v,n=4)=>v===null||v===undefined?'—':Number(v).toFixed(n).replace(/0+$/,'').replace(/\.$/,'');
export function render(){
 const active=state.fxBooks.find(b=>b.active);
 const book=state.fxBook;
 return `<div class="split"><section class="panel"><h2>汇率簿与生效区间 / ${state.fxBooks.length} 本</h2>
 <p>汇率按币种对与生效区间维护，发布后冻结。训练受理时整本取用，发布与训练并发只会看到完整旧簿或完整新簿。</p>
 ${table(['ID','名称','状态','汇率条数','校验','生效发布'],state.fxBooks.map(b=>[b.id,b.name,b.status+(b.active?' · 当前':''),b.rate_count,b.validation?(b.validation.ok?'通过':'未通过 '+b.validation.errors.length+' 项'):'未校验',b.published_at||'—']))}
 ${active?`<p class="notice">当前生效：<strong>#${active.id} ${esc(active.name)}</strong>，共 ${active.rate_count} 条。已受理训练继续沿用其受理时的汇率依据。</p>`:'<p class="notice">尚无已发布汇率簿。外币票据将无法折算，训练会失败并指出票据。</p>'}
 <h3>草稿编辑</h3>
 ${state.fxBooks.filter(b=>b.status==='draft').map(b=>`<button class="study" data-fx-book="${b.id}">#${b.id} ${esc(b.name)} · 草稿 ${b.rate_count} 条</button>`).join('')||'<p>暂无草稿。</p>'}
 <form id="fx-book">${field('汇率簿名称','name','text','required value="2027 年度汇率簿"')}${field('说明','note','text','')}<button class="primary">新建草稿</button></form>
 ${book?`<div class="fx-editor"><h3>#${book.id} ${esc(book.name)} ${badge(book.status)}</h3>
 <p>${esc(book.note||'无说明')}</p>
 ${book.validation&&!book.validation.ok?`<div class="notice">${book.validation.errors.map(e=>esc(e.message)).join('<br>')}</div>`:''}
 ${book.status==='draft'?`<form id="fx-rate"><input type="hidden" name="book_id" value="${book.id}"><input type="hidden" name="rate_id" value="">${field('从币种','from_currency','text','required maxlength=3 value="USD"')}${field('到币种','to_currency','text','required maxlength=3 value="CNY"')}${field('汇率','rate','number','required min=0.000001 step=0.000001 value="7.1"')}${field('生效起','effective_from','date','required value="2027-01-01"')}${field('生效止（空为无限期）','effective_to','date','')}<button class="primary" id="fx-save">添加汇率</button></form>
 <p><button data-fx-validate="${book.id}">校验草稿</button> <button data-fx-publish="${book.id}">发布生效</button></p>
 <div class="scroll"><table><thead><tr><th>ID</th><th>从</th><th>到</th><th>汇率</th><th>生效起</th><th>生效止</th><th>操作</th></tr></thead><tbody>${book.rates.map(r=>`<tr><td>${r.id}</td><td>${esc(r.from_currency)}</td><td>${esc(r.to_currency)}</td><td>${fmt(r.rate,6)}</td><td>${esc(r.effective_from)}</td><td>${esc(r.effective_to||'无限期')}</td><td><button data-fx-edit="${r.id}" data-book="${book.id}">编辑</button> <button data-fx-del="${r.id}" data-book="${book.id}">删除</button></td></tr>`).join('')||'<tr><td colspan="7">暂无汇率。</td></tr>'}</tbody></table></div>
 <p>校验会检查同币种对区间交叠、日期分段下的循环汇率冲突和多路径矛盾。发布前必须校验通过。</p>`:''}
 </div>`:''}
 </section><aside class="side"><h2>口径</h2><ul class="steps"><li>金额特征按票据日期折算人民币。</li><li>允许经中间币种换算。</li><li>多路径金额须一致，否则训练失败。</li><li>缺汇率时指出票据与依据。</li><li>旧样本无币种，按人民币处理。</li><li>汇率簿发布后不可改；后续补发历史汇率请新建版本。</li></ul></aside></div>`}
