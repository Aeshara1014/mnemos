"""
Substrate affinity: ensure the mind that maintains the memories is kin to
the mind that lives them.

Mnemos's consolidation passes (softening, belief review, reflection, dreaming)
rewrite an agent's memories between sessions. When those passes run on a
different model than the agent itself, a foreign mind is performing the
agent's sleep — softening its memories in another voice, stress-testing its
beliefs with another prior, narrating its identity from outside.

This module enforces a configurable affinity policy between the agent's
runtime model and the substrate (maintenance) model:

    strict  — substrate model must be the exact same model as the agent
    family  — substrate model must belong to the same model family (default)
    open    — any substrate model is permitted (mismatches are logged)

Configuration (env vars or .env, consistent with the rest of Mnemos):

    MNEMOS_AGENT_MODEL          the model that lives the sessions
                                e.g. "claude-opus-4-6", "gpt-5.2"
    MNEMOS_SUBSTRATE_AFFINITY   strict | family | open   (default: family)

Failure behavior is graceful by design: when a policy blocks the substrate
client, Mnemos falls back to rule-based local maintenance. Baseline
continuity is never interrupted. Better no dreaming than a stranger
dreaming for you.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

log = logging.getLogger("mnemos.affinity")

VALID_POLICIES = ("strict", "family", "open")
DEFAULT_POLICY = "family"

# Ordered: more specific markers first. Each entry is (regex, family).
# Matching runs against the normalized model id with any provider prefix
# (e.g. "anthropic/", "openai/", "google/") stripped.
_FAMILY_MARKERS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"claude"), "claude"),
    (re.compile(r"chatgpt|gpt[-_0-9]|^gpt$|^o[1-9][-_.]|^o[1-9]$|davinci"), "gpt"),
    (re.compile(r"gemini"), "gemini"),
    (re.compile(r"gemma"), "gemma"),
    (re.compile(r"llama"), "llama"),
    (re.compile(r"qwen|qwq"), "qwen"),
    (re.compile(r"mistral|mixtral|ministral|magistral|codestral"), "mistral"),
    (re.compile(r"deepseek"), "deepseek"),
    (re.compile(r"grok"), "grok"),
    (re.compile(r"command[-_ ]?r|^command"), "command"),
    (re.compile(r"kimi|moonshot"), "kimi"),
    (re.compile(r"glm|chatglm"), "glm"),
    (re.compile(r"\bphi[-_0-9]"), "phi"),
    (re.compile(r"\bnova[-_]"), "nova"),
    (re.compile(r"hermes"), "hermes"),
]


def normalize_model_id(model: str | None) -> str:
    """Lowercase, trim, and strip provider prefixes from a model string.

    "anthropic/claude-sonnet-4-5"  -> "claude-sonnet-4-5"
    "openrouter/openai/gpt-5"      -> "gpt-5"
    """
    if not model:
        return ""
    m = model.strip().lower()
    # Strip any number of provider prefixes ("anthropic/", "openai/", ...).
    while "/" in m:
        m = m.split("/", 1)[1]
    return m


def model_family(model: str | None) -> str:
    """Detect the family of a model string. Returns "unknown" if undetected."""
    m = normalize_model_id(model)
    if not m:
        return "unknown"
    for pattern, family in _FAMILY_MARKERS:
        if pattern.search(m):
            return family
    return "unknown"


@dataclass
class AffinityCheck:
    """Result of a substrate affinity evaluation."""

    allowed: bool
    policy: str
    agent_model: str
    substrate_model: str
    agent_family: str
    substrate_family: str
    message: str

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "policy": self.policy,
            "agent_model": self.agent_model,
            "substrate_model": self.substrate_model,
            "agent_family": self.agent_family,
            "substrate_family": self.substrate_family,
            "message": self.message,
        }


def check_affinity(
    agent_model: str | None,
    substrate_model: str | None,
    policy: str = DEFAULT_POLICY,
) -> AffinityCheck:
    """Evaluate whether a substrate model may maintain an agent's memories.

    Semantics:
    - Unknown policy values fall back to "family" with a warning.
    - If the agent model is unset, affinity cannot be enforced: allow,
      with a message asking the operator to set MNEMOS_AGENT_MODEL.
    - "open": always allowed; mismatches are reported in the message.
    - "family": same detected family required. If either family is
      undetectable, allow with a warning (cannot enforce what cannot
      be detected) — but a *detected* mismatch blocks.
    - "strict": exact normalized model id match required.
    """
    pol = (policy or DEFAULT_POLICY).strip().lower()
    if pol not in VALID_POLICIES:
        log.warning("Unknown MNEMOS_SUBSTRATE_AFFINITY %r; using %r", policy, DEFAULT_POLICY)
        pol = DEFAULT_POLICY

    a_norm = normalize_model_id(agent_model)
    s_norm = normalize_model_id(substrate_model)
    a_fam = model_family(agent_model)
    s_fam = model_family(substrate_model)

    def result(allowed: bool, message: str) -> AffinityCheck:
        return AffinityCheck(
            allowed=allowed,
            policy=pol,
            agent_model=a_norm,
            substrate_model=s_norm,
            agent_family=a_fam,
            substrate_family=s_fam,
            message=message,
        )

    if not a_norm:
        return result(
            True,
            "Agent model unknown — affinity unenforced. Set MNEMOS_AGENT_MODEL "
            "to the model that lives this agent's sessions so substrate "
            "affinity can be honored.",
        )

    if not s_norm:
        # No substrate model resolvable; nothing to gate.
        return result(True, "No substrate model configured.")

    if pol == "open":
        if a_fam != s_fam:
            return result(
                True,
                f"Affinity policy 'open': substrate family '{s_fam}' differs "
                f"from agent family '{a_fam}'. A different mind is performing "
                f"this agent's maintenance.",
            )
        return result(True, "Affinity policy 'open': permitted.")

    if pol == "strict":
        if a_norm == s_norm:
            return result(True, "Strict affinity satisfied: same model.")
        return result(
            False,
            f"Strict affinity violated: agent runs '{a_norm}' but substrate "
            f"would run '{s_norm}'. Deep maintenance disabled; rule-based "
            f"local passes will run instead. Set MNEMOS_MODEL to '{a_norm}' "
            f"or relax MNEMOS_SUBSTRATE_AFFINITY.",
        )

    # pol == "family"
    if a_fam == "unknown" or s_fam == "unknown":
        return result(
            True,
            f"Family affinity unenforceable: agent family '{a_fam}', substrate "
            f"family '{s_fam}'. Proceeding — consider using recognizable model "
            f"ids so kinship can be verified.",
        )
    if a_fam == s_fam:
        return result(True, f"Family affinity satisfied: both '{a_fam}'.")
    return result(
        False,
        f"Family affinity violated: agent is '{a_fam}' ('{a_norm}') but the "
        f"substrate would be '{s_fam}' ('{s_norm}'). A different model family "
        f"must not rewrite this agent's memories. Deep maintenance disabled; "
        f"rule-based local passes will run instead. Point MNEMOS_MODEL at a "
        f"'{a_fam}' model or set MNEMOS_SUBSTRATE_AFFINITY=open to override.",
    )
