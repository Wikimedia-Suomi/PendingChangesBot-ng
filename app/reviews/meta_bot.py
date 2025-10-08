import os
import csv
import time
import requests
from threading import Lock

# This is the ID of the Quarry querry that fetches the global bot information.
QUARRY_QUERY_ID = int(os.getenv("QUARRY_GLOBAL_BOT_QUERY_ID", "97758"))
QUARRY_CSV_URL = f"https://quarry.wmcloud.org/query/{QUARRY_QUERY_ID}/result/latest/0/csv"
CACHE_TTL = int(os.getenv("GLOBAL_BOT_CACHE_TTL", "24")) * 3600  # seconds

_cache = {"timestamp": 0, "current": set(), "former": set()}
_cache_lock = Lock()
USER_AGENT = "PendingChangesBot-ng/1.0 (global-bot-check) contact: wsaheed77@gmail.com"

def fetch_quarry_csv():
    resp = requests.get(QUARRY_CSV_URL, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    text = resp.text.splitlines()
    reader = csv.reader(text)
    # handle possible header or single-column result
    current = set()
    former = set()
    for row in reader:
        if not row:
            continue
        # only username (original query); treat as unknown -> add to 'current' conservatively
        if len(row) == 1:
            uname = row[0].strip()
            if uname:
                current.add(uname)
        else:
            uname = row[0].strip()
            status = row[1].strip().lower()
            if status == "former":
                former.add(uname)
            else:
                current.add(uname)
    return {"current": current, "former": former}

def refresh_cache_if_needed():
    with _cache_lock:
        if time.time() - _cache["timestamp"] < CACHE_TTL:
            return
        try:
            data = fetch_quarry_csv()
            _cache["current"] = data["current"]
            _cache["former"] = data["former"]
            _cache["timestamp"] = time.time()
        except Exception:
            return       
def is_in_quarry_current(username: str) -> bool:
    refresh_cache_if_needed()
    with _cache_lock:
        return username in _cache["current"]
    
def is_in_quarry_former(username: str) -> bool:
    refresh_cache_if_needed()
    return username in _cache["former"]

def get_meta_groups_via_api(username: str):
    
    url = "https://meta.wikimedia.org/w/api.php"
    params = {
        "action": "query",
        "meta": "globaluserinfo",
        "format": "json",
        "guiuser": username,
        "guiprop": "groups|merged|unattached|rights|editcount",
    }

    r = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=15)
    r.raise_for_status()
    j = r.json()
    # normal JSON path: j['query']['globaluserinfo']['groups']
    return j.get("query", {}).get("globaluserinfo", {}).get("groups", [])

def is_global_bot_via_api(username: str) -> bool:
    groups = get_meta_groups_via_api(username)
    return "bot" in groups or "global-bot" in groups
    

            
            
                