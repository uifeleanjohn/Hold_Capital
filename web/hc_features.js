/* HoldCapital — performance tab + screener + shared stock universe.
   The universe is STATIC SAMPLE data (prices/metrics are illustrative). A live
   build would pull these from a market-data feed. */
(function (root) {
"use strict";
var HC = root.HC || {};
var money = HC.money;

/* ticker, name, exchange, sector/commodity tag, ccy, price, fx, mktCap($b), P/E, divYield%, 1yr% */
var U = [
  ["BHP","BHP Group","ASX","Iron ore","AUD",57.0,1.0,210,11.5,5.2,-8],
  ["RIO","Rio Tinto","ASX","Iron ore","AUD",118.0,1.0,44,9.8,6.1,-5],
  ["FMG","Fortescue","ASX","Iron ore","AUD",21.0,1.0,55,7.5,9.0,-20],
  ["MIN","Mineral Resources","ASX","Lithium","AUD",35.0,1.0,7,12,3.0,-40],
  ["PLS","Pilbara Minerals","ASX","Lithium","AUD",2.30,1.0,8.5,20,1.0,-35],
  ["IGO","IGO Ltd","ASX","Lithium","AUD",5.2,1.0,4,18,4.0,-25],
  ["LYC","Lynas Rare Earths","ASX","Rare earths","AUD",7.5,1.0,7,30,0,15],
  ["S32","South32","ASX","Diversified","AUD",3.4,1.0,15,14,4.5,5],
  ["NST","Northern Star","ASX","Gold","AUD",16.5,1.0,19,22,1.5,30],
  ["DEG","De Grey Mining","ASX","Gold","AUD",1.62,1.0,3.8,0,0,40],
  ["BOE","Boss Energy","ASX","Uranium","AUD",4.20,1.0,1.7,0,0,-10],
  ["PDN","Paladin Energy","ASX","Uranium","AUD",9.0,1.0,2.7,35,0,20],
  ["SFR","Sandfire Resources","ASX","Copper","AUD",11.0,1.0,5,28,1.0,35],
  ["WDS","Woodside Energy","ASX","Energy","AUD",24.0,1.0,46,9,7.5,-12],
  ["STO","Santos","ASX","Energy","AUD",7.5,1.0,24,12,4.0,0],
  ["CSL","CSL Limited","ASX","AU Healthcare","AUD",250.0,1.0,120,30,1.5,-5],
  ["CBA","Commonwealth Bank","ASX","AU Financials","AUD",130.0,1.0,220,22,3.5,25],
  ["WES","Wesfarmers","ASX","AU Consumer","AUD",75.0,1.0,85,32,2.5,18],
  ["WTC","WiseTech Global","ASX","AU Tech","AUD",120.0,1.0,40,90,0.3,40],
  ["XRO","Xero","ASX","AU Tech","AUD",170.0,1.0,26,120,0,35],
  ["TLS","Telstra","ASX","AU Telco","AUD",4.0,1.0,46,22,4.5,8],
  ["NVDA","NVIDIA","NASDAQ","US Tech","USD",175.0,1.52,4300,55,0.02,80],
  ["MSFT","Microsoft","NASDAQ","US Tech","USD",480.0,1.52,3600,36,0.7,20],
  ["AAPL","Apple","NASDAQ","US Tech","USD",230.0,1.52,3500,33,0.5,12],
  ["GOOGL","Alphabet","NASDAQ","US Tech","USD",200.0,1.52,2400,26,0.5,30],
  ["AMZN","Amazon","NASDAQ","US Tech","USD",220.0,1.52,2300,42,0,25],
  ["META","Meta Platforms","NASDAQ","US Tech","USD",700.0,1.52,1800,28,0.3,45],
  ["TSLA","Tesla","NASDAQ","US Tech","USD",340.0,1.52,1100,90,0,-10],
  ["AMD","AMD","NASDAQ","US Tech","USD",170.0,1.52,280,45,0,15],
  ["MRNA","Moderna","NASDAQ","US Pharma","USD",70.0,1.52,27,0,0,-45],
  ["PFE","Pfizer","NYSE","US Pharma","USD",26.0,1.52,150,11,6.0,-8],
  ["LLY","Eli Lilly","NYSE","US Pharma","USD",820.0,1.52,780,60,0.6,22],
  ["BTC","Bitcoin","CRYPTO","Crypto","AUD",165000,1.0,2200,0,0,60],
  ["ETH","Ethereum","CRYPTO","Crypto","AUD",5500,1.0,650,0,0,40],
  ["SOL","Solana","CRYPTO","Crypto","AUD",320,1.0,150,0,0,80],
  ["XRP","XRP","CRYPTO","Crypto","AUD",3.2,1.0,180,0,0,120],
  ["BNB","BNB","CRYPTO","Crypto","AUD",1100,1.0,160,0,0,30],
  ["ADA","Cardano","CRYPTO","Crypto","AUD",1.5,1.0,50,0,0,20],
  ["DOGE","Dogecoin","CRYPTO","Crypto","AUD",0.55,1.0,80,0,0,25],
  ["LINK","Chainlink","CRYPTO","Crypto","AUD",35,1.0,22,0,0,35],
  ["XAU","Gold (per oz)","METAL","Precious metals","AUD",4200,1.0,0,0,0,28],
  ["XAG","Silver (per oz)","METAL","Precious metals","AUD",52,1.0,0,0,0,35],
  ["XPT","Platinum (per oz)","METAL","Precious metals","AUD",1800,1.0,0,0,0,10]
];
var UNIVERSE = U.map(function(r){ return {ticker:r[0],name:r[1],exchange:r[2],tag:r[3],ccy:r[4],
  px:r[5],fx:r[6],mcap:r[7],pe:r[8],dy:r[9],ret1y:r[10]}; });
var SECTORS = UNIVERSE.map(function(u){return u.tag;}).filter(function(v,i,a){return a.indexOf(v)===i;}).sort();

/* make the engine aware of every universe ticker (don't overwrite existing) */
HC.SECURITIES = HC.SECURITIES || {};
UNIVERSE.forEach(function(u){ if(!HC.SECURITIES[u.ticker])
  HC.SECURITIES[u.ticker]={name:u.name,exchange:u.exchange,tag:u.tag,ccy:u.ccy,px:u.px,fx:u.fx}; });

function esc(s){ return (""+s).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];}); }

