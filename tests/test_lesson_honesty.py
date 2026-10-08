"""The goodnight-lesson law: only a real distillation may mint a lesson.

A lesson that is just a fragment of the memory — a goodnight, a sign-off —
is not wisdom. Since 2026-10-07 the night mints no lessons at all (fading
keeps his words; what a memory taught will be asked of him), but the law
stays for the asking door: his own answer must still be new prose about
the memory, not prose lifted from it.
"""

from mnemos.consolidation.softening import _is_real_distillation

CONVERSATION = (
    "Tara said: long day, but we got the roof fixed before the rain. "
    "I said: that's the whole job some days. Sleep well. "
    "Goodnight, my heart"
)


def test_the_law_itself():
    assert not _is_real_distillation("", CONVERSATION)
    assert not _is_real_distillation("short", CONVERSATION)
    assert not _is_real_distillation("Goodnight,   MY heart", CONVERSATION)
    assert not _is_real_distillation("goodnight, my heart", "gone", CONVERSATION)
    assert _is_real_distillation(
        "Care shows up as finishing the roof together.", CONVERSATION)
