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
    action: t.action, qty: t.qty, price: t.price, brokerage: t.brokerage || 0, fx: t.fx || 1 }; });
  CUR.divs = pf.dividends.map(function(d){ var o = { date: new Date(d.date + "T00:00:00Z"), ticker: d.ticker,
    cash: d.cash, franking: d.franking || 0, withholding: d.withholding || 0, fx: d.fx || 1 };
    if(d.franking_credit != null) o.franking_credit = d.franking_credit; return o; });
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

function buildResult(){
  var opt = { method: $("optimise") && $("optimise").checked ? "min_tax" : "fifo" };
  var inc = $("income") ? $("income").value : "flat";
  if(inc === "flat") opt.marginalRate = 0.37; else opt.otherIncome = parseFloat(inc);
  var res = { broker: "server", trades: CUR.trades, dividends: CUR.divs, holdings: [], review: [] };
  return HC.runPipeline([res], opt);
}
function render(){
  if(!CUR.trades.length){ $("dash").innerHTML = '<div class=card style="text-align:center;padding:30px">'
    + '<p class=muted>No holdings yet. Add a trade or import a CSV above to see your dashboard.</p></div>';
    $("perf").innerHTML = $("journal").innerHTML = ""; $("screener").innerHTML = HC.renderScreenerShell(); return; }
  var r = buildResult();
  $("dash").innerHTML = HC.renderDashboard(r);
  $("perf").innerHTML = HC.renderPerformance(r);
  $("journal").innerHTML = HC.renderJournal(r.closedTrades, CUR.ann); wireJournal();
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

/* ---- screener ---- */
function screenFilters(){ return { market:$("scr-market").value, sector:$("scr-sector").value,
  maxPE:parseFloat($("scr-pe").value)||0, minDY:parseFloat($("scr-dy").value)||0,
  minMcap:parseFloat($("scr-mc").value)||0, q:$("scr-q").value, sortKey:SCREEN.sortKey, sortDir:SCREEN.sortDir }; }
function applyScreen(){ $("scr-body").innerHTML = HC.screenRows(screenFilters()); }
function sortScreen(k){ if(SCREEN.sortKey===k) SCREEN.sortDir = SCREEN.sortDir==="asc"?"desc":"asc"; else { SCREEN.sortKey=k; SCREEN.sortDir="desc"; } applyScreen(); }

/* ---- tabs (sidebar nav) ---- */
var TABS = { dash:"dash", perf:"perf", journal:"journal", screener:"screener" };
var TITLES = { dash:"Tax & exposure", perf:"Performance", journal:"Journal", screener:"Screener" };
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
  await API.addTrade({date:d,ticker:tk,action:$("m-action").value,qty:qty,price:px,brokerage:parseFloat($("m-brk").value)||0,fx:fx});
  $("m-ticker").value=$("m-qty").value=$("m-price").value=$("m-brk").value="";
  await loadApp();
}
function importFiles(){
  var fs=[].slice.call($("files").files); if($("statement").files.length) fs.push($("statement").files[0]);
  if($("holdings").files.length) fs.push($("holdings").files[0]);
  if(!fs.length){ alert("Choose a CSV first."); return; }
  var texts=[], done=0;
  fs.forEach(function(f){ var rd=new FileReader();
    rd.onload=async function(){ texts.push(rd.result); if(++done===fs.length){ await API.importFiles(texts); await loadApp(); } };
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
