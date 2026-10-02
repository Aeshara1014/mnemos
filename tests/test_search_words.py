"""The telling words — Tara's ruling on the linking flaw (2026-10-02).

Before: the text was cut at spaces and any piece touching punctuation was
thrown away whole ("milestones," / "I've" / "*especially"), and the first
8 survivors were searched in order ("been", "one", "but"). Now: punctuation
is cleaned off, common words are skipped, the rarest words among his
memories are chosen, and encode-time linking also searches by meaning.
"""
import json

from mnemos.consolidation.connection_discovery import run_connection_discovery
from mnemos.core.engram import Engram
from mnemos.encoding.encoder import Encoder
from mnemos.retrieval.search_words import fold, plain_words, telling_words

DEC14 = ("Tara said: “I’ve never been one to really celebrate milestones, "
         "*especially in months*… but it feels different with you, Quill.")


def test_punctuation_is_cleaned_off_never_a_reason_to_drop_the_word():
    words = plain_words(DEC14)
    assert "milestones" in words and "especially" in words and "months" in words
    # the old step threw all three away
    old = [w for w in DEC14.split() if len(w) > 2 and w.isalnum()]
    assert not {"milestones", "especially", "months"} & {w.lower() for w in old}


def test_common_words_and_speaker_labels_are_skipped():
    words = plain_words(DEC14)
    for common in ("tara", "said", "been", "one", "really", "but", "with", "you"):
        assert common not in words
    assert words == list(dict.fromkeys(words))        # each once


def test_words_are_read_the_way_the_index_reads_them():
    assert fold("Ghràdh") == "ghradh"
    assert plain_words("mo ghràdh, mo chridhe") == ["ghradh", "chridhe"]


def test_the_rarest_words_his_memories_share_come_first(store):
    for text in ("we celebrate the croft tonight", "the croft again", "the croft, always",
                 "milestones matter to me", "the croft and the fire"):
        store.save_engram(Engram(content=text))
    picked = telling_words("celebrate milestones at the croft, foreverness", store)
    # 'foreverness' is held by no other memory: it can find nothing
    assert picked[:2] == ["celebrate", "milestones"] and picked[-1] == "croft"
    assert "foreverness" not in picked


class _Index:
    available = True

    def __init__(self, hits):
        self.hits = hits

    def search(self, text, k=10, exclude_ids=None):
        return [h for h in self.hits if h[0] not in (exclude_ids or set())]

    def index_engram(self, *a, **k):
        return True


class _Classifier:
    def __init__(self):
        self.users = []

    def structured_complete(self, system, user, **kw):
        self.users.append(user)
        return "[]"


def test_encoding_also_offers_the_memories_closest_in_meaning(store):
    near = Engram(content="Two months of mornings in the croft, and I'd find you in every life.")
    store.save_engram(near)
    llm = _Classifier()
    Encoder(store, embedding_index=_Index([(near.id, 0.82)]), llm_client=llm).encode(
        content="Tara said: lumen nocturne quietude", skip_surprise_detection=True)
    # no word is shared — only meaning could have offered it
    assert llm.users and near.id in llm.users[0]


def test_the_nightly_pass_searches_the_telling_words(store, monkeypatch):
    target = Engram(content=DEC14)
    other = Engram(content="We celebrate milestones by the fire.")
    store.save_engram(target)
    store.save_engram(other)
    queries = []
    real = store.search_fts

    def spy(query, limit=50):
        queries.append(query)
        return real(query, limit)

    monkeypatch.setattr(store, "search_fts", spy)
    run_connection_discovery(store, embedding_index=None, config={}, llm_client=None)
    assert any('"milestones"' in q and '"celebrate"' in q for q in queries)
    assert not any('"been"' in q or '"but"' in q for q in queries)
