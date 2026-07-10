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

OPENROUTER_API_KEY must be set in the environment for the run subcommand.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

import httpx

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CACHE_PATH = Path.home() / ".cache" / "panel-skill" / "openrouter-models.json"
CACHE_TTL_SECONDS = 24 * 3600
OPENROUTER_BASE = "https://openrouter.ai/api/v1"
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


def fetch_live_model_ids(
    client: httpx.Client | None = None,
    cache_path: Path | None = None,
    ttl: int = CACHE_TTL_SECONDS,
) -> set[str]:
    """Return the set of live OpenRouter model ids, using a disk cache.

    A fresh, readable cache (younger than ttl) is served without a network
    call; a corrupted fresh cache falls through to a refetch. On fetch or
    parse failure a readable stale cache is used as fallback; with no usable
    cache the original error propagates. The cache write is atomic
    (temp file plus rename) so concurrent runs cannot tear it.
    """
    cache = cache_path or CACHE_PATH
    if cache.exists() and time.time() - cache.stat().st_mtime < ttl:
        cached = _read_cache(cache)
        if cached is not None:
            return cached

    owns_client = client is None
    http = client or httpx.Client(timeout=30)
    try:
        resp = http.get(f"{OPENROUTER_BASE}/models")
        resp.raise_for_status()
        ids = {entry["id"] for entry in resp.json()["data"]}
    # #EDGE: a network error OR a malformed 200 body (missing "data", non-iterable
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


def select_roster(
    models: list[Model],
    bands: dict,
    roles_data: dict,
    level: int,
    domain: str,
    live: set[str] | None = None,
) -> list[dict]:
    """Pick models per tier for a level, validate against live ids, assign roles.

    Tier counts are additive (level 2 includes level 1's free picks). When a
    tier runs out of live candidates, the fallback tier order in
    TIER_FALLBACK_ORDER supplies substitutes, which is how level 1 can use
    cheap paid models (within its cost cap) when free models are unavailable.

    Args:
        models: Curated model dataset to draw candidates from.
        bands: Loaded bands configuration (from load_bands).
        roles_data: Loaded roles configuration (from load_roles).
        level: Consensus level (1, 2, or 3).
        domain: Domain key (e.g. 'code_review', 'architecture').
        live: Optional set of live model ids for validation; None skips validation.

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
        candidates: list[Model] = []
        for fallback_tier in TIER_FALLBACK_ORDER[tier]:
            candidates.extend(models_in_cost_tier(models, fallback_tier, bands))
        taken = 0
        for candidate in candidates:
            if taken >= count:
                break
            if any(p.name == candidate.name for p in picked):
                continue
            if live is not None and candidate.name not in live:
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
    limit: int = 5,
) -> list[str]:
    """Ordered fallback candidates for run-time substitution.

    Walks the level's tiers and their fallback chains in roster order,
    skipping excluded and dead models, so a failed roster entry can be
    replaced by the next-best candidate from the same selection rules.
    """
    out: list[str] = []
    for tier in LEVEL_TIER_COUNTS[level]:
        for fallback_tier in TIER_FALLBACK_ORDER[tier]:
            for m in models_in_cost_tier(models, fallback_tier, bands):
                if m.name in exclude or m.name in out:
                    continue
                if live is not None and m.name not in live:
                    continue
                out.append(m.name)
    return out[:limit]


async def call_model(
    client: httpx.AsyncClient,
    entry: dict,
    prompt: str,
    api_key: str,
    catalog: dict[str, Model],
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

    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = await client.post(
                f"{OPENROUTER_BASE}/chat/completions",
                json={"model": entry["model"], "messages": messages},
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
            record["error"] = f"HTTP {resp.status_code}: {resp.text[:200]}"
            return record
        except httpx.HTTPError as exc:
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_BACKOFF_SECONDS * (2**attempt))
                continue
            record["error"] = f"{type(exc).__name__}: {exc}"
            return record
    # unreachable defensive return: required by ruff RET503; every loop branch
    # above either returns or continues, so the loop never exits normally
    return record


def refresh_report(models: list[Model], live: set[str]) -> dict:
    """Compare the curated dataset against live OpenRouter model ids.

    Reports rows that no longer exist upstream and free models that exist
    upstream but are not yet curated. Never edits the dataset: the
    benchmark and specialization fields are hand-rated.
    """
    curated = {m.name for m in models}
    return {
        "dead_in_curated": sorted(curated - live),
        "live_free_not_in_curated": sorted(
            i for i in live if i.endswith(":free") and i not in curated
        ),
        "curated_count": len(curated),
        "live_count": len(live),
    }


async def run_consensus(
    entries: list[dict],
    prompt: str,
    api_key: str,
    catalog: dict[str, Model],
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict:
    """Fan the prompt out to all entries in parallel and aggregate results.

    Args:
        entries: Roster entries, each with keys model, role, system_prompt.
        prompt: User question sent to every model.
        api_key: OpenRouter bearer token.
        catalog: Model objects keyed by model id for per-model cost calculation.
        transport: Optional async transport override for testing.

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
            *[call_model(client, e, prompt, api_key, catalog) for e in entries],
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
            "error": f"{type(res).__name__}: {res}",
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
    p_select.add_argument("--level", type=int, required=True, choices=[1, 2, 3])
    p_select.add_argument("--domain", default="code_review", choices=DOMAIN_CHOICES)
    p_select.add_argument("--limit", type=int, default=None)
    p_select.add_argument(
        "--no-validate", action="store_true", help="Skip live OpenRouter validation"
    )

    p_estimate = sub.add_parser("estimate", help="Cost preview for a level")
    p_estimate.add_argument("--level", type=int, required=True, choices=[1, 2, 3])
    p_estimate.add_argument("--domain", default="code_review", choices=DOMAIN_CHOICES)

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

    sub.add_parser("refresh", help="Diff curated dataset against the live catalog")
    return parser


