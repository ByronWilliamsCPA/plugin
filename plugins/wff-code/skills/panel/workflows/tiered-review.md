# Tiered Review (IT review team)

Structured multi-model review with levels and professional roles.

## Procedure

1. **Select the roster.** Pick the domain from the user's topic (security
   questions get `security`, design questions get `architecture`, code gets
   `code_review`, anything else `general`).

   ```bash
   uv run .claude/skills/panel/scripts/consensus_cli.py select --level <N> --domain <domain> > /tmp/panel-roster.json
   cat /tmp/panel-roster.json
   ```

2. **Present roster and cost.** Show the user the models, roles, and
   `estimated_cost_usd`. For level 1 proceed without waiting. For level 2-3,
   confirm with the user before running unless they already approved the
   level explicitly.

3. **Write the prompt file.** Include the user's question plus any context
   they supplied. Keep it self-contained; the models see nothing else.

   ```bash
   cat > /tmp/panel-prompt.txt << 'PROMPT'
   <the question, with context>
   PROMPT
   ```

4. **Run.**

   ```bash
   uv run .claude/skills/panel/scripts/consensus_cli.py run \
     --prompt-file /tmp/panel-prompt.txt \
     --roster-file /tmp/panel-roster.json \
     --level <N>
   ```

5. **Synthesize** per the requirements in SKILL.md. Structure the output as:
   executive summary (2-3 sentences), consensus points, disagreements with
   attribution, role-specific highlights worth noting, recommendation,
   actual cost and failures.

## Failure handling

- `failed > 0` but `succeeded >= 2`: synthesize and flag the gap. Note:
  automatic substitution runs before you see the result; if the output
  includes a `substitutions` key, report which models were swapped and that
  the panel reflects the replacements.
- `succeeded < 2`: do not synthesize a "consensus" from one voice. Report
  the errors and offer to rerun or escalate a level.
- Roster came back short (fewer models than the level promises): mention it;
  the live catalog validation likely dropped dead entries. Offer the
  refresh-data workflow.
