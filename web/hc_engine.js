/* HoldCapital engine — JavaScript port of holdcapital/engine.py + importer.py.
   Pure logic (no DOM) so it runs identically in the browser and in Node.
   Verified against the Python reference numbers. */
(function (root) {
"use strict";

var COMPANY_TAX_RATE = 0.30, MEDICARE = 0.02;
var ATO = [[0,18200,0],[18200,45000,0.16],[45000,135000,0.30],[135000,190000,0.37],[190000,Infinity,0.45]];
var RESOURCE_TAGS = ["Iron ore","Copper","Gold","Lithium","Uranium"];
var TAG_COLOUR = {"Iron ore":"#888780","Copper":"#D85A30","Gold":"#EF9F27","Lithium":"#1D9E75",
  "Uranium":"#7F77DD","US Tech":"#378ADD","US Pharma":"#534AB7","AU Healthcare":"#0F6E56",
  "Crypto":"#D4537E","Precious metals":"#BA7517","Unknown":"#B4B2A9"};

/* Security master (mirrors holdcapital/data/securities.csv). */
var SECURITIES = {
  BHP:{name:"BHP Group",exchange:"ASX",tag:"Iron ore",ccy:"AUD",px:57.0,fx:1.0},
  FMG:{name:"Fortescue",exchange:"ASX",tag:"Iron ore",ccy:"AUD",px:21.0,fx:1.0},
  PLS:{name:"Pilbara Minerals",exchange:"ASX",tag:"Lithium",ccy:"AUD",px:2.30,fx:1.0},
  DEG:{name:"De Grey Mining",exchange:"ASX",tag:"Gold",ccy:"AUD",px:1.62,fx:1.0},
  BOE:{name:"Boss Energy",exchange:"ASX",tag:"Uranium",ccy:"AUD",px:4.20,fx:1.0},
  SFR:{name:"Sandfire Resources",exchange:"ASX",tag:"Copper",ccy:"AUD",px:11.0,fx:1.0},
  CSL:{name:"CSL Limited",exchange:"ASX",tag:"AU Healthcare",ccy:"AUD",px:250.0,fx:1.0},
  NVDA:{name:"NVIDIA",exchange:"NASDAQ",tag:"US Tech",ccy:"USD",px:175.0,fx:1.52},
  MSFT:{name:"Microsoft",exchange:"NASDAQ",tag:"US Tech",ccy:"USD",px:480.0,fx:1.52},
  MRNA:{name:"Moderna",exchange:"NASDAQ",tag:"US Pharma",ccy:"USD",px:70.0,fx:1.52}
};

/* ---------- helpers ---------- */
function money(x){ var n=Math.round(Math.abs(x)).toLocaleString("en-AU"); return (x<0?"-$":"$")+n; }
function num(s){ if(s==null) return 0; s=(""+s).replace(/[$,]/g,"").trim(); if(s===""||s==="-") return 0; var v=parseFloat(s); return isNaN(v)?0:v; }
function parseDate(s){
  s=(s||"").trim();
  var m=s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{2,4})$/);
  if(m){ var y=+m[3]; if(y<100) y+=2000; return new Date(Date.UTC(y,+m[2]-1,+m[1])); }
  m=s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if(m) return new Date(Date.UTC(+m[1],+m[2]-1,+m[3]));
  m=s.match(/^(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})$/);
  if(m){ var mo={jan:0,feb:1,mar:2,apr:3,may:4,jun:5,jul:6,aug:7,sep:8,oct:9,nov:10,dec:11}[m[2].toLowerCase()];
         if(mo!=null) return new Date(Date.UTC(+m[3],mo,+m[1])); }
  return null;
}
function days(a,b){ return Math.round((b-a)/86400000); }
function fmtD(d){ var mo=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  return ("0"+d.getUTCDate()).slice(-2)+" "+mo[d.getUTCMonth()]+" "+(""+d.getUTCFullYear()).slice(2); }

