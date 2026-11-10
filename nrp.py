#!/usr/bin/env python3
"""
OSRS Name Release Predictor
===========================

Scores candidate RuneScape display names by how likely they are to be freed in
the November 2026 name release, using public data only:

  * OSRS hiscores         (secure.runescape.com/m=hiscore_oldschool)
  * RS3 hiscores          (secure.runescape.com/m=hiscore)
  * RuneMetrics profile   (apps.runescape.com/runemetrics)  -> RS3 activity dates
  * Wise Old Man          (api.wiseoldman.net)              -> ban status / last XP change

Jagex's release criteria (from the news post):
  inactive >= 2 years AND (permanently banned OR never a member OR
  bond-only membership that ended >= 5 years ago)

None of this is directly visible, so the tool infers it from proxies
(see score()). Treat the output as a ranking, not a guarantee.

Usage
-----
  python nrp.py scan [wordlist ...]   # look up names (resumable, cached)
  python nrp.py build                 # rebuild web/data.json from the cache
  python nrp.py serve [--port 8765]   # web app + live single-name lookups
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from quality import is_offensive, word_quality

ROOT = Path(__file__).resolve().parent
CACHE_FILE = ROOT / "data" / "cache.jsonl"
WEB_DIR = ROOT / "web"
DATA_OUT = WEB_DIR / "data.json"
WORDLIST_DIR = ROOT / "wordlists"

UA = "osrs-name-release-predictor/1.0 (personal research script)"
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9 _-]{0,11}$")

OSRS_URL = "https://secure.runescape.com/m=hiscore_oldschool/index_lite.json?player={}"
RS3_URL = "https://secure.runescape.com/m=hiscore/index_lite.ws?player={}"
RM_URL = "https://apps.runescape.com/runemetrics/profile/profile?user={}&activities=20"
WOM_URL = "https://api.wiseoldman.net/v2/players/{}"

OSRS_MEMBER_SKILLS = {"Agility", "Herblore", "Thieving", "Fletching", "Slayer",
                      "Farming", "Construction", "Hunter", "Sailing"}
# RS3 index_lite order: 0 overall, 1 att, 2 def, 3 str, 4 hp, 5 range, 6 pray, 7 mage,
# 8 cook, 9 wc, 10 fletch, 11 fish, 12 fm, 13 craft, 14 smith, 15 mine, 16 herb,
# 17 agil, 18 thiev, 19 slay, 20 farm, 21 rc, 22 hunt, 23 con, 24 summ, 25 dung,
# 26 div, 27 invention, 28 arch, 29 necro
RS3_MEMBER_SKILL_IDX = [16, 17, 18, 19, 20, 22, 23, 24, 26, 27]

TWO_YEARS_DAYS = 730
NOW = lambda: datetime.now(timezone.utc)  # noqa: E731


# --------------------------------------------------------------------------- #
# HTTP helpers with rate limiting / retries
# --------------------------------------------------------------------------- #
class RateLimiter:
    def __init__(self, per_second: float):
        self.interval = 1.0 / per_second
        self.lock = threading.Lock()
        self.next_at = 0.0

    def wait(self):
        with self.lock:
            now = time.monotonic()
            if self.next_at > now:
                time.sleep(self.next_at - now)
                now = self.next_at
            self.next_at = now + self.interval

    def slow_down(self, seconds: float):
        with self.lock:
            self.next_at = max(self.next_at, time.monotonic() + seconds)


JAGEX_LIMIT = RateLimiter(6.0)      # hiscores: be polite, ~6 requests/second total
RM_LIMIT = RateLimiter(1 / 3)       # RuneMetrics 429s very quickly; ~1 request per 3s
WOM_LIMIT = RateLimiter(18 / 60)    # WOM allows 20/min without an API key


def http_get(url: str, limiter: RateLimiter, retries: int = 4) -> tuple[int, str]:
    """Return (status, body). 404 is a normal answer, not an error."""
    for attempt in range(retries + 1):
        limiter.wait()
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.status, resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return 404, ""
            if e.code in (403, 429, 500, 502, 503, 504) and attempt < retries:
                backoff = (15 if e.code == 429 else 5) * (attempt + 1)
                limiter.slow_down(backoff)
                continue
            return e.code, ""
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt < retries:
                limiter.slow_down(3 * (attempt + 1))
                continue
            return -1, ""
    return -1, ""


# --------------------------------------------------------------------------- #
# Source lookups
# --------------------------------------------------------------------------- #
def q(name: str) -> str:
    return urllib.parse.quote(name.replace(" ", "_"))


def lookup_osrs(name: str) -> dict:
    status, body = http_get(OSRS_URL.format(q(name)), JAGEX_LIMIT)
    if status == 404:
        return {"found": False}
    if status != 200:
        return {"error": status}
    try:
        d = json.loads(body)
    except json.JSONDecodeError:
        return {"error": "bad-json"}
    skills = {s["name"]: s for s in d.get("skills", [])}
    overall = skills.get("Overall", {})
    member_xp = sum(max(skills[s]["xp"], 0) for s in OSRS_MEMBER_SKILLS if s in skills)
    sailing = skills.get("Sailing", {}).get("xp", -1)
    acts = sum(max(a.get("score", -1), 0) for a in d.get("activities", []))
    return {
        "found": True,
        "total": overall.get("level", 0),
        "xp": overall.get("xp", 0),
        "member_xp": member_xp,
        "sailing_xp": max(sailing, 0),
        "activity_score": acts,
    }


def lookup_rs3(name: str) -> dict:
    status, body = http_get(RS3_URL.format(q(name)), JAGEX_LIMIT)
    if status == 404:
        return {"found": False}
    if status != 200:
        return {"error": status}
    rows = [line.split(",") for line in body.strip().splitlines()]
    try:
        total = int(rows[0][1])
        xp = int(rows[0][2])
        member_xp = sum(max(int(rows[i][2]), 0) for i in RS3_MEMBER_SKILL_IDX if i < len(rows))
    except (IndexError, ValueError):
        return {"error": "bad-csv"}
    return {"found": True, "total": total, "xp": xp, "member_xp": member_xp}


def lookup_runemetrics(name: str, retries: int = 6) -> dict:
    status, body = http_get(RM_URL.format(q(name)), RM_LIMIT, retries=retries)
    if status != 200:
        return {"error": status}
    try:
        d = json.loads(body)
    except json.JSONDecodeError:
        return {"error": "bad-json"}
    if "error" in d:
        return {"state": d["error"]}  # NO_PROFILE / PROFILE_PRIVATE / NOT_A_MEMBER
    last = None
    for a in d.get("activities", []):
        try:
            dt = datetime.strptime(a["date"], "%d-%b-%Y %H:%M").replace(tzinfo=timezone.utc)
        except (KeyError, ValueError):
            continue
        last = max(last, dt) if last else dt
    return {"state": "PUBLIC", "last_activity": last.isoformat() if last else None,
            "total": d.get("totalskill")}


def lookup_wom(name: str) -> dict:
    status, body = http_get(WOM_URL.format(q(name)), WOM_LIMIT, retries=2)
    if status == 404:
        return {"found": False}
    if status != 200:
        return {"error": status}
    try:
        d = json.loads(body)
    except json.JSONDecodeError:
        return {"error": "bad-json"}
    return {"found": True, "status": d.get("status"), "build": d.get("build"),
            "type": d.get("type"), "last_changed": d.get("lastChangedAt"),
            "updated": d.get("updatedAt")}


def lookup_jagex(name: str, with_rm: bool = False) -> dict:
    """Hiscores lookup (fast). RuneMetrics is strictly rate-limited, so it only runs
    when with_rm=True (live checks) or in the enrichment pass."""
    osrs = lookup_osrs(name)
    rec = {"name": name, "osrs": osrs, "fetched": NOW().isoformat()}
    if osrs.get("sailing_xp", 0) > 0:
        # Already proven active in the last year: skip the other lookups.
        rec["rs3"] = {"skipped": True}
        return rec
    rec["rs3"] = lookup_rs3(name)
    if with_rm:
        rec["rm"] = lookup_runemetrics(name, retries=1)
    return rec


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def _age_days(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (NOW() - dt).total_seconds() / 86400


def score(rec: dict) -> dict:
    """Return {score 0-100, tier, reasons[]} for a cached record."""
    o, r, m, w = rec.get("osrs", {}), rec.get("rs3", {}), rec.get("rm", {}), rec.get("wom")
    reasons: list[str] = []

    if any("error" in x for x in (o, r)):
        return {"score": None, "tier": "error", "reasons": ["Lookup failed, re-scan this name"]}

    # ---- hard "still active" signals --------------------------------------
    if o.get("sailing_xp", 0) > 0:
        return {"score": 2, "tier": "active",
                "reasons": ["Has Sailing XP (skill released Nov 2025), so active within the last year"]}
    rm_age = _age_days(m.get("last_activity"))
    if rm_age is not None and rm_age < TWO_YEARS_DAYS:
        return {"score": 2, "tier": "active",
                "reasons": [f"RS3 activity {int(rm_age)} days ago (RuneMetrics)"]}
    if w and w.get("found"):
        wc, wu = _age_days(w.get("last_changed")), _age_days(w.get("updated"))
        if w.get("status") == "banned":
            return {"score": 35, "tier": "unlikely",
                    "reasons": ["Wise Old Man flags this account as BANNED",
                                "Batch A: none of the 16 banned-flagged names were claimed (bans are probably too recent)"]}
        if wc is not None and wc < TWO_YEARS_DAYS:
            return {"score": 3, "tier": "active",
                    "reasons": [f"XP changed {int(wc)} days ago (Wise Old Man)"]}

    in_osrs, in_rs3 = o.get("found"), r.get("found")
    rm_state = m.get("state")
    member = o.get("member_xp", 0) > 0 or r.get("member_xp", 0) > 0

    # WOM-confirmed long inactivity (only meaningful if WOM checked recently)
    wom_inactive = False
    if w and w.get("found"):
        wc, wu = _age_days(w.get("last_changed")), _age_days(w.get("updated"))
        if wc is not None and wc >= TWO_YEARS_DAYS and wu is not None and wu < 120:
            wom_inactive = True
            reasons.append(f"No XP gained in {wc / 365:.1f} years (Wise Old Man)")

    if rm_age is not None:
        reasons.append(f"Last RS3 activity {rm_age / 365:.1f} years ago")

    if m.get("error"):
        reasons.append("RuneMetrics lookup was rate-limited")
    if not in_osrs and not in_rs3 and rm_state in ("PROFILE_PRIVATE", "PUBLIC", "NOT_A_MEMBER"):
        s = 15 if not member else 8
        reasons.insert(0, "Not on either hiscore, but RuneMetrics shows an account exists")
        reasons.append("Batch A: only 1% of names like this were claimed")
        if rm_state == "NOT_A_MEMBER":
            reasons.append("RuneMetrics reports NOT_A_MEMBER")
        if rm_age is not None and rm_age >= TWO_YEARS_DAYS:
            s += 5
        return {"score": s, "tier": tier_for(s), "reasons": reasons}
    if not in_osrs and not in_rs3:
        if rm_state == "NO_PROFILE":
            s = 85
            reasons.insert(0, "Not on any hiscores and no RuneMetrics profile")
            reasons.append("Batch A: about 25% of names like this were claimed within a day, "
                           "the strongest signal found")
        else:
            s = 62
            reasons.insert(0, "Not on OSRS or RS3 hiscores (RuneMetrics not checked yet)")
            reasons.append("Batch A: about half of these had no RuneMetrics profile and released well; "
                           "the rest almost never did")
        if w and w.get("found") and w.get("status") in ("unranked", "flagged", "archived"):
            reasons.append(f"Wise Old Man status: {w.get('status')}")
        return {"score": s, "tier": tier_for(s), "reasons": reasons}

    if member:
        s = 6
        reasons.insert(0, "Has members-only skill XP, so was a member at some point")
        reasons.append("Batch A: about 0.3% of ex-member names were claimed")
        if wom_inactive or (rm_age is not None and rm_age >= TWO_YEARS_DAYS * 2.5):
            s = 15
            reasons.append("Long inactive, could qualify if membership was bond-only and ended 5+ years ago")
        if o.get("total", 0) > 1500 or r.get("total", 0) > 1500:
            s -= 3
            reasons.append("High total level, so likely a valued account")
        return {"score": max(s, 3), "tier": tier_for(max(s, 3)), "reasons": reasons}

    # Free-to-play (never-member signals)
    s = 12
    reasons.insert(0, "On the hiscores with no members-only skill XP")
    reasons.append("Batch A: none of the 129 ranked free-to-play names were released "
                   "(still on the hiscores under the same name)")
    if rm_state == "NOT_A_MEMBER":
        reasons.append("RuneMetrics reports NOT_A_MEMBER")
    if wom_inactive:
        s += 10
    elif rm_age is not None and rm_age >= TWO_YEARS_DAYS:
        s += 6
    return {"score": s, "tier": tier_for(s), "reasons": reasons}


def tier_for(s: int) -> str:
    if s >= 70:
        return "likely"
    if s >= 40:
        return "possible"
    return "unlikely"


# --------------------------------------------------------------------------- #
# Cache + dataset
# --------------------------------------------------------------------------- #
_cache_lock = threading.Lock()


def normalize(name: str) -> str | None:
    n = re.sub(r"[_\-]", " ", name.strip().lower())
    n = re.sub(r"\s+", " ", n)
    return n if NAME_RE.match(n) else None


def load_cache() -> dict[str, dict]:
    cache: dict[str, dict] = {}
    if CACHE_FILE.exists():
        with CACHE_FILE.open(encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    prev = cache.get(rec["name"], {})
                    merged = {**prev, **rec}
                    # "added" = when this name was first looked up (never overwritten by re-checks)
                    merged["added"] = prev.get("added") or rec.get("fetched")
                    cache[rec["name"]] = merged
                except (json.JSONDecodeError, KeyError):
                    pass
    return cache


def append_cache(rec: dict):
    with _cache_lock:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with CACHE_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, separators=(",", ":")) + "\n")


# --------------------------------------------------------------------------- #
# Value (how desirable the name is, independent of release likelihood)
# --------------------------------------------------------------------------- #
_word_rank: dict[str, int] | None = None
_osrs_terms: set[str] | None = None
_cool: set[str] = set()
_first_names: set[str] = set()


def _read_set(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {n for line in path.read_text(encoding="utf-8").splitlines()
            if (n := normalize(line.split("#")[0]))}


def _load_value_lists():
    global _word_rank, _osrs_terms, _cool, _first_names
    if _word_rank is None:
        _word_rank, _osrs_terms = {}, set()
        common = WORDLIST_DIR / "common-words.txt"
        if common.exists():
            for i, line in enumerate(common.read_text(encoding="utf-8").splitlines()):
                n = normalize(line)
                if n and n not in _word_rank:
                    _word_rank[n] = i + 1  # 1 = most common English word
        _osrs_terms = _read_set(WORDLIST_DIR / "osrs-terms.txt")
        _cool = set().union(*(_read_set(p) for p in WORDLIST_DIR.glob("cool-words*.txt")))
        _first_names = _read_set(WORDLIST_DIR / "first-names.txt")


VALUE_LEVELS = ["low", "medium", "high", "extreme"]


def _tier(q: int) -> str:
    return "extreme" if q >= 78 else "high" if q >= 62 else "medium" if q >= 45 else "low"


def value(name: str) -> tuple[str, str, int]:
    """Return (level, reason, quality 0-100). Shorter, cleaner, more evocative = better."""
    _load_value_lists()
    L = len(name)
    letters = name.isalpha()
    if L == 1:
        return "extreme", "Single character", 100
    if L == 2:
        return ("extreme", "Two letters", 96) if letters else ("high", "Two characters", 80)
    if name.isdigit() and L <= 3:
        return "high", "Short number", 74
    if not letters and " " not in name:
        return "low", "Mixes letters and numbers", max(10, 40 - 3 * L)

    rank = _word_rank.get(name)
    is_word = rank or name in _cool or name in _osrs_terms or name in _first_names
    if is_word:
        q, why = word_quality(name.replace(" ", ""), rank, cool=name in _cool, osrs=name in _osrs_terms,
                              first_name=name in _first_names, known_words=_word_rank.keys())
        if " " in name:
            q, why = q - 15, why + ", contains a space"
        if L == 3 and letters:
            q = max(q, 62)  # any 3-letter name is rare
        q = max(0, min(100, q))
        return _tier(q), why[:1].upper() + why[1:], q
    if " " in name:
        return "low", "Contains a space", 25
    if L == 3:
        return "high", "Three letters", 66
    if L == 4:
        return "medium", "Four letters (not a word)", 48
    return "low", "Not a known word", max(5, 40 - 3 * L)


def name_types(name: str) -> list[str]:
    """Category tags for the UI's Type filter (a name can have several)."""
    _load_value_lists()
    t = []
    if len(name) <= 2:
        t.append("short")
    if len(name) == 3 and name.isalpha():
        t.append("three")
    if name in _osrs_terms:
        t.append("osrs")
    if name in _cool:
        t.append("cool")
    if name in _first_names:
        t.append("first")
    if name in _word_rank:
        t.append("word")
    if any(c.isdigit() for c in name):
        t.append("digits")
    if " " in name:
        t.append("space")
    return t


