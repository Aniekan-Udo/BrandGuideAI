"""What a brand repeats word for word, and which spelling it writes in.

Counted in code from the brand's own voice documents, like the rest of the
VOICE SPEC.

The Brain is built never to quote the brand's sentences: the synthesis is
stripped of quotations and the voice spec describes shapes, so the writer
cannot reassemble past posts. That is right for sentences and wrong for the
few phrases a brand repeats on purpose. Observed: a brand that ended all three
of its posts with "Rinse. Refill. Repeat." and opened a turn with "Here's the
thing." in each got a Brain saying only "end with a rhythmic chain of 3-4
imperative verbs", and its draft ended "Bring. Fill. Tap. Go." The same Brain
never recorded that the brand writes British English, and the draft said
"colorful", "realize" and "math".

A phrase that recurs verbatim across most of a brand's documents is a brand
fixture, not source text, so it is recorded exactly and marked for reuse.
"""
from __future__ import annotations

import math
import re
from typing import Iterable, Optional

# How many of the brand's documents must share a phrase before it counts as a
# fixture rather than a coincidence.
MIN_DOCUMENTS = 2
# A sign-off is enforced in code, so it needs to be the brand's habit, not
# merely something it has done twice.
SIGN_OFF_SHARE = 0.6
MAX_PHRASE_WORDS = 10
MAX_PHRASES = 5

_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})
_WORD = re.compile(r"[A-Za-z0-9']+")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_MARKUP = re.compile(r"^[\s>*_#\-•]+|[\s*_]+$")


def normalise(text: str) -> str:
    """The comparison form of a phrase: straight quotes, single spaces, no markup."""
    text = _MARKUP.sub("", text.translate(_QUOTES))
    return re.sub(r"\s+", " ", text).strip()


def _key(text: str) -> str:
    return normalise(text).lower()


def _lines(document: str) -> list[str]:
    return [normalise(line) for line in document.splitlines() if normalise(line)]


def _units(document: str) -> set[str]:
    """Whole short lines, and sentences of two words or more, as written."""
    units = set()
    for line in _lines(document):
        if 2 <= len(_WORD.findall(line)) <= MAX_PHRASE_WORDS:
            units.add(line)
        for sentence in _SENTENCE_SPLIT.split(line):
            if 2 <= len(_WORD.findall(sentence)) <= MAX_PHRASE_WORDS // 2 + 3:
                units.add(sentence.strip())
    return units


