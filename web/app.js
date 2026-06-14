/* Connected HoldCapital app: auth gate + loads portfolio/prices from the API,
   then runs the SAME client engine to render every tab. */
function $(id){ return document.getElementById(id); }
var CUR = { trades: [], divs: [], me: null, ann: {}, method: "fifo" };
var SCREEN = { sortKey: "mcap", sortDir: "desc" };

/* ---- auth ---- */
async function doAuth(kind){
  var email = $("au-email").value.trim(), pw = $("au-pw").value;
  if(!email || !pw){ $("au-msg").textContent = "Enter email and password."; return; }
  try{
    var res = await (kind === "signup" ? API.signup(email, pw) : API.login(email, pw));
    API.setToken(res.token); await loadApp();
  }catch(e){ $("au-msg").textContent = "Could not " + kind + ". " + String(e).slice(0,120); }
}
function logout(){ API.setToken(null); show("login"); }

/* ---- data load + render ---- */
async function loadApp(){
  try{
    CUR.me = await API.me();
  }catch(e){ API.setToken(null); show("login"); return; }
  try{ await API.refreshPrices(); }catch(e){}
  var prices = [], pf = { trades: [], dividends: [] };
  try{ prices = await API.prices(); }catch(e){}
  try{ pf = await API.portfolio(); }catch(e){}
  prices.forEach(function(p){
    var s = HC.SECURITIES[p.ticker] || { name: p.ticker, exchange: "?", tag: "Unknown", ccy: p.currency };
    s.px = p.price; s.fx = p.fx; HC.SECURITIES[p.ticker] = s;
  });
  CUR.trades = pf.trades.map(function(t){ return { date: new Date(t.date + "T00:00:00Z"), ticker: t.ticker,
    action: t.action, qty: t.qty, price: t.price, brokerage: t.brokerage || 0, fx: t.fx || 1, account: t.account || "Default" }; });
  CUR.divs = pf.dividends.map(function(d){ var o = { date: new Date(d.date + "T00:00:00Z"), ticker: d.ticker,
    cash: d.cash, franking: d.franking || 0, withholding: d.withholding || 0, fx: d.fx || 1, account: d.account || "Default" };
    if(d.franking_credit != null) o.franking_credit = d.franking_credit; return o; });
  try{ fillPortfolios(await API.portfolios()); }catch(e){}
  try{ var notes = await API.journal(); CUR.ann = {};
    notes.forEach(function(n){ CUR.ann[n.trade_key] = {setup:n.setup, confidence:n.confidence, notes:n.notes}; });
  }catch(e){ CUR.ann = {}; }
  $("topbar-email").textContent = CUR.me.email;
  $("tier-badge").textContent = CUR.me.tier;
  try{
    var inb = await API.inboxAddress();
    $("inbox-addr").textContent = inb.address;
    $("inbox-recent").textContent = inb.recent.length
      ? (inb.recent.length + " trade(s) auto-imported recently.") : "No auto-imported trades yet.";
  }catch(e){ $("inbox-addr").textContent = "(unavailable)"; }
  try{ var bs = await API.brokerStatus();
    $("broker-status").textContent = bs.connected ? "broker connected" : (bs.stub_mode ? "(demo mode)" : "");
  }catch(e){}
  if($("income")) $("income").value = CUR.me.other_income ? String(CUR.me.other_income) : "flat";
  show("app"); render();
}

