const {test} = require('node:test');
const assert = require('node:assert/strict');
const {project} = require('../public/fundamental-research.js');
test('future value and discounted value use different denominators', () => {
  const r = project({price:80,eps:5,growth:0,multiple:20,discount:0,years:5});
  assert.equal(r.future,100); assert.equal(r.present,100);
  assert.equal(r.margin,.2); assert.equal(r.upside,.25);
});
test('discounts the terminal price and excludes dividends', () => {
  const r = project({price:80,eps:5,growth:.1,multiple:20,discount:.1,years:5});
  assert.ok(Math.abs(r.present-100)<1e-10);
  assert.ok(Math.abs(r.annual-((r.future/80)**.2-1))<1e-10);
});
test('rejects losses, missing values and invalid horizon', () => {
  const b={price:80,eps:5,growth:0,multiple:20,discount:.1,years:5};
  for (const v of [{eps:-2},{eps:0},{eps:NaN},{price:0},{years:2},{growth:-1},{multiple:0}]) assert.throws(()=>project({...b,...v}));
});
test('WACC weights debt after tax and reports equity cost separately',()=>{
 const {capitalCost}=require('../public/fundamental-research.js');
 const r=capitalCost({riskFree:.04,premium:.05,beta:1.2,debtCost:.06,tax:.25,debtWeight:.2});
 assert.ok(Math.abs(r.equityCost-.1)<1e-12);
 assert.ok(Math.abs(r.wacc-.089)<1e-12);
 assert.throws(()=>capitalCost({riskFree:.04,premium:.05,beta:1.2,debtCost:.06,tax:.25,debtWeight:1.1}));
});
test('report preserves dates, distinguishes missing evidence and avoids invented values',()=>{
 const {buildReport}=require('../public/fundamental-research.js');
 const r=buildReport({ticker:'TEST',research:{as_of:'2026-01-01',currency:'USD',source:'https://example.org',coverage:{available:0,total:1},blocks:[{metrics:[{key:'altman',label:'Altman',display:'Sin dato',explanation:'Falta modelo',source:'https://example.org',value:null}]}],history:[],scenario:{currency:'USD'}}},null,null,'','2026-02-01');
 assert.ok(r.includes('Datos consultados: 2026-01-01'));
 assert.ok(r.includes('Generado: 2026-02-01'));
 assert.ok(r.includes('Moat y calidad de gestión no evaluables'));
 assert.ok(r.includes('No calculados'));
 assert.ok(!r.includes('[object Object]'));
});
