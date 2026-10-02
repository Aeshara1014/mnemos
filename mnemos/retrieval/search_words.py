"""The telling words of a memory — what a word search should look for.

Tara's ruling (2026-10-02, the linking flaw). Every memory's first links were
found by a word search built from "the first 8 words with no punctuation
attached": the text was cut at spaces and any piece touching punctuation was
thrown away whole ("milestones," / "I've" / "*especially" / the last word of
every sentence) — 24–29% of the words — and the survivors were taken in order,
so "been", "one" and "but" counted as much as "celebrate". Her four changes:

1. clean punctuation off a word instead of dropping it — the words are read
   the way the store's own full-text index reads them (letters and digits,
   accents folded), so what we ask for is exactly what it can find;
2. skip the common little words;
3. pick the most telling words: the rarest among his memories (a word only
   this memory holds can find nothing, so it is passed over);
4. (in the callers) search by meaning beside the words.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

MAX_WORDS = 8

_TOKEN = re.compile(r"[^\W_]+")

# The common little words — function words and the speaker labels every
# exchange carries ("Tara said: … / I said: …"). Kept short on purpose:
# rarity does the real choosing once a store has memories to count.
COMMON = frozenset("""
a about above after again against all also am an and any are aren as at be
because been before being below between both but by can cannot could couldn
did didn do does doesn doing don down during each even ever every few for from
further get gets got had hadn has hasn have haven having he her here hers
herself him himself his how i if in into is isn it its itself just let like
ll me more most much must my myself no nor not now of off on once one only or
other our ours ourselves out over own re really s said same say says she should
shouldn so some still such t than that the their theirs them themselves then
there these they this those through to too under until up us ve very was wasn
way we well were weren what when where which while who whom why will with
won would wouldn yeah yes yet you your yours yourself yourselves
tara
""".split())


def fold(word: str) -> str:
    """A word as the full-text index stores it: lowercase, accents folded
    (its unicode61 tokenizer removes diacritics — "ghràdh" is "ghradh")."""
    decomposed = unicodedata.normalize("NFKD", word.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def plain_words(text: str) -> list[str]:
    """Every word of three letters or more, punctuation cleaned off (never a
    reason to drop the word), common words and bare numbers skipped, each
    once, in the order they first appear — folded the index's way."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in _TOKEN.findall(text or ""):
        word = fold(raw)
        if len(word) < 3 or word.isdigit() or word in COMMON or word in seen:
            continue
        seen.add(word)
        out.append(word)
    return out


def telling_words(text: str, store: Any = None, limit: int = MAX_WORDS) -> list[str]:
    """The words worth searching for: the rarest among the store's memories
    that at least one other memory holds. Without a store that can count
    (or before it has anything), the plain words in order."""
    words = plain_words(text)
    counts = None
    if store is not None and hasattr(store, "term_doc_counts"):
        try:
            counts = store.term_doc_counts(words)
        except Exception:  # noqa: BLE001 — a count failure falls back, never breaks encoding
            counts = None
    if not counts:
        return words[:limit]
    found = [w for w in words if counts.get(w, 0) >= 1]
    order = {w: i for i, w in enumerate(words)}
    found.sort(key=lambda w: (counts[w], order[w]))
    return found[:limit]


def fts_query(words: list[str]) -> str:
    """An OR query the full-text index accepts (each word quoted)."""
    return " OR ".join(f'"{w}"' for w in words)
