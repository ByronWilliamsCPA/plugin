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
