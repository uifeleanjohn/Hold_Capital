/* HoldCapital trade journal — analytics + view.
   Each closed round-trip (a CGT disposal) seeds a journal entry; the trader
   annotates setup / confidence / notes / mistake. Stats mirror the essentials
   of a journal like Stonk Journal: win rate, profit factor, average win/loss,
   expectancy, equity curve, and a by-setup breakdown. */
(function (root) {
"use strict";
var HC = root.HC || {};
var money = HC.money;

var SETUPS = ["Untagged","Breakout","Momentum","Producer swing","Explorer punt",
              "US large-cap hold","Event / biotech","Mean reversion","Dividend"];

/* Default annotations used for the bundled sample portfolio. */
var SAMPLE_ANN = {
  "BHP|2024-03-12|2025-08-20":  {setup:"Producer swing", confidence:4, notes:"Iron-ore strength; added on the dip, sold into the rally."},
  "NVDA|2024-01-15|2025-12-02": {setup:"US large-cap hold", confidence:5, notes:"Core AI position. Held past 12 months for the discount."},
  "DEG|2025-10-10|2026-04-01":  {setup:"Explorer punt", confidence:2, notes:"Gold spec on drill hype. Took the quick profit."},
  "PLS|2025-09-05|2026-06-10":  {setup:"Producer swing", confidence:3, notes:"Lithium bounce failed; cut the loss.", mistake:"Held through the downtrend"},
  "MRNA|2025-03-01|2026-05-15": {setup:"Event / biotech", confidence:2, notes:"Pre-data punt; thesis was wrong.", mistake:"Oversized a speculative bet"}
};

function computeJournal(trades, ann){
  ann = ann || {};
  var wins=trades.filter(function(t){return t.pnl>0;}), losses=trades.filter(function(t){return t.pnl<0;});
  var grossWin=wins.reduce(function(s,t){return s+t.pnl;},0);
  var grossLoss=losses.reduce(function(s,t){return s-t.pnl;},0);
  var total=trades.length||1;
  var winRate=wins.length/total, lossRate=losses.length/total;
  var avgWin=wins.length?grossWin/wins.length:0, avgLoss=losses.length?grossLoss/losses.length:0;
  var expectancy=winRate*avgWin - lossRate*avgLoss;
  var totalPnL=trades.reduce(function(s,t){return s+t.pnl;},0);
  var avgHold=trades.reduce(function(s,t){return s+t.daysHeld;},0)/total;

  var setups={};
  trades.forEach(function(t){
    var s=(ann[t.key]&&ann[t.key].setup)||"Untagged";
    if(!setups[s]) setups[s]={setup:s,count:0,wins:0,pnl:0};
    setups[s].count++; if(t.pnl>0) setups[s].wins++; setups[s].pnl+=t.pnl;
  });
  var bySetup=Object.keys(setups).map(function(k){var x=setups[k];
    return {setup:k,count:x.count,winRate:x.wins/x.count,pnl:x.pnl};})
    .sort(function(a,b){return b.pnl-a.pnl;});

  var cum=0, equity=trades.map(function(t){cum+=t.pnl; return {date:t.exit,cum:cum};});
  return {nTrades:trades.length,winRate:winRate,profitFactor:grossLoss?grossWin/grossLoss:Infinity,
    avgWin:avgWin,avgLoss:avgLoss,expectancy:expectancy,totalPnL:totalPnL,avgHold:avgHold,
    bySetup:bySetup,equity:equity};
}

function equitySVG(equity){
  var W=820,H=170,pad=24;
  var cums=equity.map(function(p){return p.cum;}).concat([0]);
  var lo=Math.min.apply(null,cums), hi=Math.max.apply(null,cums); if(hi===lo) hi=lo+1;
  var n=equity.length;
  function x(i){ return pad + (n<=1?0:i*(W-2*pad)/(n-1)); }
  function y(v){ return H-pad - (v-lo)*(H-2*pad)/(hi-lo); }
  var zero=y(0);
  var pts=equity.map(function(p,i){return x(i)+","+y(p.cum);}).join(" ");
  var dots=equity.map(function(p,i){return '<circle cx="'+x(i)+'" cy="'+y(p.cum)+'" r="3" fill="#1c2230"/>';}).join("");
  return '<svg viewBox="0 0 '+W+' '+H+'" width="100%" style="display:block">'
    + '<line x1="'+pad+'" y1="'+zero+'" x2="'+(W-pad)+'" y2="'+zero+'" stroke="#e2e5ea"/>'
    + '<polyline points="'+pts+'" fill="none" stroke="#185fa5" stroke-width="2"/>'+dots
    + '<text x="'+pad+'" y="14" font-size="11" fill="#5b6472">cumulative realised P&amp;L</text></svg>';
}

function esc(s){ return (""+s).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];}); }
function mo(d){ var m=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  return ("0"+d.getUTCDate()).slice(-2)+" "+m[d.getUTCMonth()]+" "+(""+d.getUTCFullYear()).slice(2); }