# ---------------------------------------------------------------------------
#  Spelling
# ---------------------------------------------------------------------------
def _spelling_pairs() -> dict[str, str]:
    """British form -> American form, for words that are spelled differently.

    Only words with a single correct spelling on each side. "Practise",
    "licence", "programme", "meter" and "tyre" are left out because each is also
    a correct word on the other side of the Atlantic, in another sense.
    """
    pairs: dict[str, str] = {}

    our = ["col", "fav", "flav", "behavi", "neighb", "hon", "hum", "lab", "harb", "rum",
           "vap", "endeav", "sav", "arm", "clam", "od", "vig", "parl", "splend"]
    # Not "-ous", "-ary" or "-ious": humorous, honorary and laborious are
    # spelled without the u in British English too.
    for stem in our:
        for suffix in ("", "s", "ed", "ing", "ful", "fully", "ite", "ites", "able", "ably",
                       "less", "hood"):
            pairs[f"{stem}our{suffix}"] = f"{stem}or{suffix}"

    ise = ["real", "organ", "recogn", "apolog", "priorit", "minim", "maxim", "custom",
           "emphas", "special", "final", "optim", "standard", "summar", "categor", "critic",
           "util", "visual", "author", "memor", "symbol", "normal", "personal", "central",
           "character", "mobil", "stabil", "capital", "general", "modern", "neutral",
           "legal", "local", "commercial", "energ", "harmon", "sympath", "agon", "patron",
           "fertil", "steril", "global", "monopol", "subsid", "dramat", "item", "sanit",
           "fantas", "trivial", "civil", "human", "colon", "familiar", "revolution"]
    for stem in ise:
        for uk, us in (("ise", "ize"), ("ised", "ized"), ("ises", "izes"), ("ising", "izing"),
                       ("isation", "ization"), ("isations", "izations"),
                       ("iser", "izer"), ("isers", "izers")):
            pairs[stem + uk] = stem + us

    # Not "-yses": "analyses" is also the plural of "analysis" on both sides.
    for stem in ("analy", "paraly", "catal", "dialy", "electroly"):
        for uk, us in (("yse", "yze"), ("ysed", "yzed"), ("ysing", "yzing")):
            pairs[stem + uk] = stem + us

    for stem in ("cent", "lit", "fib", "theat", "somb", "spect", "lust", "sab"):
        for uk, us in (("re", "er"), ("res", "ers"), ("red", "ered"), ("ring", "ering")):
            pairs[stem + uk] = stem + us

    for stem in ("travel", "cancel", "label", "model", "fuel", "level", "signal", "channel",
                 "counsel", "dial", "duel", "equal", "marvel", "panel", "quarrel", "total",
                 "tunnel"):
        for uk, us in (("led", "ed"), ("ling", "ing"), ("ler", "er"), ("lers", "ers")):
            pairs[stem + uk] = stem + us

    pairs.update({
        "grey": "gray", "greys": "grays", "greyish": "grayish", "maths": "math",
        "aluminium": "aluminum", "catalogue": "catalog", "catalogues": "catalogs",
        "defence": "defense", "defences": "defenses", "offence": "offense",
        "offences": "offenses", "mould": "mold", "moulds": "molds", "mouldy": "moldy",
        "plough": "plow", "ploughs": "plows", "pyjamas": "pajamas",
        "jewellery": "jewelry", "marvellous": "marvelous", "manoeuvre": "maneuver",
        "manoeuvres": "maneuvers", "sceptical": "skeptical", "sceptic": "skeptic",
        "sceptics": "skeptics", "paediatric": "pediatric",
    })
    return pairs


UK_TO_US = _spelling_pairs()
US_TO_UK = {us: uk for uk, us in UK_TO_US.items()}
_ANY_WORD = re.compile(r"[A-Za-z]+")


def spelling_evidence(text: str) -> tuple[list[str], list[str]]:
    """The British-only and American-only words in a text, in order seen."""
    uk, us = [], []
    for word in _ANY_WORD.findall(text):
        lower = word.lower()
        if lower in UK_TO_US:
            uk.append(lower)
        elif lower in US_TO_UK:
            us.append(lower)
    return uk, us


def spelling_variety(documents: Iterable[str]) -> tuple[Optional[str], list[str]]:
    """'british', 'american' or None, with the words that decided it.

    Needs at least two words of one kind and clear dominance over the other, so
    a brand that simply never uses a word that differs is left undecided.
    """
    uk, us = spelling_evidence("\n".join(documents))
    if len(uk) >= 2 and len(uk) >= 3 * len(us):
        return "british", sorted(set(uk))
    if len(us) >= 2 and len(us) >= 3 * len(uk):
        return "american", sorted(set(us))
    return None, []


def _with_case(replacement: str, original: str) -> str:
    if original.isupper() and len(original) > 1:
        return replacement.upper()
    if original[0].isupper():
        return replacement[0].upper() + replacement[1:]
    return replacement


def respell(content: str, variety: str, protected: Iterable[str] = ()) -> tuple[str, list[str]]:
    """Rewrite the other variety's spellings into the brand's own.

    `protected` holds words (lower case) to leave alone, such as a capitalised
    name in the source material: "Color Run" is an event, not a spelling.
    Returns the new text and the changes made, as "from -> to".
    """
    table = US_TO_UK if variety == "british" else UK_TO_US if variety == "american" else None
    if not table:
        return content, []
    keep = {w.lower() for w in protected}
    changes: list[str] = []

    def swap(match: re.Match) -> str:
        word = match.group(0)
        target = table.get(word.lower())
        if not target or word.lower() in keep:
            return word
        new = _with_case(target, word)
        changes.append(f"{word} -> {new}")
        return new

    return _ANY_WORD.sub(swap, content), changes