def compact(rec: dict) -> dict:
    sc = score(rec)
    val, val_why, quality = value(rec["name"])
    o, r, m, w = rec.get("osrs", {}), rec.get("rs3", {}), rec.get("rm", {}), rec.get("wom") or {}
    return {
        "n": rec["name"],
        "s": sc["score"],
        "t": sc["tier"],
        "why": sc["reasons"],
        "v": val,
        "vWhy": val_why,
        "q": quality,
        "types": name_types(rec["name"]),
        "osrs": o.get("total") if o.get("found") else None,
        "osrsM": bool(o.get("member_xp")),
        "rs3": r.get("total") if r.get("found") else None,
        "rs3M": bool(r.get("member_xp")),
        "rm": m.get("state"),
        "rmLast": m.get("last_activity"),
        "wom": (w.get("status") or "tracked") if w.get("found") else ("none" if w else None),
        "womChanged": w.get("last_changed"),
        "src": rec.get("src"),
        "at": rec.get("fetched"),
        "added": rec.get("added") or rec.get("fetched"),
        "post": (rec.get("post") or {}).get("status"),
        "postAt": (rec.get("post") or {}).get("checked"),
    }


def build_dataset(cache: dict[str, dict] | None = None):
    cache = cache if cache is not None else load_cache()
    allrows = [compact(rec) for rec in cache.values() if not is_offensive(rec["name"])]
    # only names with a real chance of releasing go to the web app (unlikely/active stay in the cache)
    rows = [r for r in allrows if r["t"] in ("likely", "possible")]
    # slim it down for phones: reason strings go in a shared table, empty fields are dropped
    texts: dict[str, int] = {}
    for r in rows:
        r["why"] = [texts.setdefault(w, len(texts)) for w in r["why"]]
        r["vWhy"] = texts.setdefault(r.get("vWhy") or "", len(texts))
        for k in [k for k, v in r.items() if v is None or v is False or v == []]:
            del r[k]
    tmp = DATA_OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"generated": NOW().isoformat(), "scanned": len(allrows),
                               "texts": list(texts), "names": rows},
                              separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, DATA_OUT)  # atomic: the page never sees a half-written file
    print(f"Wrote {len(rows)} likely/possible names (of {len(allrows)} scanned) -> {DATA_OUT}")


