import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

RENFE_URL = "https://www.renfe.com/es/es"
CONFIG_PATH = Path("config.json")
DEBUG_DIR = Path("debug")


def load_config():
    with CONFIG_PATH.open(encoding="utf-8") as f:
        c = json.load(f)
    required = ["active", "origin", "destination", "date", "time_from", "time_to", "passengers"]
    missing = [k for k in required if k not in c]
    if missing:
        raise ValueError(f"Faltan campos en config.json: {', '.join(missing)}")
    datetime.strptime(c["date"], "%Y-%m-%d")
    datetime.strptime(c["time_from"], "%H:%M")
    datetime.strptime(c["time_to"], "%H:%M")
    if c["origin"] == c["destination"]:
        raise ValueError("Origen y destino no pueden ser iguales")
    if int(c["passengers"]) < 1:
        raise ValueError("passengers debe ser >= 1")
    return c


def mins(hhmm):
    h, m = map(int, hhmm.split(":"))
    return h * 60 + m


def close_cookies(page):
    for label in ["Permitir solo cookies técnicas", "Rechazar", "Aceptar todas las cookies"]:
        try:
            b = page.get_by_role("button", name=label)
            if b.count():
                b.first.click(timeout=2500)
                return
        except Exception:
            pass


def choose_station(page, field_name, station):
    box = page.get_by_role("combobox", name=re.compile(field_name, re.I)).first
    box.click()
    box.fill(station)
    page.wait_for_timeout(700)
    option = page.get_by_role("option", name=re.compile(re.escape(station), re.I))
    if option.count():
        option.first.click()
        return
    # Fallback for Renfe DOM variants
    page.get_by_text(re.compile(rf"^\s*{re.escape(station)}(?:\s*\(TODAS\))?\s*$", re.I)).first.click()


def set_one_way(page):
    try:
        page.get_by_text(re.compile("Viaje solo ida", re.I)).first.click(timeout=3000)
    except Exception:
        try:
            page.get_by_role("button", name=re.compile("Fecha ida", re.I)).first.click()
            page.get_by_text(re.compile("Viaje solo ida", re.I)).first.click(timeout=3000)
        except Exception:
            pass


def set_passengers(page, passengers):
    if passengers <= 1:
        return
    try:
        page.get_by_role("button", name=re.compile("adulto", re.I)).first.click(timeout=4000)
        add = page.get_by_role("button", name=re.compile("Añadir adulto", re.I))
        for _ in range(passengers - 1):
            add.click()
        # close selector if there is a confirm button
        for name in ["Aceptar", "Listo", "Cerrar"]:
            b = page.get_by_role("button", name=re.compile(name, re.I))
            if b.count():
                try:
                    b.first.click(timeout=1000)
                    break
                except Exception:
                    pass
    except Exception as e:
        print(f"AVISO: no se pudo ajustar pasajeros: {e}")


def set_date(page, iso_date):
    target = datetime.strptime(iso_date, "%Y-%m-%d")
    # Open Renfe date picker.
    date_control = page.get_by_text(re.compile("Fecha ida", re.I)).first
    date_control.click(timeout=5000)
    page.wait_for_timeout(500)

    # Prefer native/accessibility labels containing the full target date.
    day = str(target.day)
    month_names = {
        1:"enero",2:"febrero",3:"marzo",4:"abril",5:"mayo",6:"junio",
        7:"julio",8:"agosto",9:"septiembre",10:"octubre",11:"noviembre",12:"diciembre"
    }
    month = month_names[target.month]
    patterns = [
        re.compile(rf"{target.day}.*{month}.*{target.year}", re.I),
        re.compile(rf"{day}\s+{month}", re.I),
    ]

    for _ in range(14):
        for pat in patterns:
            candidates = page.get_by_role("button", name=pat)
            if candidates.count():
                candidates.first.click()
                return
            candidates = page.get_by_text(pat)
            if candidates.count():
                try:
                    candidates.first.click(timeout=1500)
                    return
                except Exception:
                    pass

        # Check visible month and move calendar forward.
        next_buttons = [
            page.get_by_role("button", name=re.compile("siguiente", re.I)),
            page.locator("button").filter(has=page.locator("svg")).filter(has_text=""),
        ]
        moved = False
        if next_buttons[0].count():
            next_buttons[0].last.click()
            moved = True
        else:
            # Common aria labels / titles.
            for sel in ['button[aria-label*="iguiente" i]', 'button[title*="iguiente" i]']:
                b = page.locator(sel)
                if b.count():
                    b.last.click()
                    moved = True
                    break
        if not moved:
            break
        page.wait_for_timeout(300)

    raise RuntimeError(f"No pude seleccionar la fecha {iso_date} en el calendario de Renfe")