function parseCSV(text){
  var lines=text.replace(/\r/g,"").split("\n").filter(function(l){return l.trim()!=="";});
  if(!lines.length) return {headers:[],rows:[]};
  function split(line){ var out=[],cur="",q=false;
    for(var i=0;i<line.length;i++){var c=line[i];
      if(c==='"'){q=!q;} else if(c===","&&!q){out.push(cur);cur="";} else cur+=c;}
    out.push(cur); return out.map(function(x){return x.trim();}); }
  var headers=split(lines[0]);
  var rows=lines.slice(1).map(function(l){var c=split(l),o={};
    headers.forEach(function(h,i){o[h.toLowerCase()]=c[i];}); return o;});
  return {headers:headers,rows:rows};
}

/* ---------- account ---------- */
function Account(opt){ opt=opt||{};
  this.entity=opt.entity||"individual";
  this.marginalRate=opt.marginalRate!=null?opt.marginalRate:0.37;
  this.otherIncome=opt.otherIncome!=null?opt.otherIncome:null;
  this.fyStart=new Date(Date.UTC(2025,6,1)); this.fyEnd=new Date(Date.UTC(2026,5,30));
  this.today=opt.today||new Date(Date.UTC(2026,5,13));
}
Account.prototype.discountRate=function(){ return {individual:0.5,trust:0.5,smsf:1/3,company:0}[this.entity]; };
function incomeTax(t){ var x=0; for(var i=0;i<ATO.length;i++){var lo=ATO[i][0],hi=ATO[i][1],r=ATO[i][2];
  if(t>lo) x+=(Math.min(t,hi)-lo)*r;} return x; }
Account.prototype.marginalTaxOn=function(extra){
  if(this.otherIncome==null) return extra*(this.marginalRate+MEDICARE);
  var b=this.otherIncome;
  var t0=incomeTax(b)+b*MEDICARE, t1=incomeTax(b+extra)+(b+extra)*MEDICARE;
  return t1-t0;
};

/* ---------- importer ---------- */
var CS_TRADE=/^\s*([BS])\s+([\d,]+)\s+([A-Z0-9]{2,6})\s+@\s+\$?([\d.]+)/i;
var CS_DRP=/\bDRP\b.*?([\d,]+)\s+([A-Z0-9]{2,6})\s+@\s+\$?([\d.]+)/i;
var CS_DIV=/\bDIV(?:IDEND)?\b\s+([A-Z0-9]{2,6})/i;

function detect(headers){
  var h=headers.map(function(x){return x.toLowerCase();});
  function has(k){return h.indexOf(k)>=0;}
  if(has("franking credit")||has("franked %")||has("franked amount")) return "statement";
  if(has("details")&&h.some(function(c){return c.indexOf("debit")===0;})) return "commsec";
  if(has("symbol")&&(has("side")||has("fx rate"))) return "stake";
  if(has("instrument code")||(has("trade date")&&has("transaction type"))) return "sharesight";
  if(has("code")&&has("units")&&(has("type")||has("buy/sell"))) return "selfwealth";
  if((has("code")||has("symbol"))&&(has("units")||has("quantity")||has("available units"))
     &&(has("market value")||has("mkt value")||has("value")||has("last price"))
     &&!has("details")&&!has("transaction type")&&!has("side")) return "holdings";
  return "unknown";
}

