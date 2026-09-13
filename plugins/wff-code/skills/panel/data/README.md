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
  premium). Band objects sit alongside metadata keys (band_strategy,
  description, note); access bands by name, never iterate keys. The value
  (1.01-10.00) and premium (5.00+) ranges intentionally overlap; the roster
  selector deduplicates by model name, so a model in the overlap may be
  selected through either band. All other sections (tier_classification_bands,
  org_level_assignment_bands, org_level_requirements, role_assignment_bands,
  provider_info, provider_trust_bands, etc.) are legacy zen metadata and
  unconsumed.
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