def read_wordlists(paths: list[Path]) -> dict[str, str]:
    """name -> source-list label"""
    out: dict[str, str] = {}
    for p in paths:
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            n = normalize(line.split("#")[0])
            if n and n not in out:
                out[n] = p.stem
    return out


def short_names(three_letter: bool = False) -> dict[str, str]:
    """Every 1- and 2-character name (the most sought-after names in the game),
    plus optionally every 3-letter a-z combination."""
    chars = "abcdefghijklmnopqrstuvwxyz0123456789"
    letters = chars[:26]
    out = {c: "1-2 chars" for c in chars}
    out.update({a + b: "1-2 chars" for a in chars for b in chars})
    if three_letter:
        for a in letters:
            for b in letters:
                for c in letters:
                    out.setdefault(a + b + c, "3 letters")
    return out


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def cmd_scan(args):
    paths = [Path(p) for p in args.wordlists] or sorted(WORDLIST_DIR.glob("*.txt"))
    names = {} if args.no_short else short_names(args.three_letter)
    # word lists take precedence as the source label (more informative)
    names.update(read_wordlists(paths))
    names = {n: s for n, s in names.items() if not is_offensive(n)}
    if args.max_len:
        names = {n: s for n, s in names.items() if len(n) <= args.max_len}

    cache = load_cache()
    todo = [n for n in names if n not in cache or "error" in json.dumps(
        {k: cache[n].get(k) for k in ("osrs", "rs3")})]
    # A-names first, since they are released first
    todo.sort(key=lambda n: (release_key(n), len(n), n))
    cached = len(names) - len(todo)
    if args.limit:
        todo = todo[: args.limit]
    print(f"{len(names)} candidate names, {cached} already cached, "
          f"{len(todo)} to look up (about {len(todo) * 1.7 / 6 / 60:.0f} min)")

    done = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(lookup_jagex, n): n for n in todo}
        for fut in as_completed(futs):
            rec = fut.result()
            rec["src"] = names[rec["name"]]
            rec.setdefault("added", cache.get(rec["name"], {}).get("added") or rec["fetched"])
            cache[rec["name"]] = rec
            append_cache(rec)
            done += 1
            if done % 100 == 0 or done == len(todo):
                rate = done / max(time.time() - t0, 1)
                print(f"  {done}/{len(todo)}  ({rate:.1f} names/s)", flush=True)
            if done % 1000 == 0:
                build_dataset(cache)

    build_dataset(cache)
    if not args.no_enrich:
        enrich_pass(cache, args.enrich_limit)
    build_dataset(cache)


