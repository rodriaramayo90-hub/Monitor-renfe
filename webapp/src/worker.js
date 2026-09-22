const REPO = "rodriaramayo90-hub/Monitor-renfe";
const CONFIG_PATH = "config.json";
const STATIONS = {
  "OURENSE": "0071,22100,22100",
  "A CORUÑA": "0071,31412,31412"
};

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, ch => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  }[ch]));
}

function buyHtml(u) {
  const origin = (u.searchParams.get("origin") || "").toUpperCase();
  const destination = (u.searchParams.get("destination") || "").toUpperCase();
  const date = u.searchParams.get("date") || "";
  const departure = u.searchParams.get("departure") || "00:00";
  const passengers = Number(u.searchParams.get("passengers") || "1");

  if (!STATIONS[origin] || !STATIONS[destination] || origin === destination) {
    return {status:400, body:"Trayecto inválido"};
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    return {status:400, body:"Fecha inválida"};
  }
  if (!/^\d{2}:\d{2}$/.test(departure)) {
    return {status:400, body:"Hora inválida"};
  }
  if (!Number.isInteger(passengers) || passengers < 1 || passengers > 9) {
    return {status:400, body:"Pasajeros inválidos"};
  }

  const [y,m,d] = date.split("-");
  const renfeDate = `${d}/${m}/${y}`;
  const fields = {
    tipoBusqueda:"autocomplete",
    currenLocation:"menuBusqueda",
    vengoderenfecom:"SI",
    desOrigen:origin,
    desDestino:destination,
    cdgoOrigen:STATIONS[origin],
    cdgoDestino:STATIONS[destination],
    idiomaBusqueda:"ES",
    FechaIdaSel:renfeDate,
    FechaVueltaSel:"",
    _fechaIdaVisual:renfeDate,
    _fechaVueltaVisual:"",
    minPriceDeparture:"false",
    minPriceReturn:"false",
    adultos_:String(passengers),
    ninos_:"0",
    ninosMenores:"0",
    codPromocional:"",
    plazaH:"false",
    sinEnlace:"false",
    conMascota:"false",
    conBicicleta:"false",
    asistencia:"false",
    franjaHoraI:departure,
    franjaHoraV:"00:00",
    Idioma:"es",
    Pais:"ES"
  };
  const inputs = Object.entries(fields)
    .map(([k,v]) => `<input type="hidden" name="${esc(k)}" value="${esc(v)}">`)
    .join("");

  return {status:200, body:`<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Abriendo Renfe…</title>
<style>body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;margin:0;background:#f5f7fa;color:#172033;display:grid;place-items:center;min-height:100vh;padding:24px}.box{max-width:520px;background:#fff;border:1px solid #dde3ea;border-radius:18px;padding:28px;text-align:center;box-shadow:0 8px 30px #0000000a}button{border:0;border-radius:10px;padding:13px 20px;font-size:16px;font-weight:750;background:#5b2aa8;color:#fff;cursor:pointer}</style>
</head><body><div class="box"><h1>🚆 Abriendo Renfe…</h1>
<p>${esc(origin)} → ${esc(destination)} · ${esc(renfeDate)} · desde ${esc(departure)}</p>
<form id="renfe" method="post" action="https://venta.renfe.com/vol/buscarTren.do?Idioma=es&Pais=ES">
${inputs}<button type="submit">Continuar a Renfe</button></form>
<script>document.getElementById("renfe").submit();</script>
</div></body></html>`};
}

