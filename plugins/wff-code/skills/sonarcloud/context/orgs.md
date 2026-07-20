# Org-Specific Instance Details

Per-organization MCP server routing, Docker container configuration, and
known project bindings for the `sonarcloud` skill. Kept separate from
`SKILL.md` so the skill body stays generic and portable across machines;
this file holds the `byronwilliamscpa`- and `williaby`-specific values.

## MCP Server Routing

The port follows the SonarCloud organization, not the GitHub organization.

| Organization | MCP Server Name | Port | MCP Tool Prefix |
|-------------|----------------|------|-----------------|
| `byronwilliamscpa` | `sonarqube` | 8090 | `mcp__sonarqube__` |
| `williaby` | `sonarqube-williaby` | 8091 | `mcp__sonarqube-williaby__` |

Both servers are Docker containers running in HTTP transport mode. They are
registered globally in `~/.claude/settings.json` and available to all
projects.

## Reachability Probe

The proven probe is a request to the `/mcp` endpoint:

```bash
curl -sf http://localhost:8090/mcp   # byronwilliamscpa
curl -sf http://localhost:8091/mcp   # williaby
```

Do not probe `/api/health`: it is a SonarQube Server endpoint and is not
confirmed to be served by these MCP bridge containers.

## Docker Container Restart Commands

If Docker or containers are down, use these commands to restart them:

```bash
# Start Docker Desktop from Windows (WSL2 environment)
# Then containers auto-restart. If containers were removed:
docker run --init -d --name sonarqube-mcp --restart unless-stopped \
  -v ~/.sonarqube-mcp-storage:/app/storage \
  -e SONARQUBE_TOKEN -e SONARQUBE_ORG=byronwilliamscpa \
  -e SONARQUBE_TRANSPORT=http -e SONARQUBE_HTTP_PORT=8090 \
  -e SONARQUBE_HTTP_HOST=0.0.0.0 -p 8090:8090 mcp/sonarqube

docker run --init -d --name sonarqube-mcp-williaby --restart unless-stopped \
  -v ~/.sonarqube-mcp-storage-williaby:/app/storage \
  -e SONARQUBE_TOKEN -e SONARQUBE_ORG=williaby \
  -e SONARQUBE_TRANSPORT=http -e SONARQUBE_HTTP_PORT=8091 \
  -e SONARQUBE_HTTP_HOST=0.0.0.0 -p 8091:8091 mcp/sonarqube
```

## Infrastructure Checklist (per-org containers)

- [ ] `sonarqube-mcp` container is running on port 8090 (`byronwilliamscpa`)
- [ ] `sonarqube-mcp-williaby` container is running on port 8091 (`williaby`)

## Valid Organizations

Only `byronwilliamscpa` and `williaby` have a configured MCP server. Any
other organization value found in project config is unrecognized; no MCP
server is configured for it.

## Analyzer Cache Paths

Plugins are cached per org:

- `~/.sonarqube-mcp-storage/` (`byronwilliamscpa`)
- `~/.sonarqube-mcp-storage-williaby/` (`williaby`)

First start after clearing cache takes ~60s.

## Known Project Configurations

| Org | Project | Key | Region |
|-----|---------|-----|--------|
| byronwilliamscpa | .claude | `ByronWilliamsCPA_.claude` | EU |
| williaby | monte_carlo | `williaby_monte_carlo` | EU |
