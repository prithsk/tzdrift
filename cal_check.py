"""Ask Cal.com's live /v2/slots API what UTC offset it gives each zone tzdrift flagged, and compare.

The slots API formats every slot in the timeZone you request, using whatever tz database Cal's server has.
So one event type is enough to test every zone: same request, different timeZone.

  CAL_API_KEY and CAL_EVENT_TYPE_ID in .env, then:
  python cal_check.py --date 2026-11-20
"""
import argparse, datetime as dt, json, os, re, sys, urllib.request, urllib.error
from pathlib import Path
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
import tzdrift
ROOT = Path(__file__).parent
for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines() if (ROOT / ".env").exists() else []:
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        if v.strip(): os.environ.setdefault(k.strip(), v.strip())
ZONES = ["America/Vancouver", "America/Edmonton", "America/Inuvik", "America/Winnipeg", "Africa/Casablanca", "Africa/El_Aaiun",
         "America/Toronto", "Europe/London"]          # last two are controls with no rule change

def slots(event_type_id, date, tz):
    q = f"eventTypeId={event_type_id}&start={date}&end={date}&timeZone={tz}"
    req = urllib.request.Request(f"https://api.cal.com/v2/slots?{q}", headers={"Authorization": f"Bearer {os.environ['CAL_API_KEY']}", "cal-api-version": "2024-09-04", "User-Agent": "Mozilla/5.0 (compatible; tzdrift/0.1; +https://github.com/prithsk/tzdrift)", "Accept": "application/json"})
    try: return json.loads(urllib.request.urlopen(req, timeout=30).read())
    except urllib.error.HTTPError as e: raise SystemExit(f"Cal API {e.code}: {e.read()[:400]}")

def offset_of(stamp):
    m = re.search(r"([+-])(\d{2}):(\d{2})$", stamp)
    if not m: return None
    sign = 1 if m.group(1) == "+" else -1; return sign * (int(m.group(2)) * 60 + int(m.group(3)))

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--date", default="2026-11-20"); a = ap.parse_args()
    for k in ("CAL_API_KEY", "CAL_EVENT_TYPE_ID"):
        if not os.environ.get(k): raise SystemExit(f"{k} is not set in .env")
    latest = tzdrift.latest_release()
    noon = dt.datetime.fromisoformat(a.date + "T12:00:00+00:00")
    truth = tzdrift.offsets(latest, noon, 1, 1)["offsets"]
    rows = []
    for z in ZONES:
        data = slots(os.environ["CAL_EVENT_TYPE_ID"], a.date, z).get("data", {})
        stamps = [s.get("start") if isinstance(s, dict) else s for day in data.values() for s in day]
        offs = sorted({offset_of(s) for s in stamps if s})
        want = truth[z][0]
        rows.append((z, offs, want, bool(offs) and all(o == want for o in offs)))
    out = [f"# Cal.com /v2/slots vs IANA {latest}, {a.date}", "", "| Zone | Cal returned | Correct ({}) | Match |".format(latest), "|---|---|---|---|"]
    for z, offs, want, ok in rows:
        out.append(f"| {z} | {', '.join(tzdrift.fmt_off(o) for o in offs) or 'no slots'} | {tzdrift.fmt_off(want)} | {'yes' if ok else 'NO'} |")
    bad = [r for r in rows if r[1] and not r[3]]
    out += ["", f"**{len(bad)} of {len([r for r in rows if r[1]])} zones with slots came back with the wrong offset.**"]
    md = "\n".join(out); (ROOT / "cal-check-results.md").write_text(md, encoding="utf-8"); print(md)

if __name__ == "__main__": main()