def extract_train_cards(page, cfg):
    start, end = mins(cfg["time_from"]), mins(cfg["time_to"])
    results = page.evaluate("""() => {
      const timeRe = /(?:^|\\s)([01]?\\d|2[0-3]):[0-5]\\d(?:\\s*h)?(?:$|\\s)/g;
      const nodes = [...document.querySelectorAll('body *')];
      const found = [];
      for (const el of nodes) {
        const txt = (el.innerText || '').trim();
        if (!txt || txt.length > 1800) continue;
        const times = [...txt.matchAll(timeRe)].map(m => m[0].trim().replace(/\\s*h$/,''));
        const unique = [...new Set(times)];
        if (unique.length < 2) continue;
        if (!/(€|precio|plaza|disponible|completo|agotado)/i.test(txt)) continue;
        const parent = el.parentElement;
        const ptxt = parent ? (parent.innerText || '') : '';
        if (parent && ptxt.length < 1800 && ptxt.includes(txt) && [...ptxt.matchAll(timeRe)].length <= 5) continue;
        found.push({text: txt, times: unique});
      }
      return found;
    }""")

    trains = {}
    for r in results:
        times = r["times"]
        if len(times) < 2:
            continue
        dep, arr = times[0], times[1]
        try:
            dep_m = mins(dep)
        except Exception:
            continue
        if not (start <= dep_m <= end):
            continue
        text = r["text"]
        key = (dep, arr)
        # Keep shortest matching card; it tends to be the actual train card.
        if key not in trains or len(text) < len(trains[key]["text"]):
            price = None
            pm = re.search(r"(\d+(?:[.,]\d{1,2})?)\s*€", text)
            if pm:
                price = pm.group(1).replace(",", ".") + " €"
            unavailable = bool(re.search(r"solo plaza h disponible|agotad[oa]|completo|no disponible", text, re.I))
            available = (("€" in text or re.search(r"precio", text, re.I)) and not unavailable)
            trains[key] = {
                "departure": dep, "arrival": arr, "price": price,
                "available": bool(available), "text": text[:700]
            }
    return list(trains.values())


def notify(cfg, trains):
    topic = os.getenv("NTFY_TOPIC", "").strip()
    if not topic:
        print("NTFY_TOPIC no configurado: no se envían avisos todavía.")
        return
    for t in trains:
        if not t["available"]:
            continue
        msg = (
            f"Hay plazas: {cfg['origin']} → {cfg['destination']}\n"
            f"{cfg['date']} · {t['departure']} → {t['arrival']}\n"
            f"{cfg['passengers']} pasajero(s)"
        )
        if t["price"]:
            msg += f" · {t['price']}"
        requests.post(
            f"https://ntfy.sh/{topic}",
            data=msg.encode("utf-8"),
            headers={
                "Title": "RENFE - PLAZAS DISPONIBLES",
                "Priority": "5",
                "Tags": "rotating_light,train",
                "Click": RENFE_URL,
            },
            timeout=15,
        ).raise_for_status()


def run():
    cfg = load_config()
    print("CONFIG:", json.dumps(cfg, ensure_ascii=False))
    if not cfg["active"]:
        print("Monitor desactivado en config.json. La infraestructura funciona; no se consulta Renfe.")
        return 0

    DEBUG_DIR.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, locale="es-ES")
        page.set_default_timeout(15000)
        try:
            print("Abriendo Renfe...")
            page.goto(RENFE_URL, wait_until="domcontentloaded", timeout=60000)
            close_cookies(page)
            print("Seleccionando trayecto...")
            choose_station(page, "Origen", cfg["origin"])
            choose_station(page, "Destino", cfg["destination"])
            set_one_way(page)
            set_date(page, cfg["date"])
            set_passengers(page, int(cfg["passengers"]))
            print("Buscando billetes...")
            page.get_by_role("button", name=re.compile("Buscar billete", re.I)).first.click()
            page.wait_for_load_state("domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)
            body = page.locator("body").inner_text()
            print("Página de resultados cargada:", page.url)
            if "Access Denied" in body or "403" in body[:500]:
                raise RuntimeError("Renfe parece estar bloqueando la IP del runner de GitHub")
            trains = extract_train_cards(page, cfg)
            print("Trenes detectados en franja:", json.dumps(trains, ensure_ascii=False, indent=2))
            notify(cfg, trains)
            page.screenshot(path=str(DEBUG_DIR / "last.png"), full_page=True)
            return 0
        except Exception as e:
            print("ERROR:", repr(e))
            try:
                page.screenshot(path=str(DEBUG_DIR / "error.png"), full_page=True)
                (DEBUG_DIR / "page.txt").write_text(page.locator("body").inner_text()[:30000], encoding="utf-8")
            except Exception:
                pass
            return 1
        finally:
            browser.close()


if __name__ == "__main__":
    sys.exit(run())