function selectedAccount(){ return $("acct-filter") ? $("acct-filter").value : "__all__"; }
function buildResult(){
  var opt = { method: $("optimise") && $("optimise").checked ? "min_tax" : "fifo" };
  var inc = $("income") ? $("income").value : "flat";
  if(inc === "flat") opt.marginalRate = 0.37; else opt.otherIncome = parseFloat(inc);
  var acc = selectedAccount();
  var trades = acc === "__all__" ? CUR.trades : CUR.trades.filter(function(t){ return t.account === acc; });
  var divs   = acc === "__all__" ? CUR.divs   : CUR.divs.filter(function(d){ return d.account === acc; });
  var res = { broker: "server", trades: trades, dividends: divs, holdings: [], review: [] };
  return HC.runPipeline([res], opt);
}
function onAccountFilter(){
  var a = selectedAccount();
  if(a !== "__all__"){ if($("m-account")) $("m-account").value = a; if($("imp-account")) $("imp-account").value = a; }
  render();
}
function pfOpt(a){ return '<option>'+a+'</option>'; }
function fillPortfolios(list){
  if(!list || !list.length) list = ["Default"];
  var f=$("acct-filter");
  if(f){ var cf=f.value; f.innerHTML='<option value="__all__">All accounts</option>'+list.map(pfOpt).join("");
    f.value = (cf==="__all__"||list.indexOf(cf)>=0)?cf:"__all__"; }
  ["m-account","imp-account"].forEach(function(id){ var s=$(id); if(!s) return; var cv=s.value;
    s.innerHTML=list.map(pfOpt).join("");
    s.value = list.indexOf(cv)>=0 ? cv : (list.indexOf("Default")>=0?"Default":list[0]); });
  var L=$("portfolio-list");
  if(L) L.innerHTML=list.map(function(a){ return '<span class="pill" style="margin:0 5px 5px 0;display:inline-block">'+a+'</span>'; }).join("");
}
async function createPortfolio(){
  var n=($("new-portfolio").value||"").trim(); if(!n) return;
  try{ var res=await API.createPortfolio(n); $("new-portfolio").value="";
    fillPortfolios(res.portfolios || await API.portfolios());
    if($("m-account")) $("m-account").value=n;
  }catch(e){ alert("Could not create portfolio: "+String(e).slice(0,100)); }
}
function render(){
  if(!CUR.trades.length){ $("dash").innerHTML = '<div class=card style="text-align:center;padding:30px">'
    + '<p class=muted>No holdings yet. Add a trade or import a CSV above to see your dashboard.</p></div>';
    $("perf").innerHTML = $("journal").innerHTML = ""; $("screener").innerHTML = HC.renderScreenerShell(); return; }
  var r = buildResult();
  $("dash").innerHTML = HC.renderDashboard(r);
  $("perf").innerHTML = HC.renderPerformance(r);
  $("journal").innerHTML = renderPositions() + HC.renderJournal(r.closedTrades, CUR.ann); wireJournal();
  $("screener").innerHTML = HC.renderScreenerShell();
}

/* ---- journal annotations (per user, local) ---- */
function wireJournal(){
  [].forEach.call(document.querySelectorAll(".jin"), function(el){
    el.addEventListener("change", function(){
      var k = el.getAttribute("data-k"), f = el.getAttribute("data-f"), v = el.value;
      CUR.ann[k] = CUR.ann[k] || {};
      if(v === "") delete CUR.ann[k][f]; else CUR.ann[k][f] = f === "confidence" ? parseInt(v,10) : v;
      var a = CUR.ann[k];
      API.saveNote({trade_key:k, setup:a.setup||null, confidence:a.confidence||null, notes:a.notes||null}).catch(function(){});
      $("journal").innerHTML = HC.renderJournal(buildResult().closedTrades, CUR.ann); wireJournal();
    });
  });
}

