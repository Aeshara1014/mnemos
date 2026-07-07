"""
llm.py — Shared LLM calling utility for the Mnemos substrate.

Single source of truth for API key resolution and model calls.
Reads configuration from SubstrateConfig or environment variables.
"""

import json
import os
import time
from pathlib import Path
from typing import Optional


def get_api_key() -> tuple[str, str]:
    """Find API key from the environment. Returns (key, provider).

    Environment variables only. This deliberately does NOT read credentials
    from ambient config files (``~/.openclaw/*`` or ``~/.mnemos/config.json``):
    a substrate must never silently acquire a cloud key it wasn't explicitly
    handed. No env key -> no key -> the caller degrades to a rule-based pass.
    """
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if key:
        return key, "openrouter"

    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        return key, "anthropic"

    return "", ""


MODEL_MAP = {
    "flash": "google/gemini-2.5-flash",
    "flash-lite": "google/gemini-2.5-flash-lite",
    "gemini-pro": "google/gemini-3.1-pro-preview",
    "deepseek": "deepseek/deepseek-v3.2",
    "minimax": "minimax/minimax-m2.5",
    "haiku": "anthropic/claude-haiku-4-5",
    "sonnet": "anthropic/claude-sonnet-4-6",
    "opus": "anthropic/claude-opus-4-6",
    "kimi": "moonshotai/kimi-k2.5",
}


def call_llm(prompt: str, system: str = "", temperature: float = 0.3,
             model_key: str = "extraction", max_tokens: int = 4000,
             retries: int = 2, models: dict | None = None) -> Optional[str]:
    """Call LLM via OpenRouter with retry and fallback.

    Args:
        prompt: User prompt text.
        system: System prompt text.
        temperature: Sampling temperature.
        model_key: Key into the models dict (e.g. "extraction", "creative_association").
        max_tokens: Maximum response tokens.
        retries: Number of retry attempts.
        models: Model alias mapping (model_key -> alias). If None, uses "flash" default.

    Returns:
        Response text or None on failure.
    """
    import urllib.request

    key, provider = get_api_key()
    if not key:
        print("  Warning: No API key found for substrate LLM calls")
        return None

    models = models or {}
    model_alias = models.get(model_key, "flash")
    model = MODEL_MAP.get(model_alias, model_alias)
    fallback_model = MODEL_MAP.get("flash", "google/gemini-2.5-flash")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    for attempt in range(retries + 1):
        current_model = model if attempt < retries else fallback_model
        if attempt > 0:
            wait = 2 ** (attempt - 1)
            if current_model != model:
                print(f"  Attempt {attempt + 1}/{retries + 1}: falling back to {current_model}")
            else:
                print(f"  Attempt {attempt + 1}/{retries + 1}: retrying in {wait}s...")
            time.sleep(wait)

        body = json.dumps({
            "model": current_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }).encode()

        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            if attempt < retries:
                print(f"  LLM call failed (attempt {attempt + 1}): {e}")
                continue
            print(f"  LLM call failed after {retries + 1} attempts: {e}")
            return None


def load_prompt(name: str) -> str:
    """Load a prompt template from the substrate prompts directory."""
    prompts_dir = Path(__file__).resolve().parent / "prompts"
    prompt_path = prompts_dir / name
    if prompt_path.exists():
        return prompt_path.read_text()
    return ""
