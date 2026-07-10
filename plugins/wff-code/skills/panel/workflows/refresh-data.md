# Refresh Model Data

Keep `data/models.csv` aligned with the live OpenRouter catalog. The script
never edits the dataset; benchmark scores and specializations are hand-rated.

## Procedure

1. **Generate the report.**

   ```bash
   uv run .claude/skills/panel/scripts/consensus_cli.py refresh
   ```

2. **Remove dead rows.** For each model in `dead_in_curated`, delete its row
   from `.claude/skills/panel/data/models.csv` (or fix the id if the
   model was renamed upstream; check https://openrouter.ai/models).

3. **Curate additions sparingly.** From `live_free_not_in_curated`, add only
   models worth consulting (recognizable provider, plausible quality). A new
   row needs: rank (append after existing), model id, provider, tier,
   status, context (like `131K`), input_cost, output_cost, org_level,
   specialization, role, strength, humaneval_score and swe_bench_score
   (estimate from public benchmarks; mark estimates honestly), openrouter
   URL, and today's date. Remember the engine only reads the columns listed
   in `data/README.md`; the rest are reference metadata.

4. **Verify.**

   ```bash
   uv run .claude/skills/panel/scripts/consensus_cli.py select --level 1
   uv run pytest tests/unit/test_consensus_cli.py -q --no-cov
   ```

5. **Commit** the dataset change with a `chore(panel): refresh model data`
   message.
