/* Thin API client for the hosted HoldCapital backend (same origin). */
var API = (function () {
  function token(){ return localStorage.getItem("hc_token"); }
  function setToken(t){ if(t) localStorage.setItem("hc_token", t); else localStorage.removeItem("hc_token"); }
  function H(extra){ var h = Object.assign({"Content-Type":"application/json"}, extra||{});
    if(token()) h["Authorization"]="Bearer "+token(); return h; }
  async function j(method, path, body){
    var r = await fetch(path, {method:method, headers:H(), body: body!=null?JSON.stringify(body):undefined});
    if(!r.ok){ var t = await r.text(); throw new Error(t || (r.status+"")); }
    var ct = r.headers.get("content-type")||""; return ct.indexOf("json")>=0 ? r.json() : r.text();
  }
  return {
    token:token, setToken:setToken,
    signup:(email,password)=>j("POST","/auth/signup",{email,password}),
    login:(email,password)=>j("POST","/auth/login",{email,password}),
    me:()=>j("GET","/me"),
    setIncome:(v)=>j("POST","/me/income",{other_income:v}),
    portfolio:()=>j("GET","/portfolio"),
    accounts:()=>j("GET","/accounts"),
    portfolios:()=>j("GET","/portfolios"),
    createPortfolio:(name)=>j("POST","/portfolios",{name}),
    movePosition:(ticker,account,to)=>j("POST","/portfolio/move",{ticker,account,to}),
    deleteTrade:(id)=>j("DELETE","/portfolio/trade/"+id),
    addTrade:(t)=>j("POST","/portfolio/trade",t),
    importFiles:(files,account)=>j("POST","/portfolio/import",{files,account}),
    refreshPrices:()=>j("POST","/prices/refresh"),
    prices:()=>j("GET","/prices"),
    journal:()=>j("GET","/journal"),
    saveNote:(n)=>j("POST","/journal",n),
    brokerStatus:()=>j("GET","/broker/status"),
    brokerConnect:()=>j("POST","/broker/connect"),
    brokerSync:()=>j("POST","/broker/sync"),
    checkout:(tier)=>j("POST","/billing/checkout",{tier}),
    billingStatus:()=>j("GET","/billing/status"),
    inboxAddress:()=>j("GET","/inbox/address")
  };
})();