function importText(text){
  var p=parseCSV(text), broker=detect(p.headers);
  var res={broker:broker,trades:[],dividends:[],holdings:[],review:[]};
  function flag(i,reason,raw,sev){ res.review.push({row:i,reason:reason,raw:raw,severity:sev||"review"}); }
  if(broker==="unknown"){ flag(1,"could not detect broker format",p.headers.join(", ")); return res; }
  p.rows.forEach(function(r,idx){
    var i=idx+2;
    if(broker==="commsec"){
      var details=(r["details"]||"").trim();
      var debit=num(r["debit($)"]||r["debit"]), credit=num(r["credit($)"]||r["credit"]);
      var dt=parseDate(r["date"]); if(!dt){flag(i,"unrecognised date",details);return;}
      var m=CS_TRADE.exec(details);
      if(m){ var side=m[1].toUpperCase(),qty=num(m[2]),code=m[3].toUpperCase(),price=parseFloat(m[4]);
        var brk = side==="B" ? debit-qty*price : qty*price-credit;
        res.trades.push({date:dt,ticker:code,action:side==="B"?"BUY":"SELL",qty:qty,price:price,brokerage:Math.max(brk,0),fx:1.0}); return; }
      var d=CS_DRP.exec(details);
      if(d){ var q=num(d[1]),c=d[2].toUpperCase(),px=parseFloat(d[3]);
        res.trades.push({date:dt,ticker:c,action:"BUY",qty:q,price:px,brokerage:0,fx:1.0,note:"DRP"});
        flag(i,"DRP allotment imported as new parcel: "+q+" "+c+" @ "+px+" (cost base "+money(q*px)+")",details,"info"); return; }
      var md=CS_DIV.exec(details);
      if(md&&credit>0){ res.dividends.push({date:dt,ticker:md[1].toUpperCase(),cash:credit,franking:1.0,withholding:0,fx:1.0});
        if(!/franked/i.test(details)) flag(i,"dividend franking % not in export — assumed fully franked ("+md[1]+")",details,"info"); return; }
      if(debit||credit) flag(i,"unrecognised cash movement (fee/interest/transfer?)",details);
    } else if(broker==="stake"){
      var dt2=parseDate(r["date"]); if(!dt2){flag(i,"unrecognised date",JSON.stringify(r));return;}
      var typ=(r["type"]||"").toLowerCase(), sym=(r["symbol"]||"").toUpperCase(), fx=num(r["fx rate"]||r["fx"])||1.0;
      if(["trade","buy","sell","order"].indexOf(typ)>=0 || (r["side"]||"").trim()){
        var sd=(r["side"]||typ).toLowerCase(), act=sd.indexOf("buy")>=0?"BUY":sd.indexOf("sell")>=0?"SELL":null;
        if(!act){flag(i,"could not determine buy/sell",JSON.stringify(r));return;}
        res.trades.push({date:dt2,ticker:sym,action:act,qty:num(r["units"]||r["quantity"]),
          price:num(r["price (usd)"]||r["price"]),brokerage:num(r["brokerage (usd)"]||r["brokerage"]),fx:fx});
      } else if(typ.indexOf("div")>=0){
        res.dividends.push({date:dt2,ticker:sym,cash:num(r["amount (usd)"]||r["amount"]||r["price"]),
          franking:0,withholding:num(r["withholding (usd)"]||r["withholding"]),fx:fx});
      } else flag(i,"unhandled Stake row type '"+typ+"'",JSON.stringify(r));
    } else if(broker==="statement"){
      var dt3=parseDate(r["date"]); if(!dt3){flag(i,"unrecognised date",JSON.stringify(r));return;}
      var cash=num(r["cash"]||r["amount"]||r["net dividend"]);
      var fc=r["franking credit"]||r["franking credits"], fp=r["franked %"], credit3;
      if(fc!=null&&fc!=="") credit3=num(fc);
      else if(fp!=null&&fp!=="") credit3=cash*(num(fp)/100)*(0.30/0.70);
      else { credit3=0; flag(i,"no franking data on statement row",JSON.stringify(r)); }
      res.dividends.push({date:dt3,ticker:(r["code"]||r["ticker"]).toUpperCase(),cash:cash,franking:0,
        withholding:0,fx:1.0,frankingCredit:Math.round(credit3*100)/100});
    } else if(broker==="sharesight"){
      var dt4=parseDate(r["trade date"]||r["date"]); if(!dt4){flag(i,"unrecognised date",JSON.stringify(r));return;}
      var a=(r["transaction type"]||"").toUpperCase(); if(a!=="BUY"&&a!=="SELL"){flag(i,"unknown transaction type",JSON.stringify(r));return;}
      res.trades.push({date:dt4,ticker:(r["instrument code"]||r["code"]).toUpperCase(),action:a,
        qty:num(r["quantity"]),price:num(r["price"]),brokerage:num(r["brokerage"]),fx:num(r["exchange rate"]||r["fx"])||1.0});
    } else if(broker==="selfwealth"){
      var dt5=parseDate(r["date"]||r["trade date"]); if(!dt5){flag(i,"unrecognised date",JSON.stringify(r));return;}
      var ty=(r["type"]||r["buy/sell"]||"").toUpperCase(), ac=ty[0]==="B"?"BUY":ty[0]==="S"?"SELL":null;
      if(!ac){flag(i,"unknown trade type",JSON.stringify(r));return;}
      res.trades.push({date:dt5,ticker:(r["code"]).toUpperCase(),action:ac,qty:num(r["units"]||r["quantity"]),
        price:num(r["price"]),brokerage:num(r["brokerage"]),fx:1.0});
    } else if(broker==="holdings"){
      var tk=(r["code"]||r["symbol"]||"").toUpperCase();
      if(!tk){ flag(i,"holdings row missing code",JSON.stringify(r)); return; }
      res.holdings.push({ticker:tk,qty:num(r["units"]||r["quantity"]||r["available units"]),
        avgCost:num(r["avg cost"]||r["purchase price"]||r["average price"]||r["cost base"]),
        value:num(r["market value"]||r["mkt value"]||r["value"])});
    }
  });
  res.trades.sort(function(a,b){return a.date-b.date;});
  return res;
}

