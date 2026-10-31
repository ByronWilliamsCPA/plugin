#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["httpx>=0.27"]
# ///
"""Consensus engine CLI: multi-model fan-out via OpenRouter.

Subcommands (all emit JSON on stdout):
    select    Build a band-filtered roster with role assignments for a level/domain.
    estimate  Cost preview for a level without live validation or API calls.
    run       Fan a prompt out to models in parallel; emit raw responses.
    refresh   Diff the curated dataset against the live OpenRouter catalog.

OPENROUTER_API_KEY must be set in the environment for standard runs of the
run subcommand. A separate, more restrictive OPENROUTER__ZDR_API_KEY (double
underscore after OPENROUTER) is required for --zdr runs; the two keys are
never substituted for each other, so a run in ZDR mode fails rather than
falling back to the standard key. Both may instead live in a gitignored
.env at the repo root that owns this skill (a symlinked or checked-out
install, never an arbitrary Path.cwd()): main() auto-loads them from that
owning repo root's .env, and only when the resolved root actually contains
the .claude/skills/panel marker directory, without overriding a key already
present in the environment. This is a global skill that can be installed
into any project root, so Path.cwd()/.env is never read; trusting an
arbitrary cwd's .env could silently hand a run a different project's key.
Pass --zdr (or set OPENROUTER_ZDR=1 to force it for every run regardless of
prompt content) whenever the prompt carries confidential material: client or
financial data, secrets or credentials, proprietary or non-public code, or
PII. Otherwise the standard key is fine.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

import httpx

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CACHE_PATH = Path.home() / ".cache" / "panel-skill" / "openrouter-models.json"
ZDR_CACHE_PATH = Path.home() / ".cache" / "panel-skill" / "openrouter-zdr-models.json"
CACHE_TTL_SECONDS = 24 * 3600
OPENROUTER_BASE = "https://openrouter.ai/api/v1"
ZDR_TRUTHY_VALUES = {"1", "true", "yes"}
OPENROUTER_STD_ENV_NAME = "OPENROUTER_API_KEY"
OPENROUTER_ZDR_ENV_NAME = "OPENROUTER__ZDR_API_KEY"
_DOTENV_ALLOWLIST = {OPENROUTER_STD_ENV_NAME, OPENROUTER_ZDR_ENV_NAME, "OPENROUTER_ZDR"}
EST_INPUT_TOKENS = 2000
EST_OUTPUT_TOKENS = 1500
LEVEL_COST_CAPS_USD = {1: 0.50, 2: 1.00, 3: 10.00}
DOMAIN_CHOICES = ["code_review", "security", "architecture", "general"]
LEVEL_TIER_COUNTS = {
    1: {"free": 3},
    2: {"free": 3, "economy": 3},
    3: {"free": 3, "economy": 3, "premium": 2},
}
TIER_FALLBACK_ORDER = {
    "free": ["free", "economy"],
    "economy": ["economy", "value"],
    "premium": ["premium", "value"],
}
REQUEST_TIMEOUT_SECONDS = 120
MAX_RETRIES = 2
RETRY_BACKOFF_SECONDS = 2.0
FREE_COST_EPSILON = 1e-9
ZDR_STALE_CACHE_SECONDS = 7 * 24 * 3600
ZDR_STALE_CACHE_WARNING = (
    "ZDR endpoint list could not be refreshed from the live catalog; "
    "filtering against a cached list older than 7 days."
)
_SKILL_MARKER = Path(".claude") / "skills" / "panel"


@dataclass
class Model:
    """One row of the curated model dataset."""

    name: str
    provider: str
    input_cost: float
    output_cost: float
    humaneval: float
    swe_bench: float
    context: int
    specialization: str


def emit(payload: dict, stream: TextIO | None = None) -> None:
    """Write a JSON payload to stdout (or the given stream)."""
    (stream or sys.stdout).write(json.dumps(payload, indent=2) + "\n")


def parse_context(value: str | int | float | None) -> int:
    """Convert context sizes like '131K' or '1M' to a token count.

    Args:
        value: A string like '131K', '1M', '200000', a numeric value, or None.

    Returns:
        Integer token count, or 0 if the value is None or cannot be parsed.
    """
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().upper()
    multiplier = 1
    if text.endswith("K"):
        multiplier, text = 1_000, text[:-1]
    elif text.endswith("M"):
        multiplier, text = 1_000_000, text[:-1]
    try:
        return int(float(text) * multiplier)
    except ValueError:
        return 0


def _parse_model_row(row: dict) -> Model | None:
    """Parse one CSV row into a Model, returning None if the row is malformed.

    Args:
        row: A dict from csv.DictReader representing one data row.

    Returns:
        A Model instance, or None if required fields are missing or invalid.
    """
    if not (row.get("model") or "").strip():
        return None
    try:
        return Model(
            name=row["model"],
            provider=row.get("provider", ""),
            input_cost=float(row.get("input_cost") or 0),
            output_cost=float(row.get("output_cost") or 0),
            humaneval=float(row.get("humaneval_score") or 0),
            swe_bench=float(row.get("swe_bench_score") or 0),
            context=parse_context(row.get("context", 0)),
            specialization=row.get("specialization", "general"),
        )
    except (ValueError, KeyError):
        return None


def load_models(csv_path: Path | None = None) -> list[Model]:
    """Load the curated model dataset from CSV, skipping malformed rows.

    Args:
        csv_path: Optional override path to the models CSV file.

    Returns:
        List of Model instances parsed from the CSV.
    """
    path = csv_path or DATA_DIR / "models.csv"
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [m for row in rows if (m := _parse_model_row(row)) is not None]


def load_bands(path: Path | None = None) -> dict:
    """Load band criteria (cost tiers, org levels) from JSON.

    Args:
        path: Optional override path to the bands_config JSON file.

    Returns:
        Parsed bands configuration dictionary.
    """
    return json.loads(
        (path or DATA_DIR / "bands_config.json").read_text(encoding="utf-8")
    )


def load_roles(path: Path | None = None) -> dict:
    """Load role definitions and per-domain level assignments from JSON.

    Args:
        path: Optional override path to the roles JSON file.

    Returns:
        Parsed roles configuration dictionary.
    """
    return json.loads((path or DATA_DIR / "roles.json").read_text(encoding="utf-8"))


def models_in_cost_tier(models: list[Model], tier: str, bands: dict) -> list[Model]:
    """Filter models to a cost tier band, sorted by benchmark scores descending.

    The free tier requires both input and output cost to be zero (within
    FREE_COST_EPSILON); other tiers compare input cost against the band's
    min/max.

    Args:
        models: List of Model instances to filter.
        tier: Cost tier name (e.g. 'free', 'economy', 'value', 'premium').
        bands: Loaded bands configuration (from load_bands).

    Returns:
        Filtered and sorted list of Model instances.
    """
    criteria = bands["cost_tier_bands"][tier]
    max_cost = criteria.get("max_cost")
    min_cost = criteria.get("min_cost")
    kept = []
    for m in models:
        if max_cost is not None:
            if max_cost == 0.0:
                # #ASSUME: curated free models carry costs of exactly 0; epsilon guards
                # against near-zero float artifacts if live pricing ever enters the CSV.
                # #VERIFY: refresh workflow flags any free-tier row with nonzero cost.
                if (
                    m.input_cost > FREE_COST_EPSILON
                    or m.output_cost > FREE_COST_EPSILON
                ):
                    continue
            elif m.input_cost > max_cost:
                continue
        if min_cost is not None and m.input_cost < min_cost:
            continue
        kept.append(m)
    return sorted(kept, key=lambda m: (-m.humaneval, -m.swe_bench))


def role_system_prompt(role: str, roles_data: dict) -> str:
    """Build the system prompt for a professional role.

    Unknown role names are treated as literal system prompts, which is how
    flexible-mode stances ("argue for", "argue against") are passed in.
    """
    definition = roles_data["role_definitions"].get(role)
    if definition is None:
        return role
    # #ASSUME: roles.json definitions carry focus/questions/perspective; .get
    # guards partial entries. #VERIFY: refresh/curation keeps all three populated.
    return (
        f"You are acting as a {role.replace('_', ' ')}.\n\n"
        f"**Your Focus:** {definition.get('focus', '')}\n\n"
        f"**Key Questions to Address:** {definition.get('questions', '')}\n\n"
        f"**Your Perspective:** {definition.get('perspective', '')}\n\n"
        "Instructions:\n"
        "1. Analyze the question from your professional role's perspective\n"
        "2. Address the key questions relevant to your expertise\n"
        "3. Identify risks, concerns, or opportunities within your domain\n"
        "4. Provide specific, actionable insights\n"
        "5. Be concise but thorough; focus on what matters most from your perspective"
    )


def estimate_model_cost(m: Model) -> float:
    """Estimate one consultation's cost in USD using assumed token counts."""
    return round(
        (m.input_cost * EST_INPUT_TOKENS + m.output_cost * EST_OUTPUT_TOKENS)
        / 1_000_000,
        6,
    )


