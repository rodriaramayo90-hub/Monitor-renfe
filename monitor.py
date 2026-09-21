import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

RENFE_URL = "https://www.renfe.com/es/es"
CONFIG_PATH = Path("config.json")
DEBUG_DIR = Path("debug")


def load_config():
    with CONFIG_PATH.open(encoding="utf-8") as f:
        c = json.load(f)
    for key in ["active","origin","destination","date","time_from","time_to","passengers"]:
        if key not in c:
            raise ValueError(f"Falta {key} en config.json")
    datetime.strptime(c["date"], "%Y-%m-%d")
    datetime.strptime(c["time_from"], "%H:%M")
    datetime.strptime(c["time_to"], "%H:%M")
    return c


def mins(hhmm):
    h, m = map(int, hhmm.split(":"))
    return h * 60 + m


def close_cookies(page):
    for label in ["Permitir solo cookies técnicas","Rechazar","Aceptar todas las cookies"]:
        try:
            b=page.get_by_role("button",name=label)
            if b.count():
                b.first.click(timeout=2500); return
        except Exception:
            pass


def choose_station(page, field_name, station):
    box=page.get_by_role("combobox",name=re.compile(field_name,re.I)).first
    box.click(); box.fill(station); page.wait_for_timeout(700)
    opt=page.get_by_role("option",name=re.compile(re.escape(station),re.I))
    if opt.count():
        opt.first.click(); return
    page.get_by_text(re.compile(rf"^\s*{re.escape(station)}(?:\s*\(TODAS\))?\s*$",re.I)).first.click()


def set_one_way(page):
    try:
        page.get_by_text(re.compile("Viaje solo ida",re.I)).first.click(timeout=3000)
    except Exception:
        try:
            page.get_by_role("button",name=re.compile("Fecha ida",re.I)).first.click()
            page.get_by_text(re.compile("Viaje solo ida",re.I)).first.click(timeout=3000)
        except Exception:
            pass


def set_passengers(page, n):
    if n <= 1: return
    try:
        page.get_by_role("button",name=re.compile("adulto",re.I)).first.click(timeout=4000)
        add=page.get_by_role("button",name=re.compile("Añadir adulto",re.I))
        for _ in range(n-1): add.click()
    except Exception as e:
        print("AVISO pasajeros:",e)


def set_date(page, iso_date):
    target=datetime.strptime(iso_date,"%Y-%m-%d")
    page.get_by_text(re.compile("Fecha ida",re.I)).first.click(timeout=5000)
    month_names={1:"enero",2:"febrero",3:"marzo",4:"abril",5:"mayo",6:"junio",7:"julio",8:"agosto",9:"septiembre",10:"octubre",11:"noviembre",12:"diciembre"}
    pats=[re.compile(rf"{target.day}.*{month_names[target.month]}.*{target.year}",re.I),
          re.compile(rf"{target.day}\s+{month_names[target.month]}",re.I)]
    for _ in range(14):
        for pat in pats:
            for loc in [page.get_by_role("button",name=pat),page.get_by_text(pat)]:
                if loc.count():
                    try: loc.first.click(timeout=1500); return
                    except Exception: pass
        nxt=page.locator('button[aria-label*="iguiente" i],button[title*="iguiente" i]')
        if not nxt.count(): break
        nxt.last.click(); page.wait_for_timeout(300)
    raise RuntimeError(f"No pude seleccionar fecha {iso_date}")


