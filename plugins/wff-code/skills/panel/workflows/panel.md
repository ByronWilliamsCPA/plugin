# Flexible Panel

Ad-hoc multi-model consultation: any models, any roles or stances.

## Procedure

1. **Choose models.** If the user named models, use them verbatim. Otherwise
   pick 3-5 from `data/models.csv` spanning at least two providers; prefer
   high `humaneval_score` within the user's cost comfort.

2. **Assign stances or roles (optional).** Build a roles file mapping each
   model to either a role name from `data/roles.json` (for example
   `system_architect`) or a literal system prompt:

   ```bash
   cat > /tmp/panel-roles.json << 'ROLES'
   {
     "openai/gpt-5.1": "Argue FOR the proposal. Steelman it.",
     "anthropic/claude-opus-4.6": "Argue AGAINST the proposal. Find the flaws.",
     "deepseek/deepseek-chat:free": "technical_validator"
   }
   ROLES
   ```

3. **Write the prompt file** (self-contained question plus context).

4. **Run.** Pass `--max-cost` if the user approved a budget. Without
   `--level` and without `--max-cost` no cap is enforced, so state the
   expected cost before running paid models. Watch for the `warning` key:
   models outside the curated catalog are not cost-capped at all.

   ```bash
   uv run .claude/skills/panel/scripts/consensus_cli.py run \
     --prompt-file /tmp/panel-prompt.txt \
     --models "openai/gpt-5.1,anthropic/claude-opus-4.6,deepseek/deepseek-chat:free" \
     --roles-file /tmp/panel-roles.json \
     --max-cost 2.00
   ```

5. **Synthesize** per SKILL.md. With for/against stances, present the
   strongest case each side made before your verdict.
