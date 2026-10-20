import json
import logging
import re
import pathlib
import time

import requests

log = logging.getLogger(__name__)

BASE = "https://webexapis.com/v1"
_token_cache = {}


def _token_file(cfg):
    p = pathlib.Path(cfg.get("token_file", "tokens.json"))
    return p


def _load_token_file(cfg):
    p = _token_file(cfg)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def _save_token_file(cfg, data):
    p = _token_file(cfg)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _request_token(cfg, form):
    r = requests.post(BASE + "/access_token", data=form, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(
            f"Webex token request failed ({r.status_code}): {r.text}\n"
            "Check client_id/client_secret and the service-app authorization.")
    d = r.json()
    data = _load_token_file(cfg)
    data["access_token"] = d["access_token"]
    if d.get("refresh_token"):
        data["refresh_token"] = d["refresh_token"]
    data["expires_at"] = time.time() + int(d.get("expires_in", 3600)) - 300
    _save_token_file(cfg, data)
    _token_cache["access"] = d["access_token"]
    _token_cache["expires_at"] = data["expires_at"]
    return data["access_token"]


def get_token(cfg):
    now = time.time()
    if _token_cache.get("access") and now < _token_cache.get("expires_at", 0):
        return _token_cache["access"]
    data = _load_token_file(cfg)
    if data.get("access_token") and now < data.get("expires_at", 0):
        _token_cache.update(access=data["access_token"], expires_at=data["expires_at"])
        return data["access_token"]
    if data.get("refresh_token"):
        try:
            return _request_token(cfg, {
                "grant_type": "refresh_token",
                "client_id": cfg["client_id"],
                "client_secret": cfg["client_secret"],
                "refresh_token": data["refresh_token"],
            })
        except RuntimeError:
            log.warning("Refresh token rejected; falling back to client_credentials.")
    return _request_token(cfg, {
        "grant_type": "client_credentials",
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "scope": cfg.get("scopes", ""),
    })


def api(cfg, method, url, params=None, headers=None, timeout=60):
    for attempt in (1, 2):
        h = {"Authorization": f"Bearer {get_token(cfg)}"}
        if headers:
            h.update(headers)
        r = requests.request(method, url, params=params, headers=h, timeout=timeout)
        if r.status_code == 401 and attempt == 1:
            _token_cache.clear()
            _token_file(cfg).unlink(missing_ok=True)
            continue
        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After", 60)) + 1
            log.warning("Rate limited; sleeping %ss", wait)
            time.sleep(wait)
            continue
        if r.status_code >= 400:
            raise RuntimeError(f"{method} {url} -> {r.status_code}: {r.text[:500]}")
        return r
    raise RuntimeError(f"{method} {url} failed after retries")


def fetch_cdr_window(cfg, start_dt, end_dt):
    """Fetch CDR records for one <=12h window [start,end]; returns list of raw dicts."""
    url = cfg.get("analytics_base_url", "https://analytics-calling.webexapis.com").rstrip("/")
    url += "/v1/cdr_feed"
    records = []
    params = {"startTime": start_dt.isoformat(), "endTime": end_dt.isoformat(), "max": 5000}
    while True:
        r = api(cfg, "GET", url, params=params)
        time.sleep(7)
        data = r.json()
        items = data if isinstance(data, list) else data.get("items") or data.get("data") or []
        records.extend(items)
        next_url = _next_link(r)
        if not next_url:
            break
        url, params = next_url, None
    return records


def _next_link(r):
    head = r.headers.get("Link") or r.headers.get("link") or ""
    m = re.search(r'<(http[^>]+)>;\s*rel="next"', head)
    return m.group(1) if m else None


def list_groups(cfg):
    r = api(cfg, "GET", BASE + "/groups", params={"max": 2000})
    return r.json().get("items", [])


def group_by_name(cfg, name):
    r = api(cfg, "GET", BASE + "/groups", params={"name": name, "max": 10})
    items = r.json().get("items", [])
    for g in items:
        if (g.get("displayName") or g.get("name")) == name:
            return g
    return items[0] if items else None


def group_members(cfg, group_id):
    members, url, params = [], BASE + f"/groups/{group_id}/members", {"max": 2000}
    while True:
        r = api(cfg, "GET", url, params=params)
        data = r.json()
        members.extend(data.get("items", []))
        next_url = _next_link(r) or (data.get("links") or {}).get("next")
        if not next_url:
            break
        url, params = next_url, None
    return members