/* ---------------- Performance ---------------- */
function computePerformance(result){
  var secs=result.secs, open=result.open, events=result.allEvents, divs=result.dividends;
  var rows={};
  function row(tk){ if(!rows[tk]){ var s=secs[tk]||{name:tk}; rows[tk]={ticker:tk,name:s.name||tk,qty:0,cost:0,value:0,realised:0,income:0}; } return rows[tk]; }
  Object.keys(open).forEach(function(tk){ var s=secs[tk]||{px:0,fx:1};
    open[tk].forEach(function(l){ var r=row(tk); r.qty+=l.qtyOpen; r.cost+=l.qtyOpen*l.unitCost; r.value+=l.qtyOpen*(s.px||0)*(s.fx||1); }); });
  events.forEach(function(e){ row(e.ticker).realised+=e.gain; });
  divs.forEach(function(d){ row(d.ticker).income+=d.cash*d.fx; });
  var list=Object.keys(rows).map(function(k){ var r=rows[k];
    r.unreal=r.value-r.cost; r.unrealPct=r.cost?r.unreal/r.cost:0; r.total=r.unreal+r.realised+r.income; return r; })
    .sort(function(a,b){return b.value-a.value || b.total-a.total;});
  var portfolioValue=list.reduce(function(s,r){return s+r.value;},0);
  var totalUnreal=list.reduce(function(s,r){return s+r.unreal;},0);
  var totalRealised=list.reduce(function(s,r){return s+r.realised;},0);
  var totalIncome=list.reduce(function(s,r){return s+r.income;},0);
  var deployed=list.reduce(function(s,r){return s+r.cost;},0)+events.reduce(function(s,e){return s+e.costBase;},0);
  var totalReturn=totalUnreal+totalRealised+totalIncome;
  return {rows:list,portfolioValue:portfolioValue,totalUnreal:totalUnreal,totalRealised:totalRealised,
    totalIncome:totalIncome,totalReturn:totalReturn,returnPct:deployed?totalReturn/deployed:0};
}
function renderPerformance(result){
  var p=computePerformance(result);
  var rc=p.totalReturn>=0?"pos":"neg", retCls=p.totalReturn>=0?"k-green":"k-ore";
  var h='<h2 style="margin-top:6px">Performance</h2>';
  h+='<div class=muted style="margin-bottom:8px">All-time, across realised gains, open positions and dividend income.</div>';
  h+='<div class=cards>'
   + '<div class="kpi k-blue"><div class=l>PORTFOLIO VALUE</div><div class=v>'+money(p.portfolioValue)+'</div><div class=s>open positions at last price</div></div>'
   + '<div class="kpi '+retCls+'"><div class=l>TOTAL RETURN</div><div class=v>'+(p.totalReturn>=0?"+":"")+money(p.totalReturn)+'</div><div class=s>'+(p.returnPct*100).toFixed(1)+'% on capital deployed</div></div>'
   + '<div class="kpi" style="background:var(--panel)"><div class=l style="color:var(--slate)">DIVIDEND INCOME</div><div class=v>'+money(p.totalIncome)+'</div><div class=s>cash received</div></div></div>';
  h+='<div class=cards style="grid-template-columns:repeat(2,1fr)">'
   + '<div class="kpi" style="background:var(--panel)"><div class=l style="color:var(--slate)">UNREALISED</div><div class=v class="'+(p.totalUnreal>=0?"pos":"neg")+'">'+(p.totalUnreal>=0?"+":"")+money(p.totalUnreal)+'</div></div>'
   + '<div class="kpi" style="background:var(--panel)"><div class=l style="color:var(--slate)">REALISED</div><div class=v>'+(p.totalRealised>=0?"+":"")+money(p.totalRealised)+'</div></div></div>';
  h+='<h2>By holding</h2><div class=card style="padding:0;overflow:hidden"><table>'
   + '<tr><th>Holding</th><th class=r>Qty held</th><th class=r>Value</th><th class=r>Unrealised</th><th class=r>%</th><th class=r>Realised</th><th class=r>Income</th><th class=r>Total</th></tr>';
  p.rows.forEach(function(r){
    var uc=r.unreal>=0?"pos":"neg", tc=r.total>=0?"pos":"neg";
    h+='<tr><td><b>'+esc(r.name)+'</b></td><td class=r>'+(r.qty?Math.round(r.qty).toLocaleString():"—")+'</td>'
     + '<td class=r>'+(r.value?money(r.value):"—")+'</td>'
     + '<td class="r '+uc+'">'+(r.qty?((r.unreal>=0?"+":"")+money(r.unreal)):"—")+'</td>'
     + '<td class="r '+uc+'">'+(r.qty&&r.cost?((r.unrealPct>=0?"+":"")+(r.unrealPct*100).toFixed(1)+"%"):"—")+'</td>'
     + '<td class=r>'+(r.realised?((r.realised>=0?"+":"")+money(r.realised)):"—")+'</td>'
     + '<td class=r>'+(r.income?money(r.income):"—")+'</td>'
     + '<td class="r '+tc+'"><b>'+(r.total>=0?"+":"")+money(r.total)+'</b></td></tr>';
  });
  h+='</table></div>';
  h+='<p class=muted style="font-size:12px;margin-top:8px">Current prices are static sample values; a live build refreshes them from a market feed. “Total return” = unrealised + realised + income.</p>';
  return h;
}

