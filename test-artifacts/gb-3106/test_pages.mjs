globalThis.localStorage={getItem:()=>null,setItem(){},removeItem(){}};
globalThis.location={hash:'0'};
const base=await import('/workspace/frontend/src/stores/session.js');
const {state}=base;
const claims=await import('/workspace/frontend/src/pages/claims.js');
const training=await import('/workspace/frontend/src/pages/training.js');
const evaluation=await import('/workspace/frontend/src/pages/evaluation.js');
const reviews=await import('/workspace/frontend/src/pages/reviews.js');
const fx=await import('/workspace/frontend/src/pages/fx.js');
state.user={email:'analyst@demo.local',role:'analyst'};
state.claims=[{id:1,code:'A',amount:100,currency:'USD',claim_date:'2026-03-01',distance:10,holiday:false,label:1,note:''}];
state.trainings=[{id:5,name:'T',threshold:0.5,state:'failed',fx_book_id:2,error:'汇率折算失败 1 笔：A（2026-03-01，USD）：缺少 USD→CNY'}];
state.selected=state.trainings[0];
state.reviews=[];
state.fxBooks=[{id:1,name:'旧',status:'retired',active:false,rate_count:2,validation:null,published_at:'2026-01-01'},{id:2,name:'新',status:'draft',active:false,rate_count:1,validation:{ok:false,errors:[{type:'overlap',message:'汇率区间交叠'}]},published_at:null}];
state.fxBook={id:2,name:'新',status:'draft',note:'',rates:[{id:1,from_currency:'USD',to_currency:'CNY',rate:7.2,effective_from:'2027-01-01',effective_to:null}],validation:{ok:false,errors:[{type:'overlap',message:'汇率区间交叠'}]}};
state.conversions=[{code:'A',original_amount:100,currency:'USD',claim_date:'2026-03-01',cny_amount:null,rate:null,chain:null,status:'error',error:'缺少 USD→CNY 在 2026-03-01 的有效汇率'}];
const out={claims:claims.render(),training:training.render(),evaluation:evaluation.render(),reviews:reviews.render(),fx:fx.render()};
for(const [k,v] of Object.entries(out)){
 if(typeof v!=='string'||!v.length)throw new Error(k+' empty');
 console.log(k,v.length,'chars');
}
if(!out.evaluation.includes('沿用受理汇率依据重试'))throw new Error('retry button missing');
if(!out.evaluation.includes('缺少 USD→CNY'))throw new Error('error not shown');
if(!out.training.includes('无（外币票据将失败）'))throw new Error('active book hint wrong');
if(!out.fx.includes('区间交叠'))throw new Error('validation errors not shown');
if(!out.claims.includes('USD')||!out.claims.includes('2026-03-01'))throw new Error('currency/date columns missing');
console.log('UI RENDER OK');
