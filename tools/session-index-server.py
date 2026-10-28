"""Linux supervisor and plaintext exporter for our own Yanhekt session index.

The collector is the pinned Apache-2.0 AutoSlides indexer with documented
local concurrency changes under ROOT/source/local. No uploads or publishing.
"""
from __future__ import annotations

import argparse
import collections
from contextlib import closing
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import sqlite3
import subprocess
import tempfile
import threading
import time
import urllib.request

try:
    import fcntl
except ImportError:
    fcntl = None

REVISION = "84fff4da48c6f466073334613bc1eaeb48383d53"
LOCAL_PATCH = "bounded-concurrency-v1"
CONCURRENCY = 5
INTERVAL_MS = 200
ORIGIN = "https://cbiz.yanhekt.cn"
UA = "YanhektSessionIndex/0.1 (+https://github.com/1whoarei1/yanhe-api-reference)"
# The user supplied ~893000 as this term's first id: a priority hint only.
# Keep the entire original scope; metadata, not numeric ranges, decides terms.
HISTORY_BOUNDARY_HINT = 893000
RANGES = [(932000, 1000000), (931999, HISTORY_BOUNDARY_HINT), (HISTORY_BOUNDARY_HINT - 1, 1)]
LEGACY_HISTORY_KEY = "lane:range:931999:1"
COLLECTION_POLICY = "historical-priority-v1"
stop = threading.Event()
child = None


def log(event, **values):
    print(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                      "event": event, **values}, ensure_ascii=False), flush=True)