function renderJournal(trades, ann){
  ann = ann || {};
  var j=computeJournal(trades, ann);
  var pf=j.profitFactor===Infinity?"∞":j.profitFactor.toFixed(2);
  var h='';
  h+='<h2 style="margin-top:6px">Trade journal</h2>';
  h+='<div class=muted style="margin-bottom:8px">Seeded from your '+trades.length+' closed trades. Tag a setup and add notes — your stats update live and save on this computer.</div>';
  h+='<div class=cards>'
   + '<div class="kpi k-green"><div class=l>WIN RATE</div><div class=v>'+Math.round(j.winRate*100)+'%</div><div class=s>'+j.nTrades+' closed trades</div></div>'
   + '<div class="kpi k-blue"><div class=l>PROFIT FACTOR</div><div class=v>'+pf+'</div><div class=s>gross win / gross loss</div></div>'
   + '<div class="kpi '+(j.expectancy>=0?'k-green':'k-ore')+'"><div class=l>EXPECTANCY</div><div class=v>'+money(j.expectancy)+'</div><div class=s>per trade</div></div></div>';
  h+='<div class="cards" style="grid-template-columns:repeat(3,1fr)">'
   + '<div class="kpi" style="background:var(--panel)"><div class=l style="color:var(--slate)">AVG WIN</div><div class=v style="color:var(--green)">'+money(j.avgWin)+'</div></div>'
   + '<div class="kpi" style="background:var(--panel)"><div class=l style="color:var(--slate)">AVG LOSS</div><div class=v style="color:var(--red)">-'+money(j.avgLoss)+'</div></div>'
   + '<div class="kpi" style="background:var(--panel)"><div class=l style="color:var(--slate)">AVG HOLD</div><div class=v>'+Math.round(j.avgHold)+'d</div></div></div>';
  h+='<h2>Equity curve</h2><div class=card>'+equitySVG(j.equity)+'</div>';
  h+='<h2>By setup</h2><div class=card style="padding:0;overflow:hidden"><table>'
   + '<tr><th>Setup</th><th class=r>Trades</th><th class=r>Win rate</th><th class=r>Net P&amp;L</th></tr>';
  j.bySetup.forEach(function(s){ var cls=s.pnl>=0?"pos":"neg";
    h+='<tr><td>'+esc(s.setup)+'</td><td class=r>'+s.count+'</td><td class=r>'+Math.round(s.winRate*100)+'%</td>'
     + '<td class="r '+cls+'">'+(s.pnl>=0?"+":"")+money(s.pnl)+'</td></tr>'; });
  h+='</table></div>';

  h+='<h2>Trades — tag &amp; review</h2><div class=card style="padding:0;overflow:hidden"><table>'
   + '<tr><th>Holding</th><th>Exit</th><th class=r>Held</th><th class=r>P&amp;L</th><th>Setup</th><th class=r>Conf.</th><th>Notes</th></tr>';
  trades.slice().sort(function(a,b){return b.exit-a.exit;}).forEach(function(t){
    var a=ann[t.key]||{}; var cls=t.pnl>=0?"pos":"neg";
    var setOpts=SETUPS.map(function(s){return '<option'+(a.setup===s?' selected':'')+'>'+esc(s)+'</option>';}).join("");
    var confOpts=[1,2,3,4,5].map(function(c){return '<option'+(a.confidence===c?' selected':'')+'>'+c+'</option>';}).join("");
    h+='<tr><td><b>'+esc(t.name)+'</b></td><td>'+mo(t.exit)+'</td><td class=r>'+t.daysHeld+'</td>'
     + '<td class="r '+cls+'">'+(t.pnl>=0?"+":"")+money(t.pnl)+'</td>'
     + '<td><select class="jin" data-k="'+esc(t.key)+'" data-f="setup">'+'<option></option>'+setOpts+'</select></td>'
     + '<td class=r><select class="jin" data-k="'+esc(t.key)+'" data-f="confidence"><option></option>'+confOpts+'</select></td>'
     + '<td><input class="jin" data-k="'+esc(t.key)+'" data-f="notes" value="'+esc(a.notes||"")+'" placeholder="why / what happened" style="width:200px"></td></tr>';
  });
  h+='</table></div>';
  return h;
}

HC.SETUPS=SETUPS; HC.SAMPLE_ANN=SAMPLE_ANN; HC.computeJournal=computeJournal; HC.renderJournal=renderJournal;
if(typeof module!=="undefined"&&module.exports) module.exports=HC;
root.HC=HC;
})(typeof window!=="undefined"?window:(typeof globalThis!=="undefined"?globalThis:this));