/* ---------- engine ---------- */
function matchParcels(secs, trades, account, method){
  method=method||"fifo";
  var open={}, events=[];
  var sorted=trades.slice().sort(function(a,b){return a.date-b.date;});
  sorted.forEach(function(t){
    if(!open[t.ticker]) open[t.ticker]=[];
    if(t.action==="BUY"){
      var unit=(t.qty*t.price+t.brokerage)*t.fx/t.qty;
      open[t.ticker].push({ticker:t.ticker,acquired:t.date,qty:t.qty,qtyOpen:t.qty,unitCost:unit});
      return;
    }
    var qtyToSell=t.qty, netUnit=t.price*t.fx-(t.brokerage*t.fx)/t.qty, lots=open[t.ticker];
    function taxPerUnit(lot){ var held=days(lot.acquired,t.date), g=netUnit-lot.unitCost;
      return (g>0&&held>365&&account.discountRate()>0)? g*(1-account.discountRate()) : g; }
    var order = method==="fifo" ? lots.slice() : lots.slice().sort(function(a,b){return taxPerUnit(a)-taxPerUnit(b);});
    order.forEach(function(lot){
      if(qtyToSell<=1e-9) return;
      var take=Math.min(lot.qtyOpen,qtyToSell), cost=take*lot.unitCost, proceeds=take*netUnit, held=days(lot.acquired,t.date), gain=proceeds-cost;
      events.push({ticker:t.ticker,name:(secs[t.ticker]||{}).name||t.ticker,acquired:lot.acquired,disposed:t.date,
        qty:take,costBase:cost,proceeds:proceeds,gain:gain,daysHeld:held,
        discountable:(held>365&&gain>0&&account.discountRate()>0)});
      lot.qtyOpen-=take; qtyToSell-=take;
    });
    open[t.ticker]=lots.filter(function(l){return l.qtyOpen>1e-9;});
  });
  return {events:events,open:open};
}

function computeCGT(events, account){
  var fy=events.filter(function(e){return e.disposed>=account.fyStart&&e.disposed<=account.fyEnd;});
  var disc=0,nondisc=0,losses=0;
  fy.forEach(function(e){ if(e.gain>0){ if(e.discountable) disc+=e.gain; else nondisc+=e.gain; } else losses+=-e.gain; });
  var pool=losses;
  var nondiscAfter=nondisc-Math.min(pool,nondisc); pool-=(nondisc-nondiscAfter);
  var discAfter=disc-Math.min(pool,disc); pool-=(disc-discAfter);
  var discount=discAfter*account.discountRate();
  var net=nondiscAfter+(discAfter-discount);
  return {events:fy,grossGains:disc+nondisc,losses:losses,gainsAfterLosses:nondiscAfter+discAfter,
    discAfter:discAfter,discount:discount,netCapitalGain:net,carryForward:pool};
}

function frankingCredit(d){ if(d.frankingCredit!=null) return d.frankingCredit;
  return d.cash*d.fx*(d.franking||0)*(COMPANY_TAX_RATE/(1-COMPANY_TAX_RATE)); }
