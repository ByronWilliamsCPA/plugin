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

   The report also carries `curated_without_zdr_endpoint`: curated model ids
   with no zero-data-retention endpoint. These rows are not dead, but a key
   requiring ZDR (`--zdr`/`OPENROUTER_ZDR`) cannot use them. No action is
   required here; it is informational context for anyone curating the free
   tier. If the ZDR endpoint fetch itself failed, this key is `null` and a
   `zdr_error` string explains why; the rest of the refresh still ran.

3. **Curate additions sparingly.** From `live_free_not_in_curated`, add only
   models worth consulting (recognizable provider, plausible quality). A new
   row needs: rank (append after existing), model id, provider, tier,
   status, context (like `131K`), input_cost, output_cost, org_level,
   specialization, role, strength, humaneval_score and swe_bench_score
   (estimate from public benchmarks; mark estimates honestly), openrouter
   URL, and today's date. Remember the engine only reads the columns listed
   in `data/README.md`; the rest are reference metadata.

4. **Check pins.** Every id under `tier_pins` in
   `.claude/skills/panel/data/bands_config.json` must still be a row in
   `models.csv`. A pin whose row was removed or renamed is skipped silently,
   so update or remove it here.

5. **Verify.**

   ```bash
   uv run .claude/skills/panel/scripts/consensus_cli.py select --level 1
   uv run pytest tests/unit/test_consensus_cli.py -q --no-cov
   ```

6. **Commit** the dataset change with a `chore(panel): refresh model data`
   message.