def enrich_pass(cache: dict[str, dict], limit: int):
    """RuneMetrics + Wise Old Man for the best candidates. Both are slow
    (RuneMetrics ~20/min, WOM 20/min), so they run side by side on a shortlist."""
    def shortlist(field: str) -> list[str]:
        out = []
        for n, rec in cache.items():
            prev = rec.get(field)
            if prev is not None and "error" not in prev:
                continue
            sc = score(rec)
            if sc["tier"] in ("likely", "possible"):
                # first-wave names first, then the most likely, then the shortest
                out.append((release_key(n), -(sc["score"] or 0), len(n), n))
        return [t[-1] for t in sorted(out)[:limit]]

    def run(field: str, fn, rate_note: str):
        names = shortlist(field)
        if not names:
            return
        print(f"{field} enrichment: {len(names)} names ({rate_note})", flush=True)
        for i, n in enumerate(names, 1):
            res = fn(n)
            cache[n][field] = res
            append_cache({"name": n, field: res})
            if i % 25 == 0:
                print(f"  {field} {i}/{len(names)}", flush=True)
                build_dataset(cache)

    with ThreadPoolExecutor(max_workers=2) as ex:
        a = ex.submit(run, "rm", lookup_runemetrics, f"about {limit * 3 / 60:.0f} min")
        b = ex.submit(run, "wom", lookup_wom, f"about {limit / 18:.0f} min")
        a.result(); b.result()