def _read_json_file(path: str, what: str) -> object:
    """Read and parse a JSON file, exiting cleanly on missing or invalid input."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        emit({"error": f"cannot read {what} {path}: {exc}"}, stream=sys.stderr)
        raise SystemExit(2) from exc


def build_entries(args: argparse.Namespace, roles_data: dict) -> list[dict]:
    """Resolve run arguments into model entries with system prompts."""
    entries: list[dict] = []
    if args.roster_file:
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
    roster = select_roster(models, bands, roles, args.level, args.domain, live=live)
    limit = getattr(args, "limit", None)
    if limit is not None:
        roster = roster[:limit]
    fallbacks = select_fallbacks(
        models,
        bands,
        args.level,
        exclude={r["model"] for r in roster},
        live=live,
    )
    emit(
        {
            "level": args.level,
            "domain": args.domain,
            "roster": roster,
            "fallbacks": fallbacks,
            "estimated_cost_usd": round(sum(r["est_cost_usd"] for r in roster), 6),
            "cap_usd": LEVEL_COST_CAPS_USD[args.level],
        }
    )
    return 0


def _substitute_failures(
    outcome: dict,
    fallbacks: list[str],
    roles_data: dict,
    prompt: str,
    api_key: str,
    catalog: dict[str, Model],
) -> dict:
    """One substitution round: re-run failed entries on fallback models.

    Each failed result hands its role to the next unused fallback candidate.
    Substituted originals stay in the results list so the operator sees both
    the failure and its replacement; a substitutions map links them.
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
    retry_outcome = asyncio.run(run_consensus(retry_entries, prompt, api_key, catalog))
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


def _cmd_run(
    args: argparse.Namespace,
    models: list[Model],
    roles: dict,
) -> int:
    """Handle the run subcommand; return an exit code."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        emit({"error": "OPENROUTER_API_KEY is not set"}, stream=sys.stderr)
        return 1
    try:
        prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        emit(
            {"error": f"cannot read prompt file {args.prompt_file}: {exc}"},
            stream=sys.stderr,
        )
        return 2
    entries = build_entries(args, roles)
    catalog = {m.name: m for m in models}

    # Read fallbacks from the roster file (second read; double-read is acceptable per
    # spec: simplest route over refactoring build_entries to accept a pre-loaded obj).
    if args.roster_file:
        roster_payload = _read_json_file(args.roster_file, "roster file")
        fallbacks: list[str] = (
            roster_payload.get("fallbacks", [])
            if isinstance(roster_payload, dict)
            else []
        )
    else:
        # --models mode: user-named panels are never substituted
        fallbacks = []

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
    outcome = asyncio.run(run_consensus(entries, prompt, api_key, catalog))

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
            outcome, fallbacks, roles, prompt, api_key, catalog
        )

    # Recompute unknown across all result models (substitutes may also be uncatalogued).
    unknown = [r["model"] for r in outcome["results"] if r["model"] not in catalog]
    if unknown:
        outcome["warning"] = (
            "models not in curated catalog, cost unknown and not capped: "
            + ", ".join(unknown)
        )
    emit(outcome)
    return 0 if outcome["succeeded"] else 3


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; returns a process exit code."""
    args = build_parser().parse_args(argv)
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
    emit(refresh_report(models, live))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