def parse_results_text(body,cfg):
    # Renfe result pages vary often. Work from rendered visible text instead of fragile CSS.
    time_re=re.compile(r"(?<!\d)([01]\d|2[0-3]):[0-5]\d(?:\s*h)?")
    lines=[re.sub(r"\s+"," ",x).strip() for x in body.splitlines() if x.strip()]
    start,end=mins(cfg["time_from"]),mins(cfg["time_to"])
    trains={}
    for i,line in enumerate(lines):
        matches=list(time_re.finditer(line))
        # Often departure/arrival are on separate lines, so inspect a local window.
        window="\n".join(lines[max(0,i-4):min(len(lines),i+12)])
        times=[m.group(0).replace(" h","") for m in time_re.finditer(window)]
        unique=[]
        for t in times:
            if t not in unique: unique.append(t)
        if len(unique)<2: continue
        # A text window can contain more than one train. Pick the first time
        # inside the requested departure range, then the next time as arrival.
        dep_index=None
        for j,t in enumerate(unique):
            try:
                if start<=mins(t)<=end:
                    dep_index=j
                    break
            except Exception:
                pass
        if dep_index is None or dep_index+1>=len(unique):
            continue
        dep,arr=unique[dep_index],unique[dep_index+1]
        if not re.search(r"€|precio|plaza|disponible|completo|agotad|desde",window,re.I): continue
        price=None
        pm=re.search(r"(\d+(?:[.,]\d{1,2})?)\s*€",window)
        if pm: price=pm.group(1).replace(",",".")+" €"
        unavailable=bool(re.search(r"solo plaza h disponible|agotad[oa]|completo|no disponible",window,re.I))
        available=bool((price or re.search(r"precio|desde",window,re.I)) and not unavailable)
        trains[(dep,arr)]={"departure":dep,"arrival":arr,"price":price,"available":available,"text":window[:900]}
    return list(trains.values())


def save_debug(page,body):
    DEBUG_DIR.mkdir(exist_ok=True)
    page.screenshot(path=str(DEBUG_DIR/"results.png"),full_page=True)
    (DEBUG_DIR/"page.txt").write_text(body[:100000],encoding="utf-8")
    (DEBUG_DIR/"page.html").write_text(page.content()[:500000],encoding="utf-8")


def notify(cfg,trains):
    topic=os.getenv("NTFY_TOPIC","").strip()
    if not topic:
        print("NTFY_TOPIC no configurado: no se envían avisos todavía."); return
    for t in trains:
        if not t["available"]: continue
        msg=f"Hay plazas: {cfg['origin']} → {cfg['destination']}\n{cfg['date']} · {t['departure']} → {t['arrival']}\n{cfg['passengers']} pasajero(s)"
        if t["price"]: msg+=f" · {t['price']}"
        requests.post(f"https://ntfy.sh/{topic}",data=msg.encode(),headers={"Title":"RENFE - PLAZAS DISPONIBLES","Priority":"5","Tags":"rotating_light,train","Click":RENFE_URL},timeout=15).raise_for_status()


def run():
    cfg=load_config()
    print("CONFIG:",json.dumps(cfg,ensure_ascii=False))
    if not cfg["active"]:
        print("Monitor desactivado."); return 0
    DEBUG_DIR.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page(viewport={"width":1440,"height":1000},locale="es-ES")
        page.set_default_timeout(15000)
        try:
            print("Abriendo Renfe...")
            page.goto(RENFE_URL,wait_until="domcontentloaded",timeout=60000)
            close_cookies(page)
            print("Seleccionando trayecto...")
            choose_station(page,"Origen",cfg["origin"]); choose_station(page,"Destino",cfg["destination"])
            set_one_way(page); set_date(page,cfg["date"]); set_passengers(page,int(cfg["passengers"]))
            print("Buscando billetes...")
            page.get_by_role("button",name=re.compile("Buscar billete",re.I)).first.click()
            page.wait_for_load_state("domcontentloaded",timeout=60000)
            # Results are client-rendered. Wait for any time/price text rather than a fixed 5 seconds.
            try:
                page.wait_for_function("""() => /(?:[01]\\d|2[0-3]):[0-5]\\d/.test(document.body.innerText)""",timeout=30000)
            except Exception:
                pass
            page.wait_for_timeout(3000)
            body=page.locator("body").inner_text()
            print("Página de resultados cargada:",page.url)
            save_debug(page,body)
            if "Access Denied" in body or "403" in body[:500]:
                raise RuntimeError("Renfe parece bloquear la IP del runner")
            trains=parse_results_text(body,cfg)
            print("Trenes detectados en franja:",json.dumps(trains,ensure_ascii=False,indent=2))
            if not trains:
                print("DIAGNOSTICO: 0 trenes. Se adjuntan results.png, page.txt y page.html.")
                # A zero result is suspicious for this route/test and should be inspectable.
            notify(cfg,trains)
            return 0
        except Exception as e:
            print("ERROR:",repr(e))
            try:
                body=page.locator("body").inner_text()
                save_debug(page,body)
            except Exception: pass
            return 1
        finally:
            browser.close()

if __name__=="__main__":
    sys.exit(run())
