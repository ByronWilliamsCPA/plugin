# Consensus Skill Data Files

Salvaged 2026-06-11 from zen-mcp-server (docs/models/ and
tools/custom/consensus_roles.py). Hand-rated fields; never auto-edited.
Updates go through the refresh-data workflow.

## What the engine reads (the contract)

- models.csv: ONLY these columns: model, provider, input_cost, output_cost,
  humaneval_score, swe_bench_score, context, specialization. The tier, role,
  rank, status, org_level, strength columns are legacy zen metadata, retained
  for human reference only; they contain known inconsistencies (duplicate
  ranks, tier labels not present in bands_config, one role value with no
  definition) and MUST NOT be consumed by code.
- context values are strings like "131K" or "1M"; multiply K by 1,000 and M by
  1,000,000 (the engine's parse_context handles this).
- bands_config.json: ONLY the cost_tier_bands section (free, economy, value,
  premium) and the tier_pins section. Band objects sit alongside metadata keys (band_strategy,
  description, note); access bands by name, never iterate keys. The value
  (1.01-10.00) and premium (4.00+) ranges intentionally overlap; the roster
  selector deduplicates by model name, so a model in the overlap may be
  selected through either band. All other sections (tier_classification_bands,
  org_level_assignment_bands, org_level_requirements, role_assignment_bands,
  provider_info, provider_trust_bands, etc.) are legacy zen metadata and
  unconsumed.
- tier_pins maps a roster tier (a key of TIER_FALLBACK_ORDER: free, economy,
  premium) to model ids tried first for that tier, ahead of benchmark order
  and regardless of price band. Levels are additive, so an economy pin sits in
  levels 2 and 3. Pins still pass live validation; an id missing from
  models.csv is skipped. Pins are not priced at selection time: the level cost
  cap applies to the whole roster when `run` starts and aborts the run rather
  than skipping an expensive pin, so keep pinned models cheap enough to fit the
  cap of every level that includes their tier. Current pins (2026-09-23): free -> openai/gpt-6-luna, so level 1
  carries one paid frontier-family seat (about $0.001 per run); economy ->
  openai/gpt-6-sol, moonshotai/kimi-k3, to give level 2 frontier-class
  members. A pin under free is the one case where a paid model fills a free
  slot on purpose.
- roles.json: role_definitions (19 roles) and domain_roles (4 domains,
  additive levels 1-3). This file is internally consistent; domain_roles
  references only defined roles.

## Benchmark score provenance

`humaneval_score` and `swe_bench_score` are hand-rated, and for models with no
published run they are ESTIMATES from provider positioning, not measured
results. Every `:free` row added in the 2026-08-25 refresh is in that category:
the free tier turned over completely (all 20 previous free rows were retired
upstream), and the replacements are rated from model cards and parameter
counts. Treat their relative ordering as a curation judgement, not evidence.

The 2026-09-23 refresh followed the same rule. It swapped superseded paid
rows for their live successors (GPT-6 Sol/Luna/Astra, Claude Opus 5.5 and
Sonnet 5, Grok 4.7, Gemini 3.8 Flash, DeepSeek V4 Pro, Kimi K3, Mistral Medium
3.5), added GLM-5.3 and Qwen3.8 Max, removed three rows retired upstream
(`mistralai/mistral-large-2512`, `minimax/minimax-m3:free`,
`minimax/minimax-m2.7:free`), and added three free rows. Scores on every row it
touched are estimates set to rank each successor at or above its predecessor;
none is a measured result. `z-ai/glm-5.2:free` kept its scores but its live
context dropped from 256K to 32K.

This matters because the roster selector sorts each cost tier by
`(-humaneval, -swe_bench)`, so these estimates decide which three models fill a
level-1 panel. Re-rate them when real benchmark numbers land.

## Known gap: refresh does not detect price drift

`consensus_cli.py refresh` diffs model IDs only. It cannot see a live price
change on a model that is still alive. `input_cost` alone assigns a model to a
cost tier band (`models_in_cost_tier`), but the cost cap (`estimate_model_cost`)
reads both `input_cost` and `output_cost`. The 2026-08-25 refresh found 10 rows
whose prices had drifted, one by 7.3x (`openai/o4-mini`, 0.15 -> 1.10).
Re-check both fields against `https://openrouter.ai/api/v1/models` during any
refresh, not just liveness.
