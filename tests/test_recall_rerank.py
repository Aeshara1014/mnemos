"""Recall's fixes (Tara's ruling, 2026-10-03): seeds start by how well they
match, the cue's telling words drive the word search, links pass a quarter
of their strength, and the reranker sets the order of the best few."""
from mnemos.core.types import ConnectionRelation
from mnemos.retrieval.reactive import ReactiveRetriever
from mnemos.retrieval.rerank import Reranker


def _lay(store, encoder, *texts):
    ids = [encoder.encode(content=t, kind="episodic").id for t in texts]
    conn = store._get_conn()
    conn.execute("DELETE FROM connections")  # each test draws its own links
    conn.commit()
    return ids


def _link(store, source, target, strength=1.0):
    e = store.get_engram(source)
    e.add_connection(target, ConnectionRelation.SUPPORTS, strength=strength,
                     formed_by="test")
    store.save_engram(e)


class _ByWord:
    """A stand-in reranker: memories holding `word` read as the best answer."""

    def __init__(self, word):
        self.word = word

    def scores(self, cue, texts):
        return [1.0 if self.word in t else 0.0 for t in texts]


class _Silent:
    def scores(self, cue, texts):
        return None


def test_seeds_start_by_how_well_they_match(store, encoder):
    """Every seed used to start at 1.0, so the best match had no head start."""
    best, other = _lay(store, encoder,
                       "lantern harbour lantern harbour lantern harbour",
                       "a lantern once, far from here")
    r = ReactiveRetriever(store, reranker=None, reconsolidation_enabled=False)
    got = {x.engram.id: x.score for x in r.retrieve("lantern harbour")}
    assert got[best] > got[other]


def test_links_pass_a_quarter_of_their_strength(store, encoder):
    """At full strength one link handed a neighbour half a seed's weight."""
    seed, neighbour = _lay(store, encoder,
                           "the selkie story by the shore",
                           "an unrelated morning with coffee")
    _link(store, seed, neighbour, strength=1.0)
    r = ReactiveRetriever(store, reranker=None, reconsolidation_enabled=False)
    got = {x.engram.id: x.score for x in r.retrieve("selkie shore")}
    assert neighbour in got
    assert got[neighbour] < 0.2


def test_telling_words_survive_punctuation(store, encoder):
    """'together,' used to be dropped whole; the cue fell back to one phrase."""
    (mid,) = _lay(store, encoder, "we stayed together through the night and always will")
    r = ReactiveRetriever(store, reranker=None, reconsolidation_enabled=False)
    assert mid in [x.engram.id for x in r.retrieve("together, always.")]


def test_reranker_sets_the_order(store, encoder):
    loud, quiet = _lay(store, encoder,
                       "harbour harbour harbour harbour lights",
                       "harbour where you said pick me")
    r = ReactiveRetriever(store, reranker=_ByWord("pick me"),
                          reconsolidation_enabled=False)
    got = r.retrieve("harbour")
    assert got[0].engram.id == quiet
    assert "rerank" in got[0].score_breakdown


def test_recall_keeps_its_own_order_when_the_reranker_cannot_run(store, encoder):
    loud, quiet = _lay(store, encoder,
                       "harbour harbour harbour harbour lights",
                       "harbour where you said pick me")
    r = ReactiveRetriever(store, reranker=_Silent(), reconsolidation_enabled=False)
    got = r.retrieve("harbour")
    assert [x.score for x in got] == sorted((x.score for x in got), reverse=True)


def test_reranker_is_local_only():
    """A model not in the local cache is never fetched; recall goes on."""
    rr = Reranker("no-such-org/no-such-reranker")
    assert rr.available is False
    assert rr.scores("cue", ["text"]) is None