def enforce_cost_cap(total: float, level: int | None, max_cost: float | None) -> None:
    """Exit with code 2 if the estimated cost exceeds the applicable cap.

    The explicit --max-cost flag overrides the per-level default cap.
    """
    if max_cost is not None:
        cap = max_cost
    elif level is not None:
        cap = LEVEL_COST_CAPS_USD.get(level)
    else:
        cap = None
    if cap is not None and total > cap:
        emit(
            {
                "error": (
                    f"Estimated cost ${total:.4f} exceeds cap ${cap:.2f}. "
                    "Override with --max-cost if intended."
                )
            },
            stream=sys.stderr,
        )
        raise SystemExit(2)


def _env_truthy(name: str) -> bool:
    """Return True if the named env var holds a truthy string ('1'/'true'/'yes').

    Case-insensitive; unset or any other value is False. Used for
    OPENROUTER_ZDR, which travels with the API key rather than the
    invocation, so a flag alone would not be enough. An unrecognized
    non-empty value (e.g. 'on', 'y') warns on stderr, since silently
    disabling a privacy control is easy to miss.
    """
    raw = os.environ.get(name, "").strip().lower()
    if raw and raw not in ZDR_TRUTHY_VALUES and raw not in {"0", "false", "no"}:
        emit(
            {
                "warning": f"{name}={raw!r} is not recognized; ZDR mode is OFF. "
                "Use 1, true, or yes to enable it."
            },
            stream=sys.stderr,
        )
    return raw in ZDR_TRUTHY_VALUES


