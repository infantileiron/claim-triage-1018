/** @typedef {{id:number,code:string,amount:number,currency:'CNY'|'USD'|'EUR'|'JPY'|string,claim_date:string|null,distance:number,holiday:boolean,label:0|1|null,note:string}} Claim */
/** @typedef {{id:number,name:string,threshold:number,state:string,fx_book_id:number|null,result:object,error:string}} Training */
/** @typedef {{id:number,claim_id:number,training_id:number,score:number,decision:string,status:string}} Review */
/** @typedef {{id:number,book_id:number,from_currency:string,to_currency:string,rate:number,effective_from:string,effective_to:string|null}} FxRate */
/** @typedef {{id:number,name:string,status:'draft'|'published'|'retired',note:string,active:boolean,rate_count:number,validation:object|null,rates?:FxRate[]}} FxBook */
/** @typedef {{claim_id:number,code:string,currency:string,original_amount:number,claim_date:string|null,rate:number|null,cny_amount:number|null,chain:{path:string[],legs:object[],rate:number}|null,path_count:number,book_id:number|null,status:'ok'|'error',error:string}} Conversion */