def post_release_status(before: dict, now: dict) -> str:
    """Compare a name's pre-release OSRS hiscore entry with a fresh one.
      claimed   - a different account holds it now (newly ranked, or the XP changed / went down)
      freed     - was ranked before, now gone: the old holder lost the name (released, maybe still free)
      active    - same account, gained XP since our scan: the owner still plays, so it won't release
      unchanged - same as before (still free, or claimed by an account too low to rank)
    """
    if "error" in now or not before or "error" in before:
        return "error"
    if not before.get("found"):
        return "claimed" if now.get("found") else "unchanged"
    if not now.get("found"):
        return "freed"
    b_xp, n_xp = before.get("xp") or 0, now.get("xp") or 0
    if n_xp == b_xp:
        return "unchanged"
    # same account kept playing: XP only goes up and the total level barely moves
    if n_xp > b_xp and abs((now.get("total") or 0) - (before.get("total") or 0)) <= 15 and b_xp > 0:
        return "active"
    return "claimed"  # XP went down or jumped to a different account's stats


def cmd_recheck(args):
    """After a batch is released, re-query the OSRS hiscores for its names to spot claimed ones."""
    cache = load_cache()
    letters = tuple(args.prefix.lower())
    names = [n for n, rec in cache.items()
             if n.startswith(letters) and not is_offensive(n) and score(rec)["tier"] != "active"]
    names.sort(key=lambda n: (len(n), n))
    print(f"Re-checking {len(names)} names starting with {', '.join(letters)} "
          f"(about {len(names) / 6 / 60:.0f} min)", flush=True)
    counts: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(lookup_osrs, n): n for n in names}
        for i, fut in enumerate(as_completed(futs), 1):
            n = futs[fut]
            now = fut.result()
            st = post_release_status(cache[n].get("osrs"), now)
            post = {"status": st, "checked": NOW().isoformat(), "osrs": now}
            cache[n]["post"] = post
            append_cache({"name": n, "post": post})
            counts[st] = counts.get(st, 0) + 1
            if i % 200 == 0 or i == len(names):
                print(f"  {i}/{len(names)}  {counts}", flush=True)
    build_dataset(cache)