def _read_cache(cache: Path) -> set[str] | None:
    """Read cached model ids; None when missing, corrupted, or wrong-shaped."""
    try:
        data = json.loads(cache.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    # The cache is a JSON list of model-id strings. Any other shape (a bare
    # string would otherwise become a set of characters, a dict a set of keys)
    # is treated as corruption so validation never runs against garbage.
    if not isinstance(data, list) or not all(isinstance(item, str) for item in data):
        return None
    return set(data)


def _fetch_cached_ids(
    url: str,
    extract_ids: Callable[[dict], set[str]],
    client: httpx.Client | None,
    cache: Path,
    ttl: int,
) -> set[str]:
    """Shared fetch-with-disk-cache logic for OpenRouter catalog endpoints.

    A fresh, readable cache (younger than ttl) is served without a network
    call; a corrupted fresh cache falls through to a refetch. On fetch or
    parse failure a readable stale cache is used as fallback; with no usable
    cache the original error propagates. The cache write is atomic
    (temp file plus rename) so concurrent runs cannot tear it.

    Args:
        url: Full URL of the OpenRouter endpoint to fetch.
        extract_ids: Parses the JSON response body into a set of ids; a
            KeyError/TypeError/ValueError here is treated the same as a
            network failure (falls back to a stale cache).
        client: Optional shared httpx.Client; a private one is created and
            closed when omitted.
        cache: Cache file path for this endpoint.
        ttl: Cache freshness window in seconds.

    Returns:
        The set of ids extracted from the endpoint (live or cached).

    Raises:
        httpx.HTTPError: The network call failed and no usable cache exists.
    """
    if cache.exists() and time.time() - cache.stat().st_mtime < ttl:
        cached = _read_cache(cache)
        if cached is not None:
            return cached

    owns_client = client is None
    http = client or httpx.Client(timeout=30)
    try:
        resp = http.get(url)
        resp.raise_for_status()
        ids = extract_ids(resp.json())
    # #EDGE: a network error OR a malformed 200 body (missing key, non-iterable
    # data, non-dict entries -> TypeError) must fall back to a readable stale
    # cache; only re-raise when no usable cache exists. #VERIFY:
    # test_malformed_200_body_uses_stale_cache covers the parse-failure path.
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        cached = _read_cache(cache)
        if cached is not None:
            return cached
        raise
    finally:
        if owns_client:
            http.close()

    cache.parent.mkdir(parents=True, exist_ok=True)
    # #EDGE: a per-process temp name keeps concurrent refreshes from clobbering a
    # shared ".tmp" before the atomic rename; the live fetch already succeeded, so
    # a write failure is non-fatal and must not mask the result. #VERIFY:
    # test_concurrent_cache_writes_do_not_collide.
    tmp = cache.with_suffix(f".{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps(sorted(ids)), encoding="utf-8")
        tmp.replace(cache)
    except OSError:
        tmp.unlink(missing_ok=True)
    return ids


def fetch_live_model_ids(
    client: httpx.Client | None = None,
    cache_path: Path | None = None,
    ttl: int = CACHE_TTL_SECONDS,
) -> set[str]:
    """Return the set of live OpenRouter model ids, using a disk cache.

    See _fetch_cached_ids for the caching, staleness, and atomic-write
    contract; fetch_zdr_model_ids shares that helper with a different
    endpoint, id field, and cache file.
    """
    return _fetch_cached_ids(
        f"{OPENROUTER_BASE}/models",
        lambda body: {entry["id"] for entry in body["data"]},
        client,
        cache_path or CACHE_PATH,
        ttl,
    )


def fetch_zdr_model_ids(
    client: httpx.Client | None = None,
    cache_path: Path | None = None,
    ttl: int = CACHE_TTL_SECONDS,
) -> set[str]:
    """Return model ids with at least one ZDR-compliant endpoint.

    Backed by the public, unauthenticated GET /endpoints/zdr, using the same
    disk-cache contract as fetch_live_model_ids (see _fetch_cached_ids).

    #ASSUME: /endpoints/zdr stays public (no auth required) and its shape
    stays {"data": [{"model_id": ..., ...}, ...]}, with multiple entries
    possible per model (one per compliant provider endpoint). #VERIFY: a
    shape change surfaces as KeyError/TypeError inside _fetch_cached_ids,
    which falls back to a stale cache exactly like the live-catalog path;
    covered by test_zdr_malformed_200_body_uses_stale_cache.
    """
    return _fetch_cached_ids(
        f"{OPENROUTER_BASE}/endpoints/zdr",
        lambda body: {entry["model_id"] for entry in body["data"]},
        client,
        cache_path or ZDR_CACHE_PATH,
        ttl,
    )


def pinned_models(models: list[Model], tier: str, bands: dict) -> list[Model]:
    """Curated models pinned to the front of a tier, in configured order.

    Pins let a level include a model whose price or score would not earn the
    slot on its own. Pinned ids missing from the curated dataset are skipped.

    Args:
        models: Curated model dataset to resolve pinned ids against.
        tier: Roster tier name (e.g. 'economy').
        bands: Loaded bands configuration (from load_bands).

    Returns:
        Pinned Model instances for the tier, in configured order.

    Raises:
        ValueError: If any part of tier_pins is malformed: not an object, an
            unknown tier key (e.g. a misspelling), or pins that are not a list
            of strings (bands_config.json is hand-edited).
    """
    # #ASSUME: tier_pins is optional; a config without it pins nothing.
    # #VERIFY: test_real_tier_pins_exist_in_dataset fails if a pinned id
    # leaves models.csv.
    section = bands.get("tier_pins", {})
    if not isinstance(section, dict):
        raise ValueError("bands_config.json: tier_pins must be an object.")
    # Validate every entry, not just the requested tier, so a typo such as
    # "econmy" fails on any level instead of silently pinning nothing.
    for key, value in section.items():
        if key == "description":
            continue
        if key not in TIER_FALLBACK_ORDER:
            valid = ", ".join(TIER_FALLBACK_ORDER)
            raise ValueError(
                f"bands_config.json: unknown tier_pins key {key!r}; "
                f"valid tiers: {valid}."
            )
        if not isinstance(value, list) or not all(isinstance(n, str) for n in value):
            raise ValueError(
                f"bands_config.json: tier_pins.{key} must be a list of model ids."
            )
    names = section.get(tier, [])
    by_name = {m.name: m for m in models}
    return [by_name[n] for n in names if n in by_name]


def tier_candidates(models: list[Model], tier: str, bands: dict) -> list[Model]:
    """Ordered candidates for a roster tier: pins, then the fallback band chain.

    Args:
        models: Curated model dataset to draw candidates from.
        tier: Roster tier name (a key of TIER_FALLBACK_ORDER).
        bands: Loaded bands configuration (from load_bands).

    Returns:
        Candidate Model instances in selection order; may contain duplicates,
        which callers skip by name.
    """
    candidates = pinned_models(models, tier, bands)
    for fallback_tier in TIER_FALLBACK_ORDER[tier]:
        candidates.extend(models_in_cost_tier(models, fallback_tier, bands))
    return candidates


def select_roster(
    models: list[Model],
    bands: dict,
    roles_data: dict,
    level: int,
    domain: str,
    live: set[str] | None = None,
    zdr: set[str] | None = None,
) -> list[dict]:
    """Pick models per tier for a level, validate against live ids, assign roles.

    Tier counts are additive (level 2 includes level 1's free picks). When a
    tier runs out of live candidates, the fallback tier order in
    TIER_FALLBACK_ORDER supplies substitutes, which is how level 1 can use
    cheap paid models (within its cost cap) when free models are unavailable.
    Models listed under the tier's tier_pins entry in bands_config are tried
    first, ahead of the band's benchmark ordering.

    Args:
        models: Curated model dataset to draw candidates from.
        bands: Loaded bands configuration (from load_bands).
        roles_data: Loaded roles configuration (from load_roles).
        level: Consensus level (1, 2, or 3).
        domain: Domain key (e.g. 'code_review', 'architecture').
        live: Optional set of live model ids for validation; None skips validation.
        zdr: Optional set of ZDR-compliant model ids; when given, a candidate
            missing from this set is skipped regardless of live validation.
            This is how a policy-restricted key still fills level 1: free
            models without a ZDR-compliant endpoint drop out (not every free
            model lacks one; the live catalog does include some), and the
            free-to-economy fallback chain fills the resulting gap with
            cheap paid ZDR models.

    Returns:
        List of dicts with keys: model, role, est_cost_usd.  The list may
        be shorter than the domain's role count when all fallback candidates
        are exhausted; zip(picked, roles) truncates to the shorter side.

    Raises:
        ValueError: If level is not 1-3 or domain is not in roles_data.
    """
    if level not in LEVEL_TIER_COUNTS:
        raise ValueError(f"Invalid level: {level}. Must be 1, 2, or 3.")
    domain_levels = roles_data["domain_roles"].get(domain)
    if domain_levels is None:
        valid = ", ".join(roles_data["domain_roles"])
        raise ValueError(f"Invalid domain: {domain}. Valid domains: {valid}")
    roles = domain_levels.get(str(level))
    if roles is None:
        raise ValueError(f"Domain {domain} has no roles configured for level {level}.")

    picked: list[Model] = []
    for tier, count in LEVEL_TIER_COUNTS[level].items():
        taken = 0
        for candidate in tier_candidates(models, tier, bands):
            if taken >= count:
                break
            if any(p.name == candidate.name for p in picked):
                continue
            if live is not None and candidate.name not in live:
                continue
            if zdr is not None and candidate.name not in zdr:
                continue
            picked.append(candidate)
            taken += 1

    return [
        {
            "model": m.name,
            "role": role,
            "est_cost_usd": estimate_model_cost(m),
        }
        for m, role in zip(picked, roles, strict=False)
    ]


def select_fallbacks(
    models: list[Model],
    bands: dict,
    level: int,
    exclude: set[str],
    live: set[str] | None = None,
    zdr: set[str] | None = None,
    limit: int = 5,
) -> list[str]:
    """Ordered fallback candidates for run-time substitution.

    Walks the level's tiers and their fallback chains in roster order,
    skipping excluded and dead models, so a failed roster entry can be
    replaced by the next-best candidate from the same selection rules. When
    zdr is given, a candidate missing from it is skipped the same way a dead
    model is, so a substitution can never land on a policy-restricted model.
    """
    out: list[str] = []
    for tier in LEVEL_TIER_COUNTS[level]:
        for m in tier_candidates(models, tier, bands):
            if m.name in exclude or m.name in out:
                continue
            if live is not None and m.name not in live:
                continue
            if zdr is not None and m.name not in zdr:
                continue
            out.append(m.name)
    return out[:limit]


def _redact(text: str, secret: str) -> str:
    """Return a constant marker when text contains secret; otherwise text.

    Defense in depth beneath call_model's stored error strings: an HTTP
    error body or exception message could echo the Authorization header or
    otherwise leak api_key verbatim, and that string is persisted into the
    result record and eventually emitted as JSON via emit(). #VERIFY:
    test_call_model_redacts_api_key_from_http_error,
    test_call_model_redacts_api_key_from_exception_message, and
    test_escaped_exception_error_is_redacted in test_consensus_cli.py.

    #CRITICAL: the return value must never be built from secret or from any
    substring of text that depended on secret's presence (e.g. text.replace or
    text.split on secret). A taint tracker such as CodeQL's
    py/clear-text-logging-sensitive-data flags any return value that is a
    data-flow function of a parameter named like a credential, because that
    is indistinguishable from a leak at the data-flow level even when the
    literal secret value has been substituted out. Returning one of exactly
    two constants (this fixed marker, or the untouched original text) breaks
    that data flow: neither branch's return value is derived from secret.

    Args:
        text: The error string that might contain the secret.
        secret: The API key value to check for. A falsy secret always
            returns text unchanged.

    Returns:
        A fixed marker string if secret is truthy and found in text;
        otherwise text unchanged.
    """
    if secret and secret in text:
        return "[REDACTED: error text contained the API key]"
    return text


async def call_model(
    client: httpx.AsyncClient,
    entry: dict,
    prompt: str,
    api_key: str,
    catalog: dict[str, Model],
    zdr: bool = False,
) -> dict:
    """Send one chat completion and return a result record; never raises.

    Retries 429 and 5xx responses with backoff; other HTTP errors are
    terminal for this model only.

    Args:
        client: Shared async HTTP client for the fan-out batch.
        entry: Roster entry dict with keys model, role, system_prompt.
        prompt: User prompt text sent to every model.
        api_key: OpenRouter bearer token.
        catalog: Model objects keyed by model id for cost calculation.
        zdr: When True, every request body carries {"provider": {"zdr":
            true}}, restricting OpenRouter's routing to zero-data-retention
            endpoints. #CRITICAL: a policy-restricted key 404s/403s on a
            non-ZDR endpoint, so this must be set on every call in ZDR mode,
            not just the initial roster. #VERIFY:
            test_call_model_zdr_adds_provider_preference.

    Returns:
        Result dict with keys: model, role, response, tokens, cost_usd, error.
    """
    messages = []
    # empty/None system_prompt both mean: no system message
    system_prompt = entry.get("system_prompt")
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    record: dict = {
        "model": entry["model"],
        "role": entry.get("role"),
        "response": None,
        "tokens": None,
        "cost_usd": None,
        "error": None,
    }
    body: dict = {"model": entry["model"], "messages": messages}
    if zdr:
        body["provider"] = {"zdr": True}

    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = await client.post(
                f"{OPENROUTER_BASE}/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    usage = data.get("usage", {})
                    content = data["choices"][0]["message"]["content"]
                    record["tokens"] = usage
                    # #EDGE: a 200 with null content (refusals, function-call
                    # stubs, some upstream errors) is a per-model failure, not a
                    # success; recording it as a response would feed null into
                    # synthesis and count toward succeeded. #VERIFY: substitution
                    # treats it as a failed entry and tries a fallback.
                    if content is None:
                        record["error"] = "model returned null content"
                        return record
                    record["response"] = content
                    row = catalog.get(entry["model"])
                    if row is not None:
                        record["cost_usd"] = round(
                            (
                                row.input_cost * usage.get("prompt_tokens", 0)
                                + row.output_cost * usage.get("completion_tokens", 0)
                            )
                            / 1_000_000,
                            6,
                        )
                except (KeyError, IndexError, TypeError, ValueError) as exc:
                    record["error"] = f"malformed response: {exc!r}"
                return record
            if (
                resp.status_code == 429 or resp.status_code >= 500
            ) and attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_BACKOFF_SECONDS * (2**attempt))
                continue
            # Redact over the whole body before truncating: a key straddling
            # the 200-character cut would otherwise survive as a prefix that
            # _redact (which matches the complete key) cannot see.
            prefix = f"HTTP {resp.status_code}: "
            record["error"] = _redact(prefix + resp.text, api_key)[: len(prefix) + 200]
            return record
        except httpx.HTTPError as exc:
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_BACKOFF_SECONDS * (2**attempt))
                continue
            record["error"] = _redact(f"{type(exc).__name__}: {exc}", api_key)
            return record
    # unreachable defensive return: required by ruff RET503; every loop branch
    # above either returns or continues, so the loop never exits normally
    return record


def refresh_report(
    models: list[Model],
    live: set[str],
    zdr: set[str] | None = None,
    zdr_error: str | None = None,
) -> dict:
    """Compare the curated dataset against live OpenRouter model ids.

    Reports rows that no longer exist upstream and free models that exist
    upstream but are not yet curated. Never edits the dataset: the
    benchmark and specialization fields are hand-rated.

    Args:
        models: Curated model dataset.
        live: Live OpenRouter model ids (from fetch_live_model_ids).
        zdr: Live ZDR-compliant model ids (from fetch_zdr_model_ids); when
            given, the report gains curated_without_zdr_endpoint. Omitted
            when zdr_error is set instead.
        zdr_error: When the ZDR endpoint fetch failed (and no fallback was
            requested), the report carries this string plus a null
            curated_without_zdr_endpoint instead of failing the whole
            refresh; dead_in_curated and live_free_not_in_curated are
            unaffected since they only depend on the live-catalog fetch.

    Returns:
        Report dict; curated_without_zdr_endpoint/zdr_error are present only
        when zdr or zdr_error was passed.
    """
    curated = {m.name for m in models}
    report = {
        "dead_in_curated": sorted(curated - live),
        "live_free_not_in_curated": sorted(
            i for i in live if i.endswith(":free") and i not in curated
        ),
        "curated_count": len(curated),
        "live_count": len(live),
    }
    if zdr_error is not None:
        report["curated_without_zdr_endpoint"] = None
        report["zdr_error"] = zdr_error
    elif zdr is not None:
        report["curated_without_zdr_endpoint"] = sorted(curated - zdr)
    return report


async def run_consensus(
    entries: list[dict],
    prompt: str,
    api_key: str,
    catalog: dict[str, Model],
    transport: httpx.AsyncBaseTransport | None = None,
    zdr: bool = False,
) -> dict:
    """Fan the prompt out to all entries in parallel and aggregate results.

    Args:
        entries: Roster entries, each with keys model, role, system_prompt.
        prompt: User question sent to every model.
        api_key: OpenRouter bearer token.
        catalog: Model objects keyed by model id for per-model cost calculation.
        transport: Optional async transport override for testing.
        zdr: When True, every chat request carries the ZDR provider
            preference (see call_model).

    Returns:
        Aggregation dict with keys: results, succeeded, failed, total_cost_usd.
    """
    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT_SECONDS, transport=transport
    ) as client:
        # return_exceptions keeps one model's unexpected failure from cancelling
        # the whole panel; any escaped exception is normalised into that model's
        # error record so per-model isolation holds even outside call_model's
        # own try/except surface.
        raw = await asyncio.gather(
            *[
                call_model(client, e, prompt, api_key, catalog, zdr=zdr)
                for e in entries
            ],
            return_exceptions=True,
        )
    results = [
        res
        if not isinstance(res, BaseException)
        else {
            "model": entry["model"],
            "role": entry.get("role"),
            "response": None,
            "tokens": None,
            "cost_usd": None,
            "error": _redact(f"{type(res).__name__}: {res}", api_key),
        }
        for entry, res in zip(entries, raw, strict=True)
    ]
    succeeded = [r for r in results if r["error"] is None]
    return {
        "results": results,
        "succeeded": len(succeeded),
        "failed": len(results) - len(succeeded),
        "total_cost_usd": round(
            sum(
                (r["cost_usd"] if r["cost_usd"] is not None else 0.0) for r in succeeded
            ),
            6,
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser with the four subcommands."""
    parser = argparse.ArgumentParser(prog="consensus_cli", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_select = sub.add_parser("select", help="Build a roster for a level and domain")
    p_select.add_argument(
        "--level",
        type=int,
        default=2,
        choices=[1, 2, 3],
        help="Review depth; defaults to 2 (level 1 is for low-value/low-stakes items)",
    )
    p_select.add_argument("--domain", default="code_review", choices=DOMAIN_CHOICES)
    p_select.add_argument("--limit", type=int, default=None)
    p_select.add_argument(
        "--no-validate", action="store_true", help="Skip live OpenRouter validation"
    )
    p_select.add_argument(
        "--zdr",
        action="store_true",
        help=(
            "Restrict candidates to ZDR-compliant endpoints (also set by "
            "OPENROUTER_ZDR); use for keys that require zero data retention"
        ),
    )

    p_estimate = sub.add_parser("estimate", help="Cost preview for a level")
    p_estimate.add_argument(
        "--level",
        type=int,
        default=2,
        choices=[1, 2, 3],
        help="Review depth; defaults to 2 (level 1 is for low-value/low-stakes items)",
    )
    p_estimate.add_argument("--domain", default="code_review", choices=DOMAIN_CHOICES)
    p_estimate.add_argument(
        "--zdr",
        action="store_true",
        help="Restrict candidates to ZDR-compliant endpoints (see select --zdr)",
    )

    p_run = sub.add_parser("run", help="Fan a prompt out to models in parallel")
    p_run.add_argument("--prompt-file", required=True)
    # A run draws its panel from exactly one source; allowing both let the roster
    # file silently win over --models with no warning.
    source = p_run.add_mutually_exclusive_group()
    source.add_argument("--roster-file", help="Roster JSON produced by select")
    source.add_argument("--models", help="Comma-separated model ids (flexible mode)")
    p_run.add_argument(
        "--roles-file",
        help="JSON object mapping model id to a role name or literal system prompt",
    )
    p_run.add_argument(
        "--level",
        type=int,
        choices=[1, 2, 3],
        help="Apply the per-level cost cap (1, 2, or 3)",
    )
    p_run.add_argument("--max-cost", type=float, help="Override the cost cap in USD")
    p_run.add_argument(
        "--zdr",
        action="store_true",
        help=(
            "Send every request with the ZDR provider preference (also set "
            "by OPENROUTER_ZDR or a roster file with a zdr: true key)"
        ),
    )

    sub.add_parser("refresh", help="Diff curated dataset against the live catalog")
    return parser


def _read_json_file(path: str, what: str) -> object:
    """Read and parse a JSON file, exiting cleanly on missing or invalid input."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        emit({"error": f"cannot read {what} {path}: {exc}"}, stream=sys.stderr)
        raise SystemExit(2) from exc


# Sentinel distinguishing "no snapshot supplied" from a roster file whose JSON
# content is literally null (which parses to None and must not trigger a re-read).
_NO_SNAPSHOT: object = object()


def build_entries(
    args: argparse.Namespace,
    roles_data: dict,
    roster: object = _NO_SNAPSHOT,
) -> list[dict]:
    """Resolve run arguments into model entries with system prompts.

    Args:
        args: Parsed CLI arguments (roster_file, models, roles_file, ...).
        roles_data: Role definitions used to build system prompts.
        roster: Already-parsed roster payload for ``args.roster_file``. When
            supplied (anything but the default sentinel), the file is not read
            again, so a caller that also needs the payload (fallbacks, "zdr"
            declaration) works from one snapshot.

    Returns:
        Model entries, each with model, role, and system_prompt keys.

    Raises:
        SystemExit: With code 2 when an input file is unreadable or malformed.
    """
    entries: list[dict] = []
    if args.roster_file:
        if roster is _NO_SNAPSHOT:
            roster = _read_json_file(args.roster_file, "roster file")
        if isinstance(roster, dict):
            items = roster.get("roster")
        elif isinstance(roster, list):
            items = roster
        else:
            items = None
        if not isinstance(items, list):
            emit(
                {
                    "error": (
                        f"roster file {args.roster_file} must be a list of entries "
                        "or an object with a 'roster' list"
                    )
                },
                stream=sys.stderr,
            )
            raise SystemExit(2)
        for item in items:
            if not isinstance(item, dict) or "model" not in item:
                emit(
                    {
                        "error": (
                            f"roster file {args.roster_file} has an entry that is "
                            "not an object with a 'model' key"
                        )
                    },
                    stream=sys.stderr,
                )
                raise SystemExit(2)
            role = item.get("role")
            entries.append(
                {
                    "model": item["model"],
                    "role": role,
                    "system_prompt": role_system_prompt(role, roles_data)
                    if role
                    else None,
                }
            )
    elif args.models:
        roles_map = (
            _read_json_file(args.roles_file, "roles file") if args.roles_file else {}
        )
        if not isinstance(roles_map, dict):
            emit(
                {"error": f"roles file {args.roles_file} must be a JSON object"},
                stream=sys.stderr,
            )
            raise SystemExit(2)
        for name in args.models.split(","):
            name = name.strip()
            role = roles_map.get(name)
            entries.append(
                {
                    "model": name,
                    "role": role,
                    "system_prompt": role_system_prompt(role, roles_data)
                    if role
                    else None,
                }
            )
    else:
        emit({"error": "run requires --roster-file or --models"}, stream=sys.stderr)
        raise SystemExit(2)
    return entries


def _zdr_mode_enabled(args: argparse.Namespace) -> bool:
    """True when ZDR mode is requested via --zdr or the OPENROUTER_ZDR env var.

    The env var exists because the ZDR requirement is a property of the
    OpenRouter key, not of any one invocation, so it should travel with the
    key rather than need repeating on every call.
    """
    return bool(getattr(args, "zdr", False)) or _env_truthy("OPENROUTER_ZDR")


def _fetch_zdr_ids_or_exit() -> tuple[set[str], bool]:
    """Fetch the ZDR model-id set, exiting with a clear JSON error on failure.

    ZDR is a policy filter: silently returning an unfiltered roster when the
    endpoint is unreachable and no cache exists would defeat the point of
    ZDR mode, so this fails loudly instead.

    #EDGE: when the live fetch fails, _fetch_cached_ids falls back to
    reading whatever ZDR disk cache already exists, however old, without
    rewriting it. A successful live fetch always rewrites the cache (mtime
    now); a fast-path fresh-cache read only happens within
    CACHE_TTL_SECONDS (24h). So a cache still older than
    ZDR_STALE_CACHE_SECONDS (7 days) after this call returns can only mean
    the stale-fallback path was taken; that lets this function detect
    staleness from the cache file's mtime alone, with no change needed to
    _fetch_cached_ids's return contract. #VERIFY:
    test_fetch_zdr_ids_or_exit_flags_cache_older_than_seven_days and
    test_fetch_zdr_ids_or_exit_fresh_cache_not_flagged in
    test_consensus_cli.py.

    #EDGE: _fetch_cached_ids treats a failed cache write after a successful
    live fetch as non-fatal (it unlinks the temp file and returns the live
    ids anyway, per its own #EDGE note), so the on-disk cache can stay old
    even though the ids just returned are fresh. This function has no way
    to distinguish that case from a genuine stale-fallback read, so it can
    report a false-positive cache_stale=True on a successful live fetch
    when the write itself failed. This errs toward warning the operator
    rather than silently trusting a filter that may be built from
    unexpectedly old data, which is the safer failure direction for a
    policy filter like ZDR.

    Returns:
        A tuple of (zdr_ids, cache_stale): cache_stale is True when the ids
        came from a disk cache older than ZDR_STALE_CACHE_SECONDS because
        the live fetch failed and this cache was used as a fallback.
    """
    try:
        ids = fetch_zdr_model_ids()
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        emit(
            {
                "error": (
                    "cannot fetch ZDR endpoint list and no usable cache: "
                    f"{type(exc).__name__}: {exc}"
                )
            },
            stream=sys.stderr,
        )
        raise SystemExit(2) from exc
    cache_stale = (
        ZDR_CACHE_PATH.exists()
        and time.time() - ZDR_CACHE_PATH.stat().st_mtime >= ZDR_STALE_CACHE_SECONDS
    )
    return ids, cache_stale


def _cmd_select(
    args: argparse.Namespace,
    models: list[Model],
    bands: dict,
    roles: dict,
) -> int:
    """Handle the select and estimate subcommands; return an exit code."""
    live = None
    if args.command == "select" and not args.no_validate:
        live = fetch_live_model_ids()

    zdr_mode = _zdr_mode_enabled(args)
    zdr_ids = None
    cache_stale = False
    if zdr_mode:
        zdr_ids, cache_stale = _fetch_zdr_ids_or_exit()

    roster = select_roster(
        models, bands, roles, args.level, args.domain, live=live, zdr=zdr_ids
    )
    limit = getattr(args, "limit", None)
    if limit is not None:
        roster = roster[:limit]
    fallbacks = select_fallbacks(
        models,
        bands,
        args.level,
        exclude={r["model"] for r in roster},
        live=live,
        zdr=zdr_ids,
    )
    payload = {
        "level": args.level,
        "domain": args.domain,
        "roster": roster,
        "fallbacks": fallbacks,
        "estimated_cost_usd": round(sum(r["est_cost_usd"] for r in roster), 6),
        "cap_usd": LEVEL_COST_CAPS_USD[args.level],
    }
    if zdr_mode:
        payload["zdr"] = True
        if cache_stale:
            payload["zdr_cache_stale"] = True
            payload["warning"] = ZDR_STALE_CACHE_WARNING
    emit(payload)
    return 0


def _substitute_failures(
    outcome: dict,
    fallbacks: list[str],
    roles_data: dict,
    prompt: str,
    api_key: str,
    catalog: dict[str, Model],
    zdr: bool = False,
) -> dict:
    """One substitution round: re-run failed entries on fallback models.

    Each failed result hands its role to the next unused fallback candidate.
    Substituted originals stay in the results list so the operator sees both
    the failure and its replacement; a substitutions map links them.

    Args:
        outcome: Prior run_consensus aggregation to substitute into.
        fallbacks: Ordered fallback model ids, already filtered to
            live/ZDR-eligible candidates by select_fallbacks.
        roles_data: Loaded roles configuration for system-prompt building.
        prompt: User prompt text sent to every model.
        api_key: OpenRouter bearer token.
        catalog: Model objects keyed by model id for cost calculation.
        zdr: When True, retry requests also carry the ZDR provider
            preference, matching the original round.

    Returns:
        Merged outcome dict, or the original outcome unchanged when there is
        nothing to substitute.
    """
    failed = [r for r in outcome["results"] if r["error"] is not None]
    if not failed or not fallbacks:
        return outcome
    pool = list(fallbacks)
    substitutions: dict[str, str] = {}
    retry_entries: list[dict] = []
    for record in failed:
        if not pool:
            break
        candidate = pool.pop(0)
        substitutions[record["model"]] = candidate
        role = record["role"]
        retry_entries.append(
            {
                "model": candidate,
                "role": role,
                "system_prompt": role_system_prompt(role, roles_data) if role else None,
            }
        )
    retry_outcome = asyncio.run(
        run_consensus(retry_entries, prompt, api_key, catalog, zdr=zdr)
    )
    merged = outcome["results"] + retry_outcome["results"]
    succeeded = [r for r in merged if r["error"] is None]
    return {
        "results": merged,
        "succeeded": len(succeeded),
        "failed": len(merged) - len(succeeded),
        "total_cost_usd": round(
            outcome["total_cost_usd"] + retry_outcome["total_cost_usd"], 6
        ),
        "substitutions": substitutions,
    }


def _off_zdr_models(
    entries: list[dict], zdr_mode: bool, models_mode: bool
) -> list[str]:
    """Entry model ids missing a ZDR-compliant endpoint, for the run warning.

    Only checked in --models (flexible) mode under ZDR: roster-file entries
    were already restricted to the ZDR set at select time, so re-checking
    them here would be redundant. This check is informational, not a policy
    gate (the gate lives in select/estimate), so a failed ZDR fetch here is
    swallowed rather than blocking the run: the operator already asked to
    run these exact models.
    """
    if not (zdr_mode and models_mode):
        return []
    try:
        zdr_ids = fetch_zdr_model_ids()
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        return []
    return [e["model"] for e in entries if e["model"] not in zdr_ids]


def _roster_zdr_check(
    entries: list[dict], fallbacks: list[str]
) -> tuple[list[str], list[str], bool]:
    """Check an undeclared roster's entries and fallbacks against the ZDR set.

    Only called for a roster file that did not declare "zdr": true while ZDR
    mode is otherwise active (via --zdr or OPENROUTER_ZDR). A roster that
    declares "zdr": true is already restricted to ZDR ids at select time (see
    select_roster), so re-checking it here would be redundant; that case is
    handled by the caller keeping current behavior and never calling this
    function. This function fills the equivalent gap for an undeclared
    roster: without it, an operator running a plain roster file under --zdr
    would get neither the off-ZDR warning nor fallback filtering that
    --models mode already provides.

    Best-effort like the --models path (_off_zdr_models): a failed ZDR fetch
    does not block the run. Unlike that path's fully silent swallow, the
    caller surfaces the failure as a warning, since an operator combining
    --roster-file with --zdr reasonably expects the substitution pool to
    stay ZDR-compliant, and a silent skip here would waste substitution
    attempts on blocked models with no indication why.

    Args:
        entries: Roster entries (each a dict with at least "model").
        fallbacks: The roster's ordered fallback model ids.

    Returns:
        A (off_zdr_models, filtered_fallbacks, fetch_failed) tuple. When
        fetch_failed is True, off_zdr_models is [] and filtered_fallbacks is
        the input fallbacks unchanged, so a fetch failure degrades to the
        pre-existing unfiltered behavior rather than blocking substitution.
    """
    try:
        zdr_ids = fetch_zdr_model_ids()
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        return [], fallbacks, True
    off_zdr = [e["model"] for e in entries if e["model"] not in zdr_ids]
    filtered_fallbacks = [m for m in fallbacks if m in zdr_ids]
    return off_zdr, filtered_fallbacks, False


def _parse_dotenv_line(line: str) -> tuple[str, str] | None:
    """Parse one .env line into a (key, value) pair, or None for non-data lines.

    Skips blank lines and `#` comments, tolerates a leading `export` prefix
    followed by any amount of whitespace (a single space, tabs, or several
    spaces), and strips a single pair of matching quotes (`'` or `"`) around
    the value. An unquoted value's trailing ` #comment` (a literal space,
    then `#`, then arbitrary text) is stripped before quote-matching runs, so
    a quoted value followed by a trailing comment (`"quoted" # comment`) is
    also handled. A key with an empty value (`KEY=` with nothing after the
    `=`) is skipped entirely rather than returned as real data, so it cannot
    block key resolution the way a present-but-blank env var would.

    Args:
        line: One raw line from a .env file, not yet stripped.

    Returns:
        The parsed (key, value) pair, or None if the line carries no data or
        the value is empty.
    """
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith("export") and stripped[len("export") :][:1].isspace():
        stripped = stripped[len("export") :].strip()
    if "=" not in stripped:
        return None
    key, _, value = stripped.partition("=")
    key = key.strip()
    value = value.strip()
    if len(value) >= 1 and value[0] in ("'", '"'):
        # Quoted value: take everything up to the FIRST matching closing
        # quote (not "the last character of the string"), so a trailing
        # comment after the closing quote ("quoted" # comment) is dropped
        # along with the quotes themselves rather than left embedded in the
        # value. An unterminated quote (no closing match) is left as-is.
        quote = value[0]
        closing = value.find(quote, 1)
        if closing != -1:
            value = value[1:closing]
    else:
        # Unquoted value: an unescaped trailing " #comment" is not part of
        # the value. Only a comment preceded by whitespace counts, so a
        # literal "#" inside an unquoted value (rare, but not our call to
        # forbid) is left alone.
        comment_at = value.find(" #")
        if comment_at != -1:
            value = value[:comment_at].rstrip()
    if not value:
        return None
    return key, value


def _load_env_file(path: Path) -> None:
    """Load allowlisted OpenRouter env vars from one .env file into os.environ.

    #CRITICAL: this reads a file that may contain API keys and writes into
    the process environment. Only the three names in _DOTENV_ALLOWLIST are
    ever taken from the file (arbitrary .env content cannot inject other env
    vars), and a name already present in os.environ is never overwritten, so
    a stray or malicious .env cannot override an operator's explicit shell
    export. #VERIFY: test_load_env_file_allowlist_only and
    test_load_env_file_never_overrides_existing_env in test_consensus_cli.py.

    Args:
        path: Candidate .env file path; missing or unreadable is a silent
            no-op, since a .env file is optional at every search location.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        parsed = _parse_dotenv_line(line)
        if parsed is None:
            continue
        key, value = parsed
        if key not in _DOTENV_ALLOWLIST or key in os.environ:
            continue
        os.environ[key] = value


def _owning_repo_root() -> Path | None:
    """Return the repo root that owns this skill script, or None if unowned.

    The script normally lives at
    <repo_root>/.claude/skills/panel/scripts/consensus_cli.py, 4 parents up
    from the resolved file path. #CRITICAL: this is a *global* skill that
    gets symlinked or checked out into arbitrary project roots, so the
    parents[4] candidate is trusted only when it actually contains the
    .claude/skills/panel marker directory, confirming the standard
    <root>/.claude/skills/panel install layout rather than merely counting
    path segments. A bare parent-count check cannot tell an unrelated
    ancestor directory from a real install, and could even resolve to '/'
    for a script placed exactly 5 levels deep somewhere unexpected; either
    way it would let a stranger project's .env supply this process's
    OpenRouter key, silently defeating the ZDR account-restriction
    guarantee. #VERIFY:
    test_owning_repo_root_lands_on_repo_root_for_matching_depth and
    test_owning_repo_root_rejects_missing_marker in test_consensus_cli.py.

    Returns:
        The resolved repo root path when it contains the skill's marker
        directory, confirming the standard install layout, otherwise None
        (script too shallow, or no marker found there).
    """
    parents = Path(__file__).resolve().parents
    if len(parents) <= 4:
        return None
    candidate = parents[4]
    if not (candidate / _SKILL_MARKER).is_dir():
        return None
    return candidate


def _load_dotenv_keys() -> None:
    """Load OpenRouter keys from the skill's owning repo .env, if any.

    #CRITICAL: this is a global skill installed (symlinked or checked out)
    into arbitrary project roots, so Path.cwd() is not necessarily a repo
    this operator controls; trusting Path.cwd()/.env there would let an
    unrelated third-party project's .env silently supply a different
    account's key, or a standard key masquerading as the ZDR key, defeating
    the account-restriction guarantee ZDR mode depends on. Path.cwd() is
    therefore never read. Only the owning repo's .env is read, and only
    when _owning_repo_root confirms the .claude/skills/panel marker
    actually exists there. Never overrides a variable already set in
    os.environ.
    """
    repo_root = _owning_repo_root()
    if repo_root is not None:
        _load_env_file(repo_root / ".env")


def _select_api_key(zdr_mode: bool) -> str | None:
    """Return the correct OpenRouter API key for the mode, with no fallback.

    #CRITICAL: in ZDR mode this must return only OPENROUTER__ZDR_API_KEY,
    never falling back to the standard OPENROUTER_API_KEY. The ZDR key is an
    account-level data-handling guarantee, stronger than the per-request
    provider.zdr preference alone, so silently substituting the standard key
    would weaken that guarantee without any visible signal.
    #VERIFY: test_zdr_mode_never_falls_back_to_standard_key in
    test_consensus_cli.py.

    A key that is empty, contains any whitespace, or carries any
    non-printable or non-ASCII character is rejected the same way a missing
    key is: the only caller-visible signal is the variable NAME (see
    _cmd_run), never the value, so a malformed key (a stray control
    character from a copy-paste, an embedded newline) fails closed instead
    of reaching httpx as a bearer token. #VERIFY:
    test_select_api_key_rejects_key_with_control_character in
    test_consensus_cli.py.

    Args:
        zdr_mode: True when the run must use the ZDR-restricted account key.

    Returns:
        The key string, or None when the required env var is unset, empty,
        or fails the hygiene check above.
    """
    var = OPENROUTER_ZDR_ENV_NAME if zdr_mode else OPENROUTER_STD_ENV_NAME
    key = os.environ.get(var)
    if not key:
        return None
    if not key.isascii() or not key.isprintable() or any(ch.isspace() for ch in key):
        return None
    return key


def _cmd_run(
    args: argparse.Namespace,
    models: list[Model],
    roles: dict,
) -> int:
    """Handle the run subcommand; return an exit code."""
    try:
        prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        emit(
            {"error": f"cannot read prompt file {args.prompt_file}: {exc}"},
            stream=sys.stderr,
        )
        return 2
    # #CRITICAL: the roster file is read exactly once; entries, fallbacks and the
    # "zdr" declaration all derive from this single snapshot so a file changed
    # mid-run cannot split the ZDR declaration from the entries executed.
    # #VERIFY: test_roster_file_read_once_per_run counts reads of the roster path.
    roster_payload = (
        _read_json_file(args.roster_file, "roster file") if args.roster_file else None
    )
    entries = build_entries(args, roles, roster=roster_payload)
    catalog = {m.name: m for m in models}
    zdr_mode = _zdr_mode_enabled(args)

    roster_declared_zdr = False
    if args.roster_file:
        fallbacks: list[str] = (
            roster_payload.get("fallbacks", [])
            if isinstance(roster_payload, dict)
            else []
        )
        if isinstance(roster_payload, dict) and roster_payload.get("zdr"):
            zdr_mode = True
            roster_declared_zdr = True
    else:
        # --models mode: user-named panels are never substituted
        fallbacks = []

    # Key choice depends on the fully-resolved zdr_mode (flag, env var, or the
    # roster file's "zdr": true override read just above), so this must come
    # after that resolution, not at function entry.
    api_key = _select_api_key(zdr_mode)
    if not api_key:
        env_name = OPENROUTER_ZDR_ENV_NAME if zdr_mode else OPENROUTER_STD_ENV_NAME
        # Distinguish "unset" from "set but hygiene-rejected" so the operator
        # knows which problem to fix, without ever printing the value itself
        # (see _select_api_key's #VERIFY note on this exact distinction).
        if os.environ.get(env_name):
            message = (
                f"{env_name} is set but malformed (whitespace, control, or "
                "non-ASCII characters)"
            )
        else:
            message = f"{env_name} is not set"
        emit({"error": message}, stream=sys.stderr)
        return 1

    off_zdr = _off_zdr_models(entries, zdr_mode, models_mode=bool(args.models))
    zdr_check_failed = False
    if zdr_mode and args.roster_file and not roster_declared_zdr:
        off_zdr, fallbacks, zdr_check_failed = _roster_zdr_check(entries, fallbacks)

    # #ASSUME: uncatalogued models cannot be cost-estimated; the cap only covers
    # catalog rows. #VERIFY: run output carries a warning listing them so the
    # operator sees the gap.
    estimate = round(
        sum(
            estimate_model_cost(catalog[e["model"]])
            for e in entries
            if e["model"] in catalog
        ),
        6,
    )
    enforce_cost_cap(estimate, args.level, args.max_cost)
    outcome = asyncio.run(
        run_consensus(entries, prompt, api_key, catalog, zdr=zdr_mode)
    )

    if outcome["failed"] > 0 and fallbacks:
        # Cap-check substitution cost before proceeding.
        sub_estimate = round(
            sum(
                estimate_model_cost(catalog[name])
                for name in fallbacks[: outcome["failed"]]
                if name in catalog
            ),
            6,
        )
        # #CRITICAL: base the substitution cap on the cost actually incurred so
        # far (outcome["total_cost_usd"]), not the pre-flight estimate; a
        # high-token first round plus substitution could otherwise breach the
        # level cap.
        # #VERIFY: confirm enforce_cost_cap receives actual incurred cost, not pre-flight estimate
        enforce_cost_cap(
            outcome["total_cost_usd"] + sub_estimate, args.level, args.max_cost
        )
        outcome = _substitute_failures(
            outcome, fallbacks, roles, prompt, api_key, catalog, zdr=zdr_mode
        )

    # Recompute unknown across all result models (substitutes may also be uncatalogued).
    unknown = [r["model"] for r in outcome["results"] if r["model"] not in catalog]
    warnings = []
    if unknown:
        warnings.append(
            "models not in curated catalog, cost unknown and not capped: "
            + ", ".join(unknown)
        )
    if off_zdr:
        warnings.append(
            "models without a ZDR-compliant endpoint under ZDR mode (attempted "
            "anyway): " + ", ".join(off_zdr)
        )
    if zdr_check_failed:
        warnings.append(
            "could not verify roster models against the ZDR-compliant model "
            "list; off-ZDR models were not identified and fallbacks were not "
            "filtered"
        )
    if warnings:
        outcome["warning"] = "; ".join(warnings)
    if zdr_mode:
        outcome["zdr"] = True
    emit(outcome)
    return 0 if outcome["succeeded"] else 3


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; returns a process exit code."""
    args = build_parser().parse_args(argv)
    # Loaded once here (not per-subcommand) so select/estimate also honor a
    # key or OPENROUTER_ZDR sourced from the owning repo's .env, not just run.
    _load_dotenv_keys()
    try:
        models = load_models()
        bands = load_bands()
        roles = load_roles()
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        emit({"error": f"cannot load consensus data files: {exc}"}, stream=sys.stderr)
        return 2

    if args.command in ("select", "estimate"):
        return _cmd_select(args, models, bands, roles)

    if args.command == "run":
        return _cmd_run(args, models, roles)

    live = fetch_live_model_ids()
    try:
        zdr_ids = fetch_zdr_model_ids()
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        # A ZDR-endpoint outage must not fail the whole refresh; the
        # live-catalog diff (dead_in_curated, live_free_not_in_curated) is
        # still useful on its own.
        emit(refresh_report(models, live, zdr_error=f"{type(exc).__name__}: {exc}"))
        return 0
    emit(refresh_report(models, live, zdr=zdr_ids))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