/* ---- open positions (parcels) + inline add/close ---- */
var POSLIST = [];
function pesc(s){ return (""+s).replace(/[&<>]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;"}[c];}); }
function pround(n){ return Math.round(n).toLocaleString(); }
function pprice(n){ if(!n) return "—"; var dp = Math.abs(n) >= 1 ? 2 : 4;
  return "$" + n.toLocaleString("en-AU",{minimumFractionDigits:dp, maximumFractionDigits:dp}); }
function pdate(d){ var m=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  return d.getUTCDate()+" "+m[d.getUTCMonth()]+" "+(""+d.getUTCFullYear()).slice(2); }
function renderPositions(){
  POSLIST = [];
  var secs = HC.SECURITIES, M = HC.money;
  var method = $("optimise") && $("optimise").checked ? "min_tax" : "fifo";
  var acc = selectedAccount();
  var names = {}; CUR.trades.forEach(function(t){ names[t.account||"Default"]=1; });
  var list = Object.keys(names).sort();
  if(acc !== "__all__") list = [acc];
  if(!list.length) return "";
  var html = '<h2 style="margin-top:6px">Open positions</h2>';
  list.forEach(function(name){
    var trades = CUR.trades.filter(function(t){ return (t.account||"Default")===name; });
    var m = HC.matchParcels(secs, trades, new HC.Account({}), method);
    var tickers = Object.keys(m.open).filter(function(tk){ return m.open[tk].some(function(l){return l.qtyOpen>1e-9;}); });
    var rows = tickers.map(function(tk){
      var lots = m.open[tk].filter(function(l){return l.qtyOpen>1e-9;});
      var qty = lots.reduce(function(s,l){return s+l.qtyOpen;},0);
      var cost = lots.reduce(function(s,l){return s+l.qtyOpen*l.unitCost;},0);
      var sec = secs[tk] || {px:0,fx:1,name:tk};
      var last=(sec.px||0)*(sec.fx||1);
      return {tk:tk, sec:sec, lots:lots, qty:qty, cost:cost, last:last, value:qty*last, avg:cost/qty, unreal:qty*last-cost};
    });
    var totV=rows.reduce(function(s,r){return s+r.value;},0), totU=rows.reduce(function(s,r){return s+r.unreal;},0);
    var sc=totU>=0?"pos":"neg";
    html += '<div class="card"><div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:10px">'
      + '<h3 style="margin:0">'+pesc(name)+'</h3>'
      + (totV ? '<span class="muted small">'+M(totV)+' · <span class="'+sc+'">'+(totU>=0?"+":"")+M(totU)+'</span></span>' : '') + '</div>';
    if(!rows.length){ html += '<p class="muted small">No open positions in this portfolio.</p></div>'; return; }
    html += '<table><tr><th>Holding</th><th class=r>Qty</th><th class=r>Avg fill</th><th class=r>Last</th><th class=r>Value</th><th class=r>Unrealised</th><th></th></tr>';
    rows.forEach(function(r){
      var tk=r.tk, sec=r.sec, lots=r.lots;
      var i = POSLIST.length; POSLIST.push({ticker:tk, account:name});
      var uc = r.unreal>=0 ? "pos" : "neg", upct = r.cost ? r.unreal/r.cost*100 : 0;
      html += '<tr><td><div style="display:flex;align-items:center;gap:9px">'+(HC.avatar?HC.avatar(tk):'')+'<div><b>'+pesc(sec.name||tk)+'</b><div class="muted" style="font-size:11px">'+tk+'</div></div></div></td>'
        + '<td class=r>'+pround(r.qty)+'</td><td class=r>'+pprice(r.avg)+'</td><td class=r>'+pprice(r.last)+'</td>'
        + '<td class=r>'+(r.value?M(r.value):"—")+'</td>'
        + '<td class="r '+uc+'">'+(r.value?((r.unreal>=0?"+":"")+M(r.unreal)+' <span style="font-weight:400;font-size:11px">('+(upct>=0?"+":"")+upct.toFixed(1)+'%)</span>'):"—")+'</td>'
        + '<td class=r><button class="btn ghost sm" onclick="togglePosForm('+i+')">Add / close</button></td></tr>';
      html += '<tr><td colspan=7 style="border-top:0;padding-top:0;padding-bottom:14px">'
        + '<div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center"><span class="muted" style="font-size:10.5px;text-transform:uppercase;letter-spacing:.04em;margin-right:2px">Parcels</span>'
        + lots.map(function(l){return '<span style="background:var(--surface2);border:1px solid var(--border);border-radius:7px;padding:3px 9px;font-size:12px;color:var(--text2)"><b style="color:var(--text)">'+pround(l.qtyOpen)+'</b> @ '+pprice(l.unitCost)+' · '+pdate(l.acquired)+'</span>';}).join("")+'</div>'
        + '<div id="pf-'+i+'" style="display:none;margin-top:10px">'
        + '<select id="pf-'+i+'-side"><option>BUY</option><option>SELL</option></select> '
        + '<input id="pf-'+i+'-qty" type="number" placeholder="qty" style="width:80px"> '
        + '<input id="pf-'+i+'-price" type="number" placeholder="price" style="width:90px"> '
        + '<input id="pf-'+i+'-date" type="date" style="width:150px"> '
        + '<button class="btn sm" onclick="submitPos('+i+')">Save</button>'
        + '<span class="muted small" style="margin-left:8px">BUY adds · SELL closes/trims</span></div></td></tr>';
    });
    html += '</table></div>';
  });
  html += '<h2>Closed trades</h2>';
  return html;
}
function togglePosForm(i){ var f=$("pf-"+i); if(!f) return;
  f.style.display = f.style.display==="none" ? "block" : "none";
  if(f.style.display==="block" && !$("pf-"+i+"-date").value) $("pf-"+i+"-date").value = new Date().toISOString().slice(0,10);
}
async function submitPos(i){
  var p = POSLIST[i]; if(!p) return;
  var side=$("pf-"+i+"-side").value, qty=parseFloat($("pf-"+i+"-qty").value), price=parseFloat($("pf-"+i+"-price").value), d=$("pf-"+i+"-date").value;
  if(!(qty>0)||!(price>=0)||!d){ alert("Enter quantity, price and date."); return; }
  var fx=(HC.SECURITIES[p.ticker]&&HC.SECURITIES[p.ticker].fx)||1.0;
  try{ await API.addTrade({date:d,ticker:p.ticker,action:side,qty:qty,price:price,brokerage:0,fx:fx,account:p.account}); await loadApp(); }
  catch(e){ alert("Could not save: "+String(e).slice(0,100)); }
}

/* ---- screener ---- */
function screenFilters(){ return { market:$("scr-market").value, sector:$("scr-sector").value,
  maxPE:parseFloat($("scr-pe").value)||0, minDY:parseFloat($("scr-dy").value)||0,
  minMcap:parseFloat($("scr-mc").value)||0, q:$("scr-q").value, sortKey:SCREEN.sortKey, sortDir:SCREEN.sortDir }; }
function applyScreen(){ $("scr-body").innerHTML = HC.screenRows(screenFilters()); }
function sortScreen(k){ if(SCREEN.sortKey===k) SCREEN.sortDir = SCREEN.sortDir==="asc"?"desc":"asc"; else { SCREEN.sortKey=k; SCREEN.sortDir="desc"; } applyScreen(); }

/* ---- tabs (sidebar nav) ---- */
var TABS = { dash:"dash", perf:"perf", journal:"journal", screener:"screener", add:"panel" };
var TITLES = { dash:"Tax & exposure", perf:"Performance", journal:"Journal", screener:"Screener", add:"Add / import" };
function showTab(which){
  Object.keys(TABS).forEach(function(k){
    $(TABS[k]).style.display = k===which ? "block" : "none";
    $("tab-"+k).className = k===which ? "active" : "";
  });
  if($("page-title")) $("page-title").textContent = TITLES[which];
}
function togglePanel(){ var p=$("panel"); p.style.display = p.style.display==="none" ? "block" : "none"; }

/* ---- theme ---- */
function initTheme(){ var t=localStorage.getItem("hc_theme")||"dark"; document.documentElement.dataset.theme=t; themeBtn(t); }
function toggleTheme(){ var t=document.documentElement.dataset.theme==="dark"?"light":"dark";
  document.documentElement.dataset.theme=t; localStorage.setItem("hc_theme",t); themeBtn(t); }
function themeBtn(t){ var b=$("theme-btn"); if(b) b.textContent = t==="dark" ? "Light" : "Dark"; }

/* ---- ticker tape ---- */
var TICKER=[
  {s:"BHP",p:"$41.50",c:-0.8},{s:"CBA",p:"$130.00",c:0.5},{s:"CSL",p:"$250.00",c:-0.4},
  {s:"FMG",p:"$21.00",c:-2.1},{s:"RIO",p:"$118.00",c:-0.6},{s:"WDS",p:"$24.00",c:0.9},
  {s:"WES",p:"$75.00",c:1.1},{s:"NST",p:"$16.50",c:1.4},
  {s:"NVDA",p:"US$175.00",c:2.4},{s:"AAPL",p:"US$230.00",c:0.6},{s:"MSFT",p:"US$480.00",c:0.9},
  {s:"TSLA",p:"US$340.00",c:-1.8},{s:"META",p:"US$700.00",c:1.5},{s:"GOOGL",p:"US$200.00",c:0.8},
  {s:"BTC",p:"$165,000",c:3.1},{s:"ETH",p:"$5,500",c:2.2},{s:"SOL",p:"$320",c:4.5},{s:"XRP",p:"$3.20",c:-1.2},
  {s:"Gold",p:"$4,200/oz",c:0.4},{s:"Silver",p:"$52/oz",c:0.9}
];
function buildTicker(){
  var html=TICKER.map(function(t){ var cls=t.c>=0?"pos":"neg";
    return '<span class="tk"><b>'+t.s+'</b> <span class="px">'+t.p+'</span> <span class="'+cls+'">'+(t.c>=0?"+":"")+t.c.toFixed(1)+'%</span></span>';
  }).join("");
  if($("ticker-track")) $("ticker-track").innerHTML = html + html;   // duplicate for seamless loop
}

/* ---- portfolio mutations ---- */
async function addTrade(){
  var d=$("m-date").value, tk=($("m-ticker").value||"").trim().toUpperCase();
  var qty=parseFloat($("m-qty").value), px=parseFloat($("m-price").value);
  if(!d||!tk||!(qty>0)||!(px>=0)){ alert("Enter date, ticker, quantity and price."); return; }
  var fx=(HC.SECURITIES[tk]&&HC.SECURITIES[tk].fx)||1.0;
  var acct=($("m-account")&&$("m-account").value)||"Default";
  await API.addTrade({date:d,ticker:tk,action:$("m-action").value,qty:qty,price:px,brokerage:parseFloat($("m-brk").value)||0,fx:fx,account:acct});
  $("m-ticker").value=$("m-qty").value=$("m-price").value=$("m-brk").value="";
  await loadApp();
}
function importFiles(){
  var fs=[].slice.call($("files").files); if($("statement").files.length) fs.push($("statement").files[0]);
  if($("holdings").files.length) fs.push($("holdings").files[0]);
  if(!fs.length){ alert("Choose a CSV first."); return; }
  var acct=($("imp-account")&&$("imp-account").value)||"Default";
  var texts=[], done=0;
  fs.forEach(function(f){ var rd=new FileReader();
    rd.onload=async function(){ texts.push(rd.result); if(++done===fs.length){ await API.importFiles(texts, acct); await loadApp(); } };
    rd.readAsText(f); });
}
async function setIncome(){ var v=$("income").value; await API.setIncome(v==="flat"?null:parseFloat(v)); render(); }

/* ---- billing ---- */
async function upgrade(tier){
  try{ var s = await API.checkout(tier); if(s.url) window.location = s.url; }
  catch(e){ alert("Checkout error: "+String(e).slice(0,120)); }
}

function copyInbox(){ var t=$("inbox-addr").textContent;
  if(navigator.clipboard) navigator.clipboard.writeText(t); }

async function brokerConnect(){
  try{ var r = await API.brokerConnect();
    if(r.stub_mode) $("broker-status").textContent = "(demo mode — no keys set)";
    if(r.url) window.open(r.url, "_blank");
  }catch(e){ alert("Connect error: "+String(e).slice(0,120)); }
}
async function brokerSync(){
  try{ var r = await API.brokerSync();
    alert("Synced from broker: "+r.added+" new trade(s), "+r.skipped+" already had.");
    await loadApp();
  }catch(e){ alert("Sync error: "+String(e).slice(0,120)); }
}

/* ---- view switch ---- */
function show(which){ $("login").style.display = which==="login"?"block":"none";
  $("shell").style.display = which==="app"?"block":"none"; }

window.addEventListener("DOMContentLoaded", function(){
  initTheme(); buildTicker();
  if(API.token()) loadApp(); else show("login");
});