/* ---------------- Screener ---------------- */
function screen(f){
  return UNIVERSE.filter(function(u){
    if(f.market==="ASX" && u.exchange!=="ASX") return false;
    if(f.market==="US" && !(u.exchange==="NASDAQ"||u.exchange==="NYSE")) return false;
    if(f.market==="Crypto" && u.exchange!=="CRYPTO") return false;
    if(f.market==="Metals" && u.exchange!=="METAL") return false;
    if(f.sector&&f.sector!=="all"&&u.tag!==f.sector) return false;
    if(f.maxPE&&u.pe>0&&u.pe>f.maxPE) return false;
    if(f.minDY&&u.dy<f.minDY) return false;
    if(f.minMcap&&u.mcap<f.minMcap) return false;
    if(f.q){ var q=f.q.toLowerCase(); if(u.ticker.toLowerCase().indexOf(q)<0&&u.name.toLowerCase().indexOf(q)<0) return false; }
    return true;
  }).sort(function(a,b){ var k=f.sortKey||"mcap", d=f.sortDir==="asc"?1:-1;
    if(k==="ticker"||k==="name"||k==="tag") return d*(""+a[k]).localeCompare(""+b[k]);
    return d*((a[k]||0)-(b[k]||0)); });
}
function screenRows(f){
  var rows=screen(f);
  if(!rows.length) return '<tr><td colspan=8 class=muted style="padding:14px">No matches.</td></tr>';
  return rows.map(function(u){ var rc=u.ret1y>=0?"pos":"neg";
    return '<tr><td><b>'+u.ticker+'</b></td><td>'+esc(u.name)+'</td><td>'+u.exchange+'</td><td>'+esc(u.tag)+'</td>'
     + '<td class=r>'+(u.ccy==="USD"?"US$":"$")+u.px.toFixed(2)+'</td>'
     + '<td class=r>$'+u.mcap+'b</td><td class=r>'+(u.pe>0?u.pe.toFixed(1):"—")+'</td>'
     + '<td class=r>'+(u.dy>0?u.dy.toFixed(1)+"%":"—")+'</td>'
     + '<td class="r '+rc+'">'+(u.ret1y>=0?"+":"")+u.ret1y+'%</td></tr>'; }).join("");
}
function renderScreenerShell(){
  var secOpts='<option value=all>All sectors</option>'+SECTORS.map(function(s){return '<option value="'+esc(s)+'">'+esc(s)+'</option>';}).join("");
  var cols=[["ticker","Ticker"],["name","Name"],["exchange","Exch"],["tag","Sector"],["px","Price"],["mcap","Mkt cap"],["pe","P/E"],["dy","Yield"],["ret1y","1yr"]];
  var head=cols.map(function(c,i){ var cls=(i>=4)?" class=r":"";
    return '<th'+cls+' style="cursor:pointer" onclick="sortScreen(\''+c[0]+'\')">'+c[1]+'</th>'; }).join("");
  var h='<h2 style="margin-top:6px">Screener</h2>';
  h+='<div class=muted style="margin-bottom:8px">Filter a built-in ASX + US watchlist. Click a column to sort.</div>';
  h+='<div class=card><div class=row>'
   + '<div><label class=fld style="margin-top:0">Market</label><select id=scr-market onchange=applyScreen()><option value=all>All</option><option>ASX</option><option>US</option><option>Crypto</option><option>Metals</option></select></div>'
   + '<div><label class=fld style="margin-top:0">Sector</label><select id=scr-sector onchange=applyScreen()>'+secOpts+'</select></div>'
   + '<div><label class=fld style="margin-top:0">Max P/E</label><input id=scr-pe type=number placeholder="any" style="width:90px" oninput=applyScreen()></div>'
   + '<div><label class=fld style="margin-top:0">Min yield %</label><input id=scr-dy type=number placeholder="any" style="width:90px" oninput=applyScreen()></div>'
   + '<div><label class=fld style="margin-top:0">Min mkt cap $b</label><input id=scr-mc type=number placeholder="any" style="width:110px" oninput=applyScreen()></div>'
   + '<div><label class=fld style="margin-top:0">Search</label><input id=scr-q placeholder="ticker / name" oninput=applyScreen()></div>'
   + '</div></div>';
  h+='<div class=card style="padding:0;overflow-x:auto"><table style="min-width:720px"><thead><tr>'+head+'</tr></thead><tbody id=scr-body>'+screenRows({sortKey:"mcap",sortDir:"desc"})+'</tbody></table></div>';
  h+='<p class=muted style="font-size:12px;margin-top:8px">Static sample universe of '+UNIVERSE.length+' stocks. A live screener pulls prices and fundamentals from a market-data feed.</p>';
  return h;
}

HC.UNIVERSE=UNIVERSE; HC.SECTORS=SECTORS; HC.screen=screen; HC.screenRows=screenRows;
HC.renderScreenerShell=renderScreenerShell; HC.computePerformance=computePerformance; HC.renderPerformance=renderPerformance;
if(typeof module!=="undefined"&&module.exports) module.exports=HC;
root.HC=HC;
})(typeof window!=="undefined"?window:(typeof globalThis!=="undefined"?globalThis:this));
