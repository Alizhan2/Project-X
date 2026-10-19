#!/usr/bin/env python3
"""Bounded load/contention test for a Doedu STAGING or local stack (stdlib only).

SAFETY: refuses any host except localhost/127.0.0.1 unless --authorised-host is given. Never run it against production.
It creates throw-away users (loadtest-*@example.test) and bookings, so use a database you can re-seed.
Scenarios:  reads | flow | race | dup        e.g.  ops/loadtest.py http://127.0.0.1:8200 reads --users 20 --seconds 20
"""
import argparse
import http.cookiejar
import json
import statistics
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo


class Client:
    def __init__(self, base):
        self.base = base
        # Secure cookies are normally withheld over plain http; for a LOCAL http test stack allow them (browsers exempt localhost too).
        self.jar = http.cookiejar.CookieJar(http.cookiejar.DefaultCookiePolicy(secure_protocols=("https", "http")))
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def csrf(self):
        return next((c.value for c in self.jar if c.name == "csrftoken"), "")

    def call(self, method, path, body=None, headers=None):
        data = json.dumps(body).encode() if body is not None else None
        h = {"Content-Type": "application/json", "X-CSRFToken": self.csrf(), **(headers or {})}
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=h)
        started = time.perf_counter()
        try:
            with self.opener.open(req, timeout=30) as r:
                payload = r.read()
                status = r.status
        except urllib.error.HTTPError as e:
            payload, status = e.read(), e.code
        ms = (time.perf_counter() - started) * 1000
        try:
            parsed = json.loads(payload) if payload else None
        except ValueError:
            parsed = None
        return status, parsed, ms

    def register(self):
        self.call("GET", "/api/auth/csrf/")
        email = f"loadtest-{uuid.uuid4().hex[:12]}@example.test"
        s, _, _ = self.call("POST", "/api/auth/register/", {"email": email, "full_name": "Load Test", "password": "correct-horse-42-lt"})
        assert s == 201, f"register failed: {s}"
        return email


def pct(values, p):
    return sorted(values)[min(len(values) - 1, int(len(values) * p))] if values else float("nan")


def report(name, lat, errors, seconds, extra=""):
    print(f"{name:<34} n={len(lat):<5} err={errors:<3} rps={len(lat)/seconds:6.1f}  p50={pct(lat,.5):6.0f}ms p95={pct(lat,.95):6.0f}ms p99={pct(lat,.99):6.0f}ms max={max(lat, default=0):6.0f}ms {extra}")


def demo_day():
    d = datetime.now(ZoneInfo("Europe/Berlin")).date() + timedelta(days=1)
    return d.isoformat()


def scenario_reads(base, users, seconds):
    day = demo_day()
    paths = [f"/api/search/?origin=NG-BUS&destination=PM-MARINA&depart_after={day}T11:00&passengers=1&sort=price",
             f"/api/search/?origin=NG-BUS&destination=RV-BUS&depart_after={day}T06:00&passengers=2",
             "/api/stops/", "/api/config/", "/api/health/ready/"]
    lat = {p.split("?")[0]: [] for p in paths}
    errors = [0]
    stop = time.time() + seconds
    lock = threading.Lock()

    def worker(i):
        c = Client(base)
        n = i
        while time.time() < stop:
            p = paths[n % len(paths)]
            n += 1
            s, _, ms = c.call("GET", p)
            with lock:
                lat[p.split("?")[0]].append(ms)
                errors[0] += s >= 500 or s == 429

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(users)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    allv = [v for l in lat.values() for v in l]
    for k, v in lat.items():
        report(k, v, 0, seconds)
    report(f"ALL ({users} concurrent users)", allv, errors[0], seconds)


def find_service(c, origin, dest, hhmm, passengers=1, only_direct=True):
    day = demo_day()
    s, d, _ = c.call("GET", f"/api/search/?origin={origin}&destination={dest}&depart_after={day}T{hhmm}&passengers={passengers}")
    for r in d["results"]:
        if not only_direct or r["transfers"] == 0:
            return r
    raise SystemExit("no suitable journey found: is the stack freshly seeded?")


def checkout_body(it, passengers=1):
    return {"passengers": passengers, "legs": it["selection"], "expected_total": it["total_price"],
            "contact_email": "loadtest@example.test", "travellers": [f"T{i}" for i in range(passengers)]}


