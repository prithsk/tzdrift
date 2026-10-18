"""tzdrift: see timezone bugs before they happen.

A runtime's timezone database is a snapshot. When governments change their clock rules, every runtime
on an older snapshot starts rendering those zones wrong on the day the change takes effect. tzdrift diffs
your runtime's IANA release against the latest one, hour by hour, and lists every zone and date that will
render wrong inside your horizon.

  python tzdrift.py --runtime 2026b                 # a release name
  python tzdrift.py --node                          # whatever tzdata your installed Node ships
  python tzdrift.py --runtime 2026a --fail-within 30   # exit 1 if anything breaks within 30 days (for CI)
"""
import argparse, datetime as dt, hashlib, json, os, subprocess, sys, tempfile
from pathlib import Path
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
CACHE = Path(os.environ.get("TZDRIFT_CACHE", Path.home() / ".cache" / "tzdrift"))

def release_to_pip(rel):
    """IANA '2026b' -> PyPI tzdata '2026.2'."""
    rel = rel.strip().lower()
    return f"{rel[:4]}.{ord(rel[4]) - ord('a') + 1}"

def latest_release():
    out = subprocess.run([sys.executable, "-m", "pip", "index", "versions", "tzdata"], capture_output=True, text=True).stdout
    v = out.split("(")[1].split(")")[0]                     # 'tzdata (2026.5)' -> 2026.5
    y, n = v.split(".")[:2]; return f"{y}{chr(ord('a') + int(n) - 1)}"

def ensure(rel):
    d = CACHE / rel
    if not (d / "tzdata").exists():
        d.mkdir(parents=True, exist_ok=True)
        r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--target", str(d), f"tzdata=={release_to_pip(rel)}"], capture_output=True, text=True)
        if r.returncode: raise SystemExit(f"could not fetch tzdata {rel}: {r.stderr[-300:]}")
    return d

PROBE = r'''
import sys, json, datetime as dt
sys.path.insert(0, sys.argv[1])
import zoneinfo; zoneinfo.reset_tzpath(to=[])
import tzdata
start = dt.datetime.fromisoformat(sys.argv[2]); hours = int(sys.argv[3]); step = int(sys.argv[4])
out = {}
for n in sorted(zoneinfo.available_timezones()):
    try: z = zoneinfo.ZoneInfo(n)
    except Exception: continue
    out[n] = [int((start + dt.timedelta(hours=h)).astimezone(z).utcoffset().total_seconds() // 60) for h in range(0, hours, step)]
print(json.dumps({"version": tzdata.IANA_VERSION, "offsets": out}))
'''

def offsets(rel, start, hours, step):
    d = ensure(rel)
    r = subprocess.run([sys.executable, "-c", PROBE, str(d), start.isoformat(), str(hours), str(step)], capture_output=True, text=True)
    if r.returncode: raise SystemExit(r.stderr[-500:])
    return json.loads(r.stdout)

def canonical_names(rel):
    tab = ensure(rel) / "tzdata" / "zoneinfo" / "zone1970.tab"
    if not tab.exists(): return set()
    return {line.split("\t")[2].strip() for line in tab.read_text(encoding="utf-8").splitlines() if line and not line.startswith("#") and len(line.split("\t")) > 2}

def alias_groups(rel, zones):
    root = ensure(rel) / "tzdata" / "zoneinfo"; groups = {}; canon = canonical_names(rel)
    for z in zones:
        p = root / z
        key = hashlib.sha1(p.read_bytes()).hexdigest() if p.exists() else z
        groups.setdefault(key, []).append(z)
    return [sorted(g, key=lambda z: (z not in canon, z.startswith(("Canada/", "US/", "Etc/")), z)) for g in groups.values()]

def drift(runtime, latest, start, horizon_days=365, step=1):
    hours = horizon_days * 24
    old, new = offsets(runtime, start, hours, step), offsets(latest, start, hours, step)
    rows = []
    for z, cur in new["offsets"].items():
        prev = old["offsets"].get(z)
        if prev is None:
            rows.append({"zone": z, "first_wrong": start.isoformat(), "shift_min": None, "wrong_hours": hours, "note": f"zone missing from {runtime}"}); continue
        idx = [i for i, (a, b) in enumerate(zip(prev, cur)) if a != b]
        if idx:
            i = idx[0]
            rows.append({"zone": z, "first_wrong": (start + dt.timedelta(hours=i * step)).isoformat(),
                         "runtime_offset": prev[i], "correct_offset": cur[i], "shift_min": prev[i] - cur[i], "wrong_hours": len(idx) * step})
    groups = alias_groups(latest, [r["zone"] for r in rows])
    by = {r["zone"]: r for r in rows}
    merged = []
    for g in groups:
        r = dict(by[g[0]]); r["aliases"] = g[1:]; merged.append(r)
    merged.sort(key=lambda r: (r["first_wrong"], r["zone"]))
    return {"runtime": runtime, "latest": latest, "start": start.isoformat(), "horizon_days": horizon_days, "rule_sets": merged,
            "keys": len(rows)}

def fmt_off(m):
    if m is None: return "-"
    s = "+" if m >= 0 else "-"; m = abs(m); return f"UTC{s}{m // 60:02d}:{m % 60:02d}"

def render(res):
    rs = res["rule_sets"]
    out = [f"runtime tzdata {res['runtime']} vs latest {res['latest']}, next {res['horizon_days']} days from {res['start'][:10]}",
           f"{len(rs)} rule sets ({res['keys']} timezone keys) will render wrong", ""]
    if rs:
        out += ["| Zone | Also | First wrong | Runtime says | Correct | Error |", "|---|---|---|---|---|---|"]
        for r in rs:
            err = f"{r['shift_min']:+d} min" if r.get("shift_min") is not None else r.get("note", "")
            out.append(f"| {r['zone']} | {', '.join(r['aliases']) or '-'} | {r['first_wrong'][:10]} | {fmt_off(r.get('runtime_offset'))} | {fmt_off(r.get('correct_offset'))} | {err} |")
    return "\n".join(out)

def node_release():
    try: return subprocess.run(["node", "-p", "process.versions.tz"], capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception: raise SystemExit("node not found; pass --runtime instead")

def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True); g.add_argument("--runtime"); g.add_argument("--node", action="store_true")
    ap.add_argument("--latest"); ap.add_argument("--horizon-days", type=int, default=365); ap.add_argument("--start")
    ap.add_argument("--fail-within", type=int, help="exit 1 if any zone goes wrong within this many days"); ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    runtime = node_release() if a.node else a.runtime
    latest = a.latest or latest_release()
    start = dt.datetime.fromisoformat(a.start).replace(tzinfo=dt.timezone.utc) if a.start else dt.datetime.now(dt.timezone.utc).replace(minute=0, second=0, microsecond=0)
    res = drift(runtime, latest, start, a.horizon_days)
    print(json.dumps(res, indent=1) if a.json else render(res))
    if a.fail_within is not None:
        cut = start + dt.timedelta(days=a.fail_within)
        soon = [r for r in res["rule_sets"] if dt.datetime.fromisoformat(r["first_wrong"]) <= cut]
        if soon: sys.exit(1)

if __name__ == "__main__": main()