# ---------------------------------------------------------------------------
#  Fixtures
# ---------------------------------------------------------------------------
def measure_fixtures(documents: Iterable[str]) -> dict:
    """The brand's sign-off, its other repeated phrases and its spelling."""
    documents = [d for d in documents if d and d.strip()]
    n = len(documents)
    variety, words = spelling_variety(documents)
    result = {"documents": n, "sign_off": None, "sign_off_count": 0, "phrases": [],
              "spelling": variety, "spelling_evidence": words[:6]}
    if n < MIN_DOCUMENTS:
        return result
    needed = max(MIN_DOCUMENTS, math.ceil(n / 2))

    # The sign-off: the same last line, word for word, on most documents.
    last: dict[str, list[str]] = {}
    for document in documents:
        lines = _lines(document)
        if lines and 1 <= len(_WORD.findall(lines[-1])) <= MAX_PHRASE_WORDS:
            last.setdefault(_key(lines[-1]), []).append(lines[-1])
    if last:
        key, forms = max(last.items(), key=lambda kv: len(kv[1]))
        if len(forms) >= MIN_DOCUMENTS and len(forms) / n >= SIGN_OFF_SHARE:
            result["sign_off"] = max(set(forms), key=forms.count)
            result["sign_off_count"] = len(forms)

    # Other phrases repeated word for word across documents.
    seen: dict[str, list[str]] = {}
    for document in documents:
        for unit in _units(document):
            seen.setdefault(_key(unit), []).append(unit)
    sign_off_key = _key(result["sign_off"]) if result["sign_off"] else None
    phrases = [
        (max(set(forms), key=forms.count), len(forms))
        for key, forms in seen.items()
        if len(forms) >= needed and key != sign_off_key
        and not (sign_off_key and key in sign_off_key)
    ]
    # Longer phrases first, then the more widespread: a shared three-word line
    # says more about a brand than a shared two-word one.
    phrases.sort(key=lambda p: (-p[1], -len(_WORD.findall(p[0]))))
    result["phrases"] = phrases[:MAX_PHRASES]
    return result


SIGN_OFF_LABEL = "- SIGN-OFF:"
SPELLING_LABEL = "- SPELLING:"


def render_fixtures(fixtures: dict) -> list[str]:
    """Lines for the VOICE SPEC. Empty when nothing was found."""
    n = fixtures.get("documents", 0)
    lines: list[str] = []
    if fixtures.get("sign_off"):
        lines.append(f'{SIGN_OFF_LABEL} "{fixtures["sign_off"]}" ends {fixtures["sign_off_count"]} '
                     f"of {n} documents. End the piece with exactly this line.")
    for phrase, count in fixtures.get("phrases") or []:
        lines.append(f'- REPEATED PHRASE: "{phrase}" appears in {count} of {n} documents. '
                     "Use it where it fits, exactly as written.")
    if fixtures.get("spelling"):
        name = "British" if fixtures["spelling"] == "british" else "American"
        other = "American" if name == "British" else "British"
        seen = ", ".join(fixtures.get("spelling_evidence") or [])
        lines.append(f"{SPELLING_LABEL} {name} English (seen: {seen}). "
                     f"Never {other} spellings.")
    if not lines:
        return []
    return [
        "BRAND FIXTURES (repeated word for word across this brand's documents). Unlike its other "
        "sentences, these are the brand's own signatures, so reuse them exactly:",
        *lines,
    ]


def sign_off_from(metrics: str) -> Optional[str]:
    """The sign-off recorded in a Brand Brain's VOICE SPEC, if any."""
    match = re.search(re.escape(SIGN_OFF_LABEL) + r'\s*"(.+?)" ends \d+ of \d+ documents', metrics or "")
    return match.group(1) if match else None


def spelling_from(metrics: str) -> Optional[str]:
    """'british' or 'american', as recorded in a Brand Brain's VOICE SPEC."""
    match = re.search(re.escape(SPELLING_LABEL) + r"\s*(British|American) English", metrics or "")
    return match.group(1).lower() if match else None


def ends_with_sign_off(content: str, sign_off: str) -> bool:
    """Whether a draft's last line ends with the sign-off, ignoring markup and case."""
    lines = _lines(content)
    return bool(lines) and _key(lines[-1]).endswith(_key(sign_off))


def last_line(content: str) -> str:
    lines = _lines(content)
    return lines[-1] if lines else ""