def atomic_bytes(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".index-", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as output:
            output.write(value)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_json(path, value):
    atomic_bytes(path, json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())


def database(root):
    return root / "data" / "yanhekt-index.db"


def connect(root):
    db = database(root)
    if not db.is_file():
        return None
    connection = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def effective_lane_states(connection):
    """Read-only projection also works before the one-time cursor migration."""
    states = {r["key"]: json.loads(r["value"]) for r in connection.execute(
        "SELECT key,value FROM crawl_state WHERE key LIKE 'lane:%'")}
    previous = states.get(LEGACY_HISTORY_KEY)
    if previous:
        cursor = int(previous["cursor"])
        if not 0 <= cursor <= 932000:
            raise RuntimeError("Previous historical cursor is outside its original scope")
        for start, end in RANGES[1:]:
            key = f"lane:range:{start}:{end}"
            if key in states:
                continue
            next_id = max(end - 1, min(start, cursor))
            done = bool(previous.get("done")) or cursor < end
            if done:
                next_id = end - 1
            inherited = dict(previous) if next_id == cursor and not done else {
                "missRun": 0, "missRunStart": None, "parkedUntilMs": None}
            states[key] = {**inherited, "cursor": next_id, "done": done}
    return states


def migrate_lanes(root):
    """Split the old historical lane without marking deferred ids as visited."""
    if not database(root).is_file():
        return []
    with closing(sqlite3.connect(database(root), timeout=10)) as connection, connection:
        connection.row_factory = sqlite3.Row
        connection.execute("BEGIN IMMEDIATE")
        states = effective_lane_states(connection)
        added = []
        for start, end in RANGES:
            key = f"lane:range:{start}:{end}"
            if key not in states:
                continue
            result = connection.execute("INSERT OR IGNORE INTO crawl_state(key,value) VALUES(?,?)",
                (key, json.dumps(states[key], separators=(",", ":"))))
            if result.rowcount:
                added.append(key)
    return added


def active_schedule(report):
    # Finish the older interval before spending more batches on this term.
    return [2] if not report["ranges"][2]["done"] else [1, 0]


def statistics(connection):
    if connection is None:
        return {"sessions": 0, "courses": 0, "unresolvedSessions": 0, "gaps": 0,
                "requests": 0, "progressIds": 0, "scopeIds": 1000000,
                "ranges": [{"from": a, "to": b, "next": a, "done": False, "visited": 0}
                           for a, b in RANGES], "complete": False,
                "collectionPolicy": COLLECTION_POLICY, "historicalPriorityDone": False}
    states = effective_lane_states(connection)
    ranges = []
    for start, end in RANGES:
        state = states.get(f"lane:range:{start}:{end}", {})
        cursor = int(state.get("cursor", start))
        size = abs(end - start) + 1
        visited = size if state.get("done") else min(size, abs(cursor - start))
        ranges.append({"from": start, "to": end, "next": cursor,
                       "done": bool(state.get("done")), "visited": visited})
    sessions = connection.execute("SELECT COUNT(*) FROM sessions WHERE gone_at IS NULL").fetchone()[0]
    courses = connection.execute("SELECT COUNT(*) FROM courses").fetchone()[0]
    unresolved = connection.execute("SELECT COUNT(*) FROM failures f WHERE f.kind='session' "
        "AND NOT EXISTS (SELECT 1 FROM sessions s WHERE s.id=f.id)").fetchone()[0]
    gaps = connection.execute("SELECT COUNT(*) FROM gaps").fetchone()[0]
    requests = connection.execute("SELECT COALESCE(SUM(requests),0) FROM runs").fetchone()[0]
    return {"sessions": sessions, "courses": courses, "unresolvedSessions": unresolved,
            "gaps": gaps, "requests": requests, "progressIds": sum(r["visited"] for r in ranges),
            "scopeIds": sum(abs(a - b) + 1 for a, b in RANGES), "ranges": ranges,
            "collectionPolicy": COLLECTION_POLICY, "historicalPriorityDone": ranges[2]["done"],
            "complete": all(r["done"] for r in ranges) and not unresolved and not gaps}


def status(root):
    connection = connect(root)
    try:
        return statistics(connection)
    finally:
        if connection:
            connection.close()


def teacher_names(row):
    try:
        professors = json.loads(row.get("professors") or "[]")
    except (TypeError, ValueError):
        professors = []
    if not isinstance(professors, list):
        professors = []
    names = [p["name"].strip() for p in professors if isinstance(p, dict)
             and isinstance(p.get("name"), str) and p["name"].strip()]
    if not names:
        names = [p.strip() for p in re.split(r"[、,，]", row.get("professor_names") or "") if p.strip()]
    return list(dict.fromkeys(names))


def export(root):
    connection = connect(root)
    if connection is None:
        raise RuntimeError("No database yet; run a bounded collection first")
    try:
        connection.execute("BEGIN")  # One consistent WAL snapshot for data and coverage.
        coverage = statistics(connection)
        sessions = collections.defaultdict(list)
        for row in connection.execute("SELECT id,course_id FROM sessions WHERE gone_at IS NULL ORDER BY id"):
            sessions[row["course_id"]].append(row["id"])
        courses = []
        for raw in connection.execute("SELECT * FROM courses ORDER BY id"):
            row = dict(raw)
            year, semester = row.get("school_year"), row.get("semester")
            term = f"{year}-{semester}" if isinstance(year, str) and re.fullmatch(r"\d{4}-\d{4}", year) and semester in range(1, 10) else None
            courses.append({"id": row["id"], "name": row.get("name_zh") or "",
                            "number": row.get("number"), "term": term,
                            "teachers": teacher_names(row), "sessions": sessions[row["id"]]})
    finally:
        connection.close()
    coverage["exportedSessions"] = sum(len(c["sessions"]) for c in courses)
    document = {"format": "yanhekt-session-index/v1", "generatedAt": time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "partial": not coverage["complete"],
        "collectionPolicy": {"name": COLLECTION_POLICY,
                             "historyBoundaryHint": HISTORY_BOUNDARY_HINT,
                             "estimated": True, "termSource": "course.school_year/semester"},
        "source": {"kind": "self-collected", "origin": ORIGIN,
                   "collector": "bit-admin/Yanhekt-AutoSlides", "revision": REVISION,
                   "localPatch": LOCAL_PATCH},
        "coverage": coverage, "courses": courses}
    raw = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode()
    target = root / "exports"
    atomic_bytes(target / "catalog.json", raw)
    atomic_bytes(target / "catalog.json.gz", gzip.compress(raw, compresslevel=6, mtime=0))
    atomic_json(target / "status.json", {**coverage, "generatedAt": document["generatedAt"],
                "catalogSha256": hashlib.sha256(raw).hexdigest(), "catalogBytes": len(raw)})
    return coverage


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def preflight():
    headers = {"Accept": "application/json", "Origin": "https://www.yanhekt.cn",
               "Referer": "https://www.yanhekt.cn/", "User-Agent": UA,
               "Xdomain-Client": "web_user", "Xclient-Version": "v1",
               "Xclient-Timestamp": str(int(time.time())),
               "Xclient-Signature": hashlib.md5(b"1138b69dfef641d9d7ba49137d2d4875_v1_undefined").hexdigest()}
    request = urllib.request.Request(ORIGIN + "/v1/course/session?session_id=71990&with_video=true", headers=headers)
    with urllib.request.build_opener(NoRedirect).open(request, timeout=20) as response:
        if "application/json" not in response.headers.get("Content-Type", ""):
            raise RuntimeError("Preflight returned a non-JSON page; no scanning")
        body = json.load(response)
    data = body.get("data") or {}
    if str(body.get("code")) != "0" or str(data.get("id")) != "71990" or str(
            data.get("course_id") or (data.get("course") or {}).get("id")) != "9397":
        raise RuntimeError("Preflight session identity is unavailable or inconsistent; no scanning")


def environment():
    # No inherited deployment, release or upload credentials are needed here.
    return {k: v for k, v in os.environ.items() if not k.startswith(("CF_", "CLOUDFLARE_", "INDEX_", "GITHUB_", "GH_"))}


def collector_command(root, start, end, request_limit):
    return ["/usr/bin/node", "--disable-warning=ExperimentalWarning",
            str(root / "source" / "indexer" / "src" / "cli.mjs"), "now",
            "--db", str(database(root)), "--from", str(start), "--to", str(end),
            "--interval-ms", str(INTERVAL_MS), "--concurrency", str(CONCURRENCY),
            "--gap-threshold", "1000000", "--batch", "25",
            "--refresh-days", "0", "--max-requests", str(request_limit), "--minutes", "60",
            "--user-agent", UA, "--quiet"]


def signal_stop(signum, frame):
    stop.set()
    if child is not None and child.poll() is None:
        child.send_signal(signal.SIGINT)


def run(root, once=False, request_limit=300):
    global child
    if fcntl is None:
        raise RuntimeError("The supervisor runs on Linux; status/export also work locally")
    root.mkdir(parents=True, exist_ok=True)
    with (root / "collector.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        signal.signal(signal.SIGTERM, signal_stop)
        signal.signal(signal.SIGINT, signal_stop)
        marker = json.loads((root / "source" / "SOURCE.json").read_text())
        if marker["revision"] != REVISION:
            raise RuntimeError("Collector source revision mismatch")
        if marker.get("localPatch") != LOCAL_PATCH:
            raise RuntimeError("Collector concurrency patch mismatch")
        log("configuration", concurrency=CONCURRENCY, intervalMs=INTERVAL_MS,
            localPatch=LOCAL_PATCH, collectionPolicy=COLLECTION_POLICY)
        migrated = migrate_lanes(root)
        if migrated:
            log("historical-lanes-migrated", added=migrated)
        state_file = root / "supervisor.json"
        state = json.loads(state_file.read_text()) if state_file.exists() else {"turn": 0}
        failures = 0
        while not stop.is_set():
            before = status(root)
            schedule = active_schedule(before)
            available = [i for i in schedule if not before["ranges"][i]["done"]]
            if not available:
                log("range-scan-finished", **export(root))
                return
            turn = state["turn"]
            while before["ranges"][schedule[turn % len(schedule)]]["done"]:
                turn += 1
            start, end = RANGES[schedule[turn % len(schedule)]]
            try:
                preflight()
                if stop.wait(1.1):
                    break
                command = collector_command(root, start, end, request_limit)
                log("batch-start", start=start, end=end, requestLimit=request_limit,
                    concurrency=CONCURRENCY, intervalMs=INTERVAL_MS)
                child = subprocess.Popen(command, cwd=root, env=environment())
                code = child.wait()
                child = None
                after = export(root)
                log("batch-exported", returncode=code, **after)
                if code or (after["progressIds"] == before["progressIds"] and
                            after["sessions"] == before["sessions"]):
                    raise RuntimeError(f"Collector stalled or exited with code {code}; cursors retained")
                state["turn"] = turn + 1
                atomic_json(state_file, state)
                failures = 0
                if once:
                    return
                stop.wait(1.1)
            except Exception as error:
                if child is not None and child.poll() is None:
                    child.send_signal(signal.SIGINT)
                    child.wait(timeout=30)
                child = None
                if stop.is_set():
                    break
                failures += 1
                delay = min(60 * 2 ** min(failures - 1, 4), 900)
                log("backoff", error=str(error), seconds=delay)
                if once:
                    raise
                stop.wait(delay)
        if database(root).exists():
            export(root)
        log("stopped")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["run", "once", "status", "export", "preflight"])
    parser.add_argument("--root", type=Path, default=Path.home() / ".local/share/yanhe-session-index")
    parser.add_argument("--max-requests", type=int, default=300)
    args = parser.parse_args()
    if not 30 <= args.max_requests <= 3600:
        parser.error("--max-requests must be between 30 and 3600; at most 5 parallel requests, >= 200 ms global spacing")
    root = args.root.expanduser().resolve()
    os.umask(0o077)
    if args.command in {"run", "once"}:
        run(root, once=args.command == "once", request_limit=args.max_requests)
    elif args.command == "status":
        print(json.dumps(status(root), ensure_ascii=False, indent=2))
    elif args.command == "export":
        print(json.dumps(export(root), ensure_ascii=False))
    else:
        preflight()
        print("preflight OK: session 71990 belongs to course 9397")


if __name__ == "__main__":
    main()