function computeIncome(divs, account){
  var fy=divs.filter(function(d){return d.date>=account.fyStart&&d.date<=account.fyEnd;});
  var auCash=0,franking=0,foreign=0,fito=0;
  fy.forEach(function(d){
    if((d.withholding||0)===0&&d.fx===1.0) auCash+=d.cash*d.fx;
    if(d.fx===1.0) franking+=frankingCredit(d);
    if(d.fx!==1.0) foreign+=d.cash*d.fx;
    fito+=(d.withholding||0)*d.fx;
  });
  return {auCash:auCash,franking:franking,foreignCash:foreign,fito:fito};
}
function estimateTax(cgt, income, account){
  var assessable=cgt.netCapitalGain+income.auCash+income.franking+income.foreignCash;
  var gross=account.marginalTaxOn(assessable), offsets=income.franking+income.fito;
  return {assessable:assessable,grossTax:gross,offsets:offsets,netTax:gross-offsets};
}
function exposureXray(secs, open){
  var positions=[], byTag={};
  Object.keys(open).forEach(function(tk){
    var qty=open[tk].reduce(function(s,l){return s+l.qtyOpen;},0); if(qty<=1e-9) return;
    var sec=secs[tk]||{name:tk,tag:"Unknown",px:0,fx:1};
    var value=qty*sec.px*sec.fx, cost=open[tk].reduce(function(s,l){return s+l.qtyOpen*l.unitCost;},0);
    positions.push({ticker:tk,name:sec.name,tag:sec.tag,value:value,unrealised:value-cost});
    byTag[sec.tag]=(byTag[sec.tag]||0)+value;
  });
  var total=positions.reduce(function(s,p){return s+p.value;},0)||1;
  var tags=Object.keys(byTag).map(function(k){return {tag:k,value:byTag[k],weight:byTag[k]/total};})
    .sort(function(a,b){return b.value-a.value;});
  var res=0; Object.keys(byTag).forEach(function(k){ if(RESOURCE_TAGS.indexOf(k)>=0) res+=byTag[k]; });
  return {positions:positions.sort(function(a,b){return b.value-a.value;}),total:total,tags:tags,resourcesWeight:res/total};
}
function exposureFromHoldings(secs, holdings){
  var positions=[], byTag={};
  holdings.forEach(function(h){
    var sec=secs[h.ticker]||{name:h.ticker,tag:"Unknown",px:0,fx:1};
    var value=h.value || h.qty*sec.px*sec.fx;
    positions.push({ticker:h.ticker,name:sec.name,tag:sec.tag,value:value,unrealised:0});
    byTag[sec.tag]=(byTag[sec.tag]||0)+value;
  });
  var total=positions.reduce(function(s,p){return s+p.value;},0)||1;
  var tags=Object.keys(byTag).map(function(k){return {tag:k,value:byTag[k],weight:byTag[k]/total};})
    .sort(function(a,b){return b.value-a.value;});
  var res=0; Object.keys(byTag).forEach(function(k){ if(RESOURCE_TAGS.indexOf(k)>=0) res+=byTag[k]; });
  return {positions:positions.sort(function(a,b){return b.value-a.value;}),total:total,tags:tags,resourcesWeight:res/total};
}

function closedTradesFrom(events){
  function iso(d){ return d.toISOString().slice(0,10); }
  return events.map(function(e){
    return {key:e.ticker+"|"+iso(e.acquired)+"|"+iso(e.disposed),ticker:e.ticker,name:e.name,
      entry:e.acquired,exit:e.disposed,daysHeld:e.daysHeld,cost:e.costBase,proceeds:e.proceeds,
      pnl:e.gain,ret:e.costBase?e.gain/e.costBase:0,discountable:e.discountable};
  }).sort(function(a,b){return a.exit-b.exit;});
}