function html() {
  return `<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Monitor Renfe</title>
<style>
:root{font-family:system-ui,-apple-system,Segoe UI,sans-serif;color:#172033;background:#f5f7fa}
*{box-sizing:border-box}body{margin:0;padding:24px 14px}.wrap{max-width:620px;margin:auto}
.card{background:white;border:1px solid #dde3ea;border-radius:18px;padding:22px;box-shadow:0 8px 30px #0000000a}
h1{margin:0 0 6px;font-size:28px}.sub{color:#667085;margin:0 0 22px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.full{grid-column:1/-1}
label{display:block;font-weight:650;font-size:14px;margin-bottom:6px}input,select,button{width:100%;min-height:48px;border-radius:10px;font-size:16px}
input,select{border:1px solid #cfd6df;padding:10px 12px;background:white}button{border:0;padding:11px 16px;font-weight:750;cursor:pointer}
.primary{background:#5b2aa8;color:white}.secondary{background:#eef1f5;color:#273142}.status{margin-top:18px;padding:14px;border-radius:12px;background:#f2f4f7;line-height:1.5}
.ok{background:#ecfdf3;color:#116b3b}.err{background:#fff1f0;color:#9f1c14}.actions{display:grid;grid-template-columns:2fr 1fr;gap:10px;margin-top:18px}
@media(max-width:520px){.grid{grid-template-columns:1fr}.full{grid-column:auto}.actions{grid-template-columns:1fr}body{padding:12px}.card{padding:18px}}
</style></head>
<body><main class="wrap"><section class="card">
<h1>🚆 Monitor Renfe</h1><p class="sub">Configura la búsqueda y recibe un aviso cuando aparezcan plazas.</p>
<form id="form">
<div class="grid">
<div class="full"><label for="direction">Trayecto</label><select id="direction"><option value="OC">Ourense → A Coruña</option><option value="CO">A Coruña → Ourense</option></select></div>
<div class="full"><label for="date">Fecha del viaje</label><input id="date" type="date" required></div>
<div><label for="from">Salida desde</label><input id="from" type="time" required></div>
<div><label for="to">Salida hasta</label><input id="to" type="time" required></div>
<div><label for="passengers">Pasajeros</label><select id="passengers"><option>1</option><option>2</option><option>3</option><option>4</option><option>5</option><option>6</option><option>7</option><option>8</option><option>9</option></select></div>
<div><label for="pin">PIN</label><input id="pin" type="password" inputmode="numeric" autocomplete="current-password" required></div>
</div>
<div class="actions"><button class="primary" type="submit">🔔 Activar / actualizar avisos</button><button class="secondary" type="button" id="stop">Desactivar</button></div>
</form>
<div id="status" class="status">Introduce el PIN para cargar la configuración activa.</div>
</section></main>
<script>
const $=id=>document.getElementById(id), status=$("status");
async function api(method, body){
 const pin=$("pin").value.trim(); if(!pin) throw new Error("Introduce el PIN.");
 const r=await fetch("/api/config",{method,headers:{"content-type":"application/json","x-app-pin":pin},body:body?JSON.stringify(body):undefined});
 const data=await r.json().catch(()=>({})); if(!r.ok) throw new Error(data.error||"Error de conexión"); return data;
}
function fill(c){
 $("direction").value=c.origin==="A CORUÑA"?"CO":"OC"; $("date").value=c.date; $("from").value=c.time_from; $("to").value=c.time_to; $("passengers").value=String(c.passengers);
 status.className="status "+(c.active?"ok":""); status.textContent=(c.active?"🟢 Activo: ":"⚪ Desactivado: ")+c.origin+" → "+c.destination+" · "+c.date+" · "+c.time_from+"–"+c.time_to+" · "+c.passengers+" pasajero(s)";
}
$("pin").addEventListener("change",async()=>{try{fill(await api("GET"));}catch(e){status.className="status err";status.textContent=e.message;}});
$("form").addEventListener("submit",async e=>{e.preventDefault();try{
 const co=$("direction").value==="CO"; const payload={active:true,origin:co?"A CORUÑA":"OURENSE",destination:co?"OURENSE":"A CORUÑA",date:$("date").value,time_from:$("from").value,time_to:$("to").value,passengers:Number($("passengers").value)};
 fill(await api("PUT",payload)); status.textContent="✅ Configuración guardada. "+status.textContent;
}catch(err){status.className="status err";status.textContent=err.message;}});
$("stop").addEventListener("click",async()=>{try{const c=await api("GET");c.active=false;fill(await api("PUT",c));}catch(err){status.className="status err";status.textContent=err.message;}});
</script></body></html>`;
}

async function github(env, method, body) {
  const url = `https://api.github.com/repos/${REPO}/contents/${CONFIG_PATH}`;
  const r = await fetch(url, {
    method,
    headers: {
      "Authorization": `Bearer ${env.GITHUB_TOKEN}`,
      "Accept": "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "renfe-monitor-config"
    },
    body: body ? JSON.stringify(body) : undefined
  });
  const data = await r.json();
  if (!r.ok) throw new Error(data.message || "GitHub error");
  return data;
}
function auth(req, env){ return req.headers.get("x-app-pin") === env.APP_PIN; }
function validate(c){
  if(!["OURENSE","A CORUÑA"].includes(c.origin)||!["OURENSE","A CORUÑA"].includes(c.destination)||c.origin===c.destination) throw new Error("Trayecto inválido");
  if(!/^\d{4}-\d{2}-\d{2}$/.test(c.date)) throw new Error("Fecha inválida");
  if(!/^\d{2}:\d{2}$/.test(c.time_from)||!/^\d{2}:\d{2}$/.test(c.time_to)||c.time_from>c.time_to) throw new Error("Franja horaria inválida");
  c.passengers=Number(c.passengers); if(!Number.isInteger(c.passengers)||c.passengers<1||c.passengers>9) throw new Error("Pasajeros inválidos");
  c.active=Boolean(c.active); return c;
}
export default {
 async fetch(req, env) {
  const u=new URL(req.url);
  if(u.pathname==="/" && req.method==="GET") return new Response(html(),{headers:{"content-type":"text/html; charset=utf-8","cache-control":"no-store"}});
  if(u.pathname==="/buy" && req.method==="GET"){
    const page=buyHtml(u);
    return new Response(page.body,{status:page.status,headers:{"content-type":"text/html; charset=utf-8","cache-control":"no-store"}});
  }
  if(u.pathname!=="/api/config") return new Response("Not found",{status:404});
  if(!auth(req,env)) return Response.json({error:"PIN incorrecto"},{status:401});
  try{
   const file=await github(env,"GET");
   const current=JSON.parse(atob(file.content.replace(/\n/g,"")));
   if(req.method==="GET") return Response.json(current,{headers:{"cache-control":"no-store"}});
   if(req.method==="PUT"){
    const next=validate(await req.json());
    const content=btoa(unescape(encodeURIComponent(JSON.stringify(next,null,2)+"\n")));
    await github(env,"PUT",{message:"Update Renfe search from web form",content,sha:file.sha,branch:"main"});
    return Response.json(next);
   }
   return Response.json({error:"Método no permitido"},{status:405});
  }catch(e){return Response.json({error:e.message||"Error interno"},{status:500});}
 }
};