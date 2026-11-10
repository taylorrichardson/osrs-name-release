# OSRS Name Release Predictor

Ranks candidate display names by how likely they are to be freed in the November 2026
name release, rates how valuable each one is, and shows them in release order
(official 18-batch schedule, A on Thu Nov 5 through 6-9 on Mon Nov 30, 06:00 EST; the next batch is highlighted).

Only Python 3 is needed. There are no dependencies.

```
python nrp.py serve          # open http://127.0.0.1:8765
python nrp.py scan           # look up every name in wordlists/*.txt + all 1-2 char names (resumable)
python nrp.py scan --three-letter   # also every 3-letter name aaa-zzz (~90 min)
python nrp.py scan my.txt    # scan your own list (one name per line)
python nrp.py enrich         # RuneMetrics + Wise Old Man for the top 500 candidates (slow)
python nrp.py build          # rebuild web/data.json from data/cache.jsonl
```

Leave `serve` running while a scan is going and refresh the page: `data.json` is rebuilt every
1,000 names. The "Check any name live" box looks up any name on demand.

## Signals

| Source | Used for |
|---|---|
| OSRS hiscores | found or not, members-skill XP, Sailing XP (Sailing XP means active in the last year) |
| RS3 hiscores | found or not, members-skill XP |
| RuneMetrics | `NO_PROFILE` / `PROFILE_PRIVATE` / `NOT_A_MEMBER`, last RS3 activity date (heavily rate-limited, so only used for the top candidates) |
| Wise Old Man | `banned` status, last XP change (rate limit is 20 per minute) |

Release rule: inactive for 2+ years, AND (banned OR never a member OR bond-only membership that ended 5+ years ago).

**Caveat:** a name that isn't on any hiscore is either held by a hidden, low-level or banned
account (a good candidate), or it's **already free**. Check it in-game. These are estimates.

## Updating the batch schedule

The official schedule lives in `SCHEDULE` at the top of `web/app.js`. If Jagex moves a batch, edit its date there.

## After a batch releases: spot claimed names

```
python nrp.py recheck a      # letters of the batch that just opened, e.g. ef, yz012
```

This re-checks that batch's names on the OSRS hiscores and compares them with the pre-release snapshot:
**TAKEN** means a different account now has the name (newly ranked, or XP changed). **FREED** means the old
account vanished from the hiscores, so the name was released and may still be free. No badge means no visible
change: the name is either still free or was taken by an account too low-level to appear on the hiscores.