function optimise(secs, open, cgt, account){
  var actions=[], pool=cgt.discAfter, eff=account.marginalTaxOn(1000)/1000;
  Object.keys(open).forEach(function(tk){
    var sec=secs[tk]||{name:tk,px:0,fx:1};
    open[tk].forEach(function(lot){
      if(lot.qtyOpen<=1e-9) return;
      var value=lot.qtyOpen*sec.px*sec.fx, cost=lot.qtyOpen*lot.unitCost, unreal=value-cost;
      var anniv=new Date(Date.UTC(lot.acquired.getUTCFullYear()+1,lot.acquired.getUTCMonth(),lot.acquired.getUTCDate()));
      var dtd=days(account.today,anniv);
      if(unreal<0&&pool>0){ var off=Math.min(-unreal,pool); var save=off*account.discountRate()*eff; pool-=off;
        actions.push({kind:"harvest",ticker:tk,name:sec.name,saving:save,
          detail:"Unrealised loss of "+money(unreal)+". Selling before 30 June offsets discounted gains."});
      } else if(unreal>0&&dtd>0&&dtd<=30){ var save2=unreal*account.discountRate()*eff;
        actions.push({kind:"wait",ticker:tk,name:sec.name,saving:save2,
          detail:"Crosses the 12-month line in "+dtd+" days ("+fmtD(anniv)+"). Hold past it to unlock the 50% discount on ~"+money(unreal)+"."});
      }
    });
  });
  return actions.sort(function(a,b){return b.saving-a.saving;});
}

/* ---------- pipeline ---------- */
function runPipeline(results, opt){
  opt=opt||{};
  var account=new Account(opt);
  var trades=[], stmtDivs=[], brokerDivs=[], holdings=[], review=[], unknown={};
  results.forEach(function(r){
    trades=trades.concat(r.trades);
    holdings=holdings.concat(r.holdings||[]);
    (r.broker==="statement"?stmtDivs:brokerDivs).push.apply(r.broker==="statement"?stmtDivs:brokerDivs, r.dividends);
    r.review.forEach(function(x){ review.push(Object.assign({broker:r.broker},x)); });
  });
  var dividends = stmtDivs.length ? stmtDivs.concat(brokerDivs.filter(function(d){return d.fx!==1.0;})) : brokerDivs;
  var secs={}; Object.keys(SECURITIES).forEach(function(k){secs[k]=SECURITIES[k];});
  trades.forEach(function(t){ if(!secs[t.ticker]){ secs[t.ticker]={name:t.ticker,exchange:"?",tag:"Unknown",ccy:"AUD",px:0,fx:1}; unknown[t.ticker]=1; } });
  holdings.forEach(function(h){ if(!secs[h.ticker]){ secs[h.ticker]={name:h.ticker,exchange:"?",tag:"Unknown",ccy:"AUD",px:0,fx:1}; unknown[h.ticker]=1; } });
  var m=matchParcels(secs, trades, account, opt.method||"fifo");
  var cgt=computeCGT(m.events, account);
  var income=computeIncome(dividends, account);
  var tax=estimateTax(cgt, income, account);
  // Exposure: prefer an explicit holdings export when supplied, else derive from open parcels.
  var xray = holdings.length ? exposureFromHoldings(secs, holdings) : exposureXray(secs, m.open);
  var actions=optimise(secs, m.open, cgt, account);
  return {account:account,cgt:cgt,income:income,tax:tax,xray:xray,actions:actions,
          review:review,unknown:Object.keys(unknown),nTrades:trades.length,nDiv:dividends.length,
          holdings:holdings,closedTrades:closedTradesFrom(m.events),
          open:m.open,allEvents:m.events,dividends:dividends,secs:secs,
          exposureSource:holdings.length?"holdings export":"transaction history"};
}