def release_key(name: str) -> int:
    c = name[0]
    return ord(c) - ord("a") if c.isalpha() else 26  # digits come last


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(WEB_DIR), **kw)

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")  # always pick up edited files / new data
        super().end_headers()

    def log_message(self, fmt, *args):
        if "/api/" in (args[0] if args else ""):
            sys.stderr.write("%s\n" % (fmt % args))

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/check":
            qs = urllib.parse.parse_qs(parsed.query)
            name = normalize(qs.get("name", [""])[0])
            if not name:
                return self._json(400, {"error": "Names are 1-12 letters, numbers, spaces, - or _"})
            rec = lookup_jagex(name, with_rm=True)
            if qs.get("wom", ["1"])[0] == "1":
                rec["wom"] = lookup_wom(name)
            # keep the existing list source / value context if this name was scanned before
            prev = load_cache().get(name, {})
            rec["src"] = prev.get("src") or "manual"
            append_cache(rec)
            return self._json(200, compact(rec))
        return super().do_GET()

    def _json(self, code: int, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def cmd_serve(args):
    if not DATA_OUT.exists():
        build_dataset()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Serving on http://127.0.0.1:{args.port}  (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan", help="look up candidate names")
    s.add_argument("wordlists", nargs="*", help="text files, one name per line (default: wordlists/*.txt)")
    s.add_argument("--limit", type=int, help="only look up this many new names")
    s.add_argument("--max-len", type=int, help="skip names longer than this")
    s.add_argument("--no-short", action="store_true", help="skip the built-in 1-2 character names")
    s.add_argument("--three-letter", action="store_true",
                   help="also scan every 3-letter name aaa-zzz (17,576 names, ~90 min)")
    s.add_argument("--no-enrich", action="store_true", help="skip the RuneMetrics/Wise Old Man pass")
    s.add_argument("--enrich-limit", type=int, default=500,
                   help="how many top candidates get RuneMetrics + Wise Old Man lookups (~20/min)")
    s.set_defaults(func=cmd_scan)
    b = sub.add_parser("build", help="rebuild web/data.json from cache")
    b.set_defaults(func=lambda a: build_dataset())
    v = sub.add_parser("serve", help="run the web app")
    v.add_argument("--port", type=int, default=8765)
    v.set_defaults(func=cmd_serve)
    e = sub.add_parser("enrich", help="only run the RuneMetrics/Wise Old Man pass on cached names")
    e.add_argument("--limit", type=int, default=500)
    e.set_defaults(func=lambda a: (lambda c: (enrich_pass(c, a.limit), build_dataset(c)))(load_cache()))
    r = sub.add_parser("recheck", help="after a batch releases, re-check its names to spot claimed ones")
    r.add_argument("prefix", help="starting letters of the released batch, e.g. a  or  ef")
    r.set_defaults(func=cmd_recheck)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
