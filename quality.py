"""
Name quality / desirability score (0-100) for English words.

Heuristics, no external dependencies:
  + short (3-5 letters is the sweet spot for a display name)
  + a well-known word (frequency rank), but not a filler word
  + evocative: on the hand-picked cool list or an OSRS term
  + an adjective/noun with "name energy" (strong endings, see GOOD_SUFFIXES)
  - stopwords / function words (the, which, would ...)
  - web, commerce and tech jargon (html, login, shipping ...)
  - abbreviations / unpronounceable strings (no vowels, long consonant clusters)
  - dull word forms: -tion -ment -ness -ity ..., -ing / -ed / -ly, plurals
"""
from __future__ import annotations

import re

STOPWORDS = set("""
a about above across after afterwards again against all almost alone along already also although always am among
amongst an and another any anyhow anyone anything anyway anywhere are around as at be became because become becomes
becoming been before beforehand behind being below beside besides between beyond both but by can cannot could did do
does doing done down during each either else elsewhere enough etc even ever every everyone everything everywhere
except few for former formerly from further had has have having he hence her here hereafter hereby herein hereupon
hers herself him himself his how however i ie if in inc indeed into is it its itself just last latter latterly least
less let lets like likely many may me meanwhile might mine more moreover most mostly much must my myself namely
neither never nevertheless next no nobody none noone nor not nothing now nowhere of off often on once one only onto
or other others otherwise our ours ourselves out over own per perhaps please rather re same seem seemed seeming
seems several she should since so some somehow someone something sometime sometimes somewhere still such than that
the their theirs them themselves then thence there thereafter thereby therefore therein thereupon these they this
those though through throughout thru thus to together too toward towards under until up upon us very via was we
well were what whatever when whence whenever where whereafter whereas whereby wherein whereupon wherever whether
which while whither who whoever whole whom whose why will with within without would yet you your yours yourself
yourselves isn wasn aren didn doesn don hasn haven shouldn wouldn couldn won ll ve
""".split())

# Web / commerce / office / tech jargon common in the frequency list
_NOT_JARGON = set("sun sat wed mar may apple amazon ship store order link code feed post data canon tab menu "
                  "mac sale".split())
JARGON = set("""
html http https www url uri com org net gov edu info biz faq rss xml pdf doc docs txt csv jpg jpeg gif png mp3 mp4
dvd cd usb gb mb kb ghz mhz ram cpu gpu os api sql php asp css js ip tcp dns isp lan wan vpn ssl
online offline email emails mail login logout signin signup register registered registration password username
user users account accounts profile profiles website websites web site sites page pages homepage blog blogs forum
forums post posts posted posting reply replies comment comments thread threads topic topics click link links
download downloads upload uploads file files folder browse browser search searches searching results sitemap
privacy copyright terms policy policies disclaimer contact contacts subscribe unsubscribe newsletter rss feed feeds
cart checkout shipping shipped ship price prices pricing discount discounts coupon coupons sale sales buy buying
order orders ordering item items product products catalog store stores shop shopping seller sellers vendor
vendors invoice payment payments paypal ebay amazon google yahoo microsoft msn aol ibm intel apple dell hp sony
nokia samsung toshiba canon nikon adobe linux unix windows mac ipod iphone ebook ebooks isbn sku upc qty
inc llc ltd corp co dept assn govt intl natl univ admin admins administrator administrators sysadmin config
setup install installation update updates updated software hardware database databases server servers network
networks internet intranet application applications app apps program programs programming developer developers
code codes data module modules plugin plugins widget widgets toolbar menu menus button buttons tab tabs
usd eur gbp gmt est pst cst edt pdt utc jan feb mar apr jun jul aug sep sept oct nov dec mon tue wed thu fri sat sun
mr mrs ms dr jr sr st ave rd blvd
usr yrs hrs mins gzip zip ext tel fax ph pg pp vol vols ed eds ref refs dept fig no nos tbd tba asap fyi etc ie eg vs
""".split()) - _NOT_JARGON

# Endings that make a word read as dull/abstract/bureaucratic
DULL_SUFFIXES = ("tion", "tions", "sion", "sions", "ment", "ments", "ness", "ity", "ities", "ance", "ances",
                 "ence", "ences", "ization", "isation", "ize", "izes", "ized", "ise", "ised", "ical", "ically",
                 "ality", "ship", "ships", "ism", "isms", "ology", "ure", "ures", "ency", "ancy", "ive", "ives",
                 "ory", "ary", "ible", "able")