def scenario_flow(base, users):
    """Each virtual user: register, search, reserve, fail a payment, pay. Latencies per step."""
    steps = {"register": [], "search": [], "checkout": [], "pay": []}
    results, failures = [], []
    lock = threading.Lock()

    def worker():
        try:
            one_user()
        except Exception as exc:  # noqa: BLE001 - count it, keep the run going
            with lock:
                results.append(False)
                failures.append(repr(exc)[:80])

    def one_user():
        c = Client(base)
        t = time.perf_counter(); c.register(); r_ms = (time.perf_counter() - t) * 1000
        it = find_service(c, "NG-BUS", "RV-BUS", "16:00")
        s1, b, ms1 = c.call("POST", "/api/bookings/", checkout_body(it), {"Idempotency-Key": uuid.uuid4().hex})
        ok = s1 == 201
        ms2 = 0
        if ok:
            s2, _, ms2 = c.call("POST", f"/api/bookings/{b['reference']}/pay/", {"outcome": "success"}, {"Idempotency-Key": uuid.uuid4().hex})
            ok = s2 == 200
        with lock:
            steps["register"].append(r_ms); steps["checkout"].append(ms1); steps["pay"].append(ms2); results.append(ok)

    started = time.time()
    ts = [threading.Thread(target=worker) for _ in range(users)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    secs = time.time() - started
    for k, v in steps.items():
        if v:
            report(k, v, 0, secs)
    print(f"complete purchases: {sum(results)}/{users}" + (f"   failures: {sorted(set(failures))}" if failures else ""))


def scenario_race(base, users):
    """`users` passengers try to buy the LAST place of GL1 07:30 (seeded with exactly one place left) at the same instant."""
    day = demo_day()
    clients = [Client(base) for _ in range(users)]
    for c in clients:
        c.register()
    it = find_service(clients[0], "NG-BUS", "RV-BUS", "07:00")
    last = next((r for r in json.loads(json.dumps([find_service(clients[0], "NG-BUS", "RV-BUS", "07:25")])) if r["legs"][0]["route_code"] == "GL1"), None)
    if not last:
        raise SystemExit("GL1 07:30 not offered (already sold out? re-seed)")
    barrier = threading.Barrier(users)
    codes, ms = [], []
    lock = threading.Lock()

    def worker(c):
        barrier.wait()
        s, _, m = c.call("POST", "/api/bookings/", checkout_body(last), {"Idempotency-Key": uuid.uuid4().hex})
        with lock:
            codes.append(s); ms.append(m)

    ts = [threading.Thread(target=worker, args=(c,)) for c in clients]
    [t.start() for t in ts]
    [t.join() for t in ts]
    print(f"{users} simultaneous checkouts for the last place -> statuses {sorted(codes)}")
    print(f"  successes: {codes.count(201)} (must be exactly 1), conflicts: {codes.count(409)}, 5xx: {sum(c >= 500 for c in codes)}, p95={pct(ms,.95):.0f}ms")
    sys.exit(0 if codes.count(201) == 1 and not any(c >= 500 for c in codes) else 1)


def scenario_dup(base, users):
    """The SAME checkout (same Idempotency-Key) sent `users` times in parallel must create exactly one booking."""
    c0 = Client(base)
    c0.register()
    it = find_service(c0, "NG-BUS", "RV-BUS", "18:00")
    key = uuid.uuid4().hex
    barrier = threading.Barrier(users)
    out, refs = [], set()

    def worker():
        c = Client(base)
        c.jar = c0.jar  # same session
        c.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(c0.jar))
        barrier.wait()
        s, b, _ = c.call("POST", "/api/bookings/", checkout_body(it), {"Idempotency-Key": key})
        out.append(s)
        if b and "reference" in b:
            refs.add(b["reference"])

    ts = [threading.Thread(target=worker) for _ in range(users)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    print(f"{users} identical checkouts -> statuses {sorted(out)}, distinct bookings: {len(refs)} (must be 1)")
    sys.exit(0 if len(refs) == 1 and not any(s >= 500 for s in out) else 1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("base"); ap.add_argument("scenario", choices=["reads", "flow", "race", "dup"])
    ap.add_argument("--users", type=int, default=10); ap.add_argument("--seconds", type=int, default=15)
    ap.add_argument("--authorised-host", action="store_true", help="allow a non-local host you are authorised to load test")
    a = ap.parse_args()
    host = urllib.parse.urlparse(a.base).hostname
    if host not in ("localhost", "127.0.0.1") and not a.authorised_host:
        sys.exit(f"refusing to load test {host}: only localhost by default (never production)")
    if a.users > 200:
        sys.exit("refusing: --users is capped at 200")
    {"reads": lambda: scenario_reads(a.base, a.users, a.seconds), "flow": lambda: scenario_flow(a.base, a.users),
     "race": lambda: scenario_race(a.base, a.users), "dup": lambda: scenario_dup(a.base, a.users)}[a.scenario]()