/* ---------- dashboard render (returns HTML string) ---------- */
function esc(s){ return (""+s).replace(/[&<>]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;"}[c];}); }
function renderDashboard(r){
  var a=r.account, cgt=r.cgt, inc=r.income;
  var made=cgt.gainsAfterLosses+inc.auCash+inc.foreignCash, save=r.actions.reduce(function(s,x){return s+x.saving;},0);
  var events=cgt.events.slice().sort(function(x,y){return (x.gain<0)-(y.gain<0) || y.gain-x.gain;});
  var fy="2025-26", today=fmtD(a.today);
  var h='';
  h+='<div class="hdrow"><div class=brand><span class=d>&#9670;</span> HoldCapital</div>'
   + '<div class="muted small">FY '+fy+' &middot; generated '+today+'</div></div><hr>';
  h+='<div class=muted>Imported <b>'+r.nTrades+'</b> trades and <b>'+r.nDiv+'</b> dividends.'
   + (r.review.length?' <b>'+r.review.length+'</b> rows flagged (below).':'')+'</div>';
  h+='<div class=cards>'
   + '<div class="kpi k-green"><div class=l>YOU MADE</div><div class=v>'+money(made)+'</div><div class=s>Realised gains + dividends</div></div>'
   + '<div class="kpi k-ore"><div class=l>YOU\'LL OWE</div><div class=v>&asymp; '+money(r.tax.netTax)+'</div><div class=s>Est. extra tax from investing</div></div>'
   + '<div class="kpi k-blue"><div class=l>YOU CAN SAVE</div><div class=v>'+money(save)+'</div><div class=s>Acting before 30 June</div></div></div>';
  h+='<h2>Exposure x-ray <span class="muted small">— what you hold now, '+money(r.xray.total)+'</span></h2><div class="card exp">';
  r.xray.tags.forEach(function(t){ var col=TAG_COLOUR[t.tag]||"#888780";
    h+='<div class=expr><div class=top><span>'+esc(t.tag)+'</span><span class=muted>'+money(t.value)+' &middot; '+(t.weight*100).toFixed(1)+'%</span></div>'
     + '<div class=bar><i style="width:'+(t.weight*100)+'%;background:'+col+'"></i></div></div>'; });
  h+='<div class="flag review" style="margin-top:6px">'+Math.round(r.xray.resourcesWeight*100)+'% of the book is in resource commodities.</div></div>';
  h+='<h2>Realised capital gains events</h2><div class=card style="padding:0;overflow:hidden"><table>'
   + '<tr><th>Holding</th><th>Acquired</th><th>Disposed</th><th class=r>Days</th><th class=r>Cost base</th><th class=r>Proceeds</th><th class=r>Gain / loss</th><th class=r>Disc.</th></tr>';
  events.forEach(function(e){ var cls=e.gain>=0?"pos":"neg", sign=e.gain>=0?"+":"";
    h+='<tr><td><b>'+esc(e.name)+'</b></td><td>'+fmtD(e.acquired)+'</td><td>'+fmtD(e.disposed)+'</td><td class=r>'+e.daysHeld+'</td>'
     + '<td class=r>'+money(e.costBase)+'</td><td class=r>'+money(e.proceeds)+'</td>'
     + '<td class="r '+cls+'">'+sign+money(e.gain)+'</td><td class=r>'+(e.discountable?"50%":(e.gain<0?"n/a":"—"))+'</td></tr>'; });
  h+='</table></div>';
  h+='<h2>How the net capital gain is worked out</h2><div class=card style="padding:0;overflow:hidden"><table>'
   + '<tr><td>Total capital gains (gross)</td><td class=r>'+money(cgt.grossGains)+'</td></tr>'
   + '<tr><td>Less capital losses</td><td class=r>'+money(-cgt.losses)+'</td></tr>'
   + '<tr><td>Gains after losses</td><td class=r>'+money(cgt.gainsAfterLosses)+'</td></tr>'
   + '<tr><td>Less '+Math.round(a.discountRate()*100)+'% CGT discount</td><td class=r>'+money(-cgt.discount)+'</td></tr>'
   + '<tr><td><b>Net capital gain</b></td><td class=r><b>'+money(cgt.netCapitalGain)+'</b></td></tr></table></div>';
  h+='<h2>Dividend income &amp; franking</h2><div class=card style="padding:0;overflow:hidden"><table>'
   + '<tr><td>Australian dividends (cash)</td><td class=r>'+money(inc.auCash)+'</td></tr>'
   + '<tr><td>Franking credits</td><td class=r>'+money(inc.franking)+'</td></tr>'
   + '<tr><td>Foreign dividends (AUD)</td><td class=r>'+money(inc.foreignCash)+'</td></tr>'
   + '<tr><td>Foreign income tax offset</td><td class=r>'+money(inc.fito)+'</td></tr></table></div>';
  if(r.actions.length){ h+='<h2>Actions before 30 June</h2>';
    r.actions.forEach(function(x){ var title=x.kind==="harvest"?("Harvest the "+x.name+" loss"):("Hold "+x.name+" past the 12-month line");
      h+='<div class="act '+x.kind+'"><div style="display:flex;justify-content:space-between"><span class=h>'+esc(title)+'</span>'
       + '<span class=h>save &asymp; '+money(x.saving)+'</span></div><div class="small muted">'+esc(x.detail)+'</div></div>'; }); }
  if(r.review.length){ h+='<h2>Rows flagged for review</h2><div class=card>';
    r.review.forEach(function(x){ h+='<div class="flag '+(x.severity||"review")+'"><b>'+esc(x.broker)+'</b> &middot; '+esc(x.reason)+'</div>'; });
    if(r.unknown.length) h+='<div class="flag review">Unknown tickers (no price/sector on file): '+esc(r.unknown.join(", "))+'</div>';
    h+='</div>'; }
  h+='<div class=bottom><span>Estimated net tax after offsets &amp; the actions above</span><span class=v>&asymp; '+money(r.tax.netTax-save)+'</span></div>';
  return h;
}

/* ---------- shared UI atoms (self-contained inline styles) ---------- */
var AV_COLOURS=["#378ADD","#D85A30","#1D9E75","#7F77DD","#EF9F27","#D4537E","#0F6E56","#534AB7","#185FA5","#BA7517"];
var LOGO_EXCH={ASX:"AU",NASDAQ:"US",NYSE:"US"};   // EODHD logo country code by exchange
function avatar(t){
  t=(""+(t||"?")); var h=0; for(var i=0;i<t.length;i++) h=(h*31+t.charCodeAt(i))>>>0;
  var c=AV_COLOURS[h%AV_COLOURS.length];
  var sec=SECURITIES[t], code=sec?LOGO_EXCH[sec.exchange]:null;
  // Real company logo from EODHD's 40k logo CDN (ASX + US); falls back to the
  // coloured initials underneath when the logo 404s (crypto, metals, obscure tickers).
  var img = code ? '<img src="https://eodhd.com/img/logos/'+code+'/'+t+'.png" loading="lazy" onerror="this.remove()" style="position:absolute;inset:0;width:100%;height:100%;border-radius:50%;object-fit:contain;background:#fff">' : '';
  return '<span style="position:relative;display:inline-flex;align-items:center;justify-content:center;width:26px;height:26px;border-radius:50%;background:'+c+'26;color:'+c+';font-size:10px;font-weight:700;flex-shrink:0;overflow:hidden;letter-spacing:-.02em">'+t.slice(0,2).toUpperCase()+img+'</span>';
}
function chgPill(p){ var pos=p>=0,c=pos?"#36b37e":"#e5675f";
  var v=(typeof p==="number")?((p%1===0)?p:p.toFixed(1)):p;
  return '<span style="background:'+c+'26;color:'+c+';padding:2px 8px;border-radius:7px;font-size:12px;font-weight:600;white-space:nowrap">'+(pos?"+":"")+v+'%</span>';
}
function statusPill(kind){ var m={win:["#36b37e","WIN"],loss:["#e5675f","LOSS"],open:["#8a93a0","OPEN"],flat:["#8a93a0","FLAT"]}; var x=m[kind]||m.open;
  return '<span style="display:inline-flex;align-items:center;gap:5px;font-size:11px;font-weight:700;color:'+x[0]+'"><span style="width:7px;height:7px;border-radius:50%;background:'+x[0]+'"></span>'+x[1]+'</span>';
}

var HC={SECURITIES:SECURITIES,importText:importText,runPipeline:runPipeline,renderDashboard:renderDashboard,
        Account:Account,matchParcels:matchParcels,computeCGT:computeCGT,money:money,
        avatar:avatar,chgPill:chgPill,statusPill:statusPill};
if(typeof module!=="undefined"&&module.exports) module.exports=HC;
root.HC=HC;
})(typeof window!=="undefined"?window:(typeof globalThis!=="undefined"?globalThis:this));