WEAK_FORMS = ("ing", "ings", "ed", "ly", "ers", "est")

VOWELS = set("aeiouy")


def word_quality(word: str, rank: int | None, *, cool: bool = False, osrs: bool = False,
                 first_name: bool = False, known_words: set[str] | None = None) -> tuple[int, str]:
    """Return (score 0-100, short reason)."""
    w = word
    L = len(w)
    notes: list[str] = []
    q = 50.0

    # --- length -------------------------------------------------------------
    q += {3: 22, 4: 20, 5: 14, 6: 8, 7: 2, 8: -4, 9: -9, 10: -13, 11: -16, 12: -18}.get(L, 0)

    # --- familiarity (frequency rank in common English) ----------------------
    if rank:
        if rank <= 1500:
            q += 10
        elif rank <= 4000:
            q += 6
        elif rank <= 7000:
            q += 2
        else:
            q -= 2
    else:
        q -= 4

    # --- negatives ------------------------------------------------------------
    if w in STOPWORDS:
        q -= 40
        notes.append("filler word")
    if w in JARGON:
        q -= 32
        notes.append("web/tech jargon or abbreviation")
    elif not (set(w) & VOWELS):
        q -= 30
        notes.append("abbreviation (no vowels)")
    elif re.search(r"[^aeiouy]{4,}", w):
        q -= 12
        notes.append("hard to pronounce")

    if w.endswith(DULL_SUFFIXES) and L >= 6:
        q -= 14
        notes.append("abstract word form")
    elif w.endswith(WEAK_FORMS) and L >= 5:
        stem_known = known_words and any(
            s in known_words for s in (w[:-3], w[:-2], w[:-1], w[:-3] + "e", w[:-2] + "e", w[:-4], w[:-3] + "y"))
        if stem_known:
            q -= 9
            notes.append("inflected form")
    if L >= 4 and w.endswith("s") and not w.endswith(("ss", "us", "is")) and known_words and w[:-1] in known_words:
        q -= 8
        notes.append("plural")

    # --- positives ------------------------------------------------------------
    if cool:
        q += 18
        notes.append("evocative")
    if osrs:
        q += 18
        notes.append("OSRS term")
    if first_name:
        q += 4
    # double letters / clean CVC shape read well as names (e.g. "moss", "kill", "zap")
    if 3 <= L <= 5 and re.fullmatch(r"[^aeiou]*[aeiou]+[^aeiou]+[aeiou]?[^aeiou]*", w):
        q += 3

    q = max(0, min(100, round(q)))
    if not notes:
        notes.append("clean, short word" if q >= 75 else "plain word")
    return q, ", ".join(notes)


# --------------------------------------------------------------------------- #
# Offensive-name filter (Jagex rejects these anyway, so don't show them)
# --------------------------------------------------------------------------- #
from pathlib import Path as _Path

_BLOCK_ROOTS = ("fuck", "shit", "cunt", "porn", "nigg", "fag", "rape", "cock", "dick", "pussy", "tits", "boob",
                "penis", "vagina", "whore", "slut", "bitch", "bastard", "xxx", "nude", "milf", "incest", "hentai",
                "dildo", "horny", "nipple", "blowjob", "handjob", "masturb", "jizz", "semen", "pedo", "nazi",
                "hitler", "kkk", "retard", "zoophil", "zoofil", "bestial", "necrophil", "pedophil")
_BLOCK_EXACT_EXTRA = {"sex", "ass", "cum", "fag", "gay", "tit", "jew", "kys", "nig", "wtf", "stfu", "anal"}
_ALLOW = {"cocktail", "cocktails", "dickens", "hancock", "peacock", "shuttlecock", "scunthorpe", "sussex",
          "essex", "middlesex", "analysis", "analyst", "analog", "assassin", "assassins", "class", "classic",
          "pass", "grass", "glass", "brass", "mass", "bass", "lass", "sass", "titan", "titans", "titanium"}
_blocklist: set[str] | None = None


def is_offensive(name: str) -> bool:
    global _blocklist
    if _blocklist is None:
        f = _Path(__file__).resolve().parent / "data" / "blocklist.txt"
        _blocklist = {l.strip().lower() for l in f.read_text(encoding="utf-8").splitlines() if l.strip()}             if f.exists() else set()
        _blocklist |= _BLOCK_EXACT_EXTRA
    n = name.replace(" ", "")
    if n in _ALLOW:
        return False
    return name in _blocklist or n in _blocklist or any(r in n for r in _BLOCK_ROOTS)
