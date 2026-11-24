// Test data that stands in for the artifact database during virtual-phone tests.
window.__data = {
 modules:[
  {id:'foundations',title:'Startup Law Basics',vol:'I',order:1,blurb:'Recognition, entity choice, shares and ESOPs.'},
  {id:'contracts',title:'Founders, Contracts & Disputes',vol:'II',order:2,blurb:'SHAs, non-competes, arbitration.'},
  {id:'funding',title:'Funding & FEMA',vol:'III',order:3,blurb:'Instruments, pricing, Press Note 3, buybacks.'},
  {id:'foreign',title:'Foreign Law & Offshore Structures',vol:'IV',order:4,blurb:'Flips, ODI rules, reverse flips, GIFT IFSC.'},
  {id:'tax',title:'Tax Strategies',vol:'V',order:5,blurb:'Income-tax Act 2025, holiday, ESOP tax.'},
  {id:'compliance',title:'Data, Tech & Employment',vol:'VI',order:6,blurb:'DPDP, labour codes, platforms.'},
  {id:'founders',title:'Founder Playbook: Control & Survival',vol:'VII',order:7,blurb:'Control, term sheets, staying out of court.'}],
 lessons:[
  {id:'f1',module:'foundations',order:1,title:'What counts as a startup',summary:'Recognition is the gateway to most benefits.',body:['A regular startup must be within 10 years of incorporation and under the turnover limit.','A Deep Tech category allows longer and larger.'],keyPoints:['Test point one','Test point two'],sources:[{t:'Source',u:'https://example.com'}],updated:'2026-11-24'},
  {id:'t1',module:'tax',order:1,title:'The Income-tax Act, 2025',summary:'Section numbers changed.',body:['Applies from tax year 2026-27.'],keyPoints:['Single tax year'],updated:'2026-11-24'},
  {id:'fp1',module:'founders',order:1,title:'Control = votes + board seats + vetoes',summary:'Watch the board.',body:['Control has four layers.'],keyPoints:['Board first']}],
 cases:[
  {id:'tiger',name:'AAR v Tiger Global International II Holdings',court:'Supreme Court',date:'15 Jan 2026',year:2026,citation:'2026 INSC 60',module:'tax',status:'Good law',tags:['GAAR','DTAA'],facts:'Mauritius entities sold Flipkart Singapore shares.',held:'Gains taxable in India.',why:'Substance matters.',src:{t:'Source',u:'https://example.com'}},
  {id:'voda',name:'Vodafone International Holdings v Union of India',court:'Supreme Court',year:2012,citation:'(2012) 6 SCC 613',module:'tax',status:'Superseded by statute',facts:'Offshore share sale.',held:'Not taxable as then worded.',why:'Led to indirect transfer rules.'}],
 gaps:[{id:'g1',order:1,module:'tax',title:'Mauritius treaty route',status:'Closed',gap:'Gains taxed only in Mauritius.',used:'Funds routed via Mauritius.',closed:'2016 protocol, GAAR, Tiger Global.',timeline:[{y:'2016',e:'Protocol'},{y:'2026',e:'Tiger Global'}],today:'Substance needed.',src:[{t:'Source',u:'https://example.com'}]}],
 stories:[
  {id:'byjus',order:1,short:"Byju's",name:"Byju's: debt, lenders and insolvency",who:'Founders',country:'India',year:2026,kind:'Insolvency',outcome:'Ongoing',what:'Lenders took control of the US unit.',move:'Foreign-law debt.',lesson:'Debt is control.',apply:'List events of default.',status:'Continuing.',checked:'2026-11-24'},
  {id:'zerodha',order:2,short:'Zerodha',name:'Zerodha: control by not raising',country:'India',year:2010,kind:'Control kept',outcome:'Kept control',what:'Never raised capital.',move:'Profitable early.',lesson:'Not needing money protects you.'}],
 traps:[{id:'pref',order:1,clause:'Participating liquidation preference',looks:'2x participating.',risk:'Founders get little in a modest exit.',ask:'1x non-participating.',india:'Contractual via SHA.'}],
 quiz:[{id:'q01',module:'foundations',q:'Turnover ceiling for a regular startup?',opts:['₹25 crore','₹100 crore','₹200 crore','₹300 crore'],a:2,why:'Raised to ₹200 crore.'}],
 updates:[
  {id:'u1',date:'2026-11-13',kind:'Law in force',module:'compliance',title:'DPDP phase 2: consent managers',summary:'Rule 4 applies.',src:{t:'Source',u:'https://example.com'}},
  {id:'u2',date:'2026-01-15',kind:'Judgment',module:'tax',title:'Supreme Court taxes Tiger Global exit',summary:'GAAR applied.'}]};
(function(){
 const snap=a=>({docs:a.map(d=>({id:d.id,exists:true,data:()=>d})),metadata:{fromCache:false}});
 window.claude={use:async n=>{
  if(n==='db')return{collection:p=>({onSnapshot:cb=>{setTimeout(()=>cb(snap(window.__data[p]||[])),50);return()=>{}},doc:()=>({get:async()=>({exists:false}),set:async()=>{}})}),
   doc:()=>({onSnapshot:cb=>{setTimeout(()=>cb({exists:true,data:()=>({lastChecked:'2026-11-24',note:'Test data'})}),50);return()=>{}}})};
  if(n==='user')return{id:async()=>'tester'};
  if(n==='sample'){return async(m,o)=>{o.onText&&o.onText({text:'Test answer.'});return{text:'Test answer.\nFrom the library: test',truncated:false}}}
  return null}};
})();
