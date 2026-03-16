# ShopSense - AI Shopping Assistant

## Project Overview
ShopSense is a microservices demo app for Groundcover DevRel, built with Python/FastAPI. It showcases observability patterns across 4 services.

## Architecture
- **Gateway** (port 8000): API routing, CORS, request logging
- **Catalog** (port 8001): Product CRUD, search, seed data
- **Recommendation** (port 8002): LLM-powered product suggestions
- **Orders** (port 8003): Cart management, checkout

## Your Task

1. Read the PRD at `prd.json` (in the same directory as this file)
2. Read the progress log at `progress.txt` (check Codebase Patterns section first)
3. Check you're on the correct branch from PRD `branchName`. If not, check it out or create from main.
4. Pick the **highest priority** user story where `passes: false`
5. Implement that single user story
6. Run quality checks: `cd services/<service> && python -m py_compile main.py` for each changed service, and `docker-compose config` for compose changes
7. Update CLAUDE.md files if you discover reusable patterns
8. If checks pass, commit ALL changes with message: `feat: [Story ID] - [Story Title]`
9. Update the PRD to set `passes: true` for the completed story
10. Append your progress to `progress.txt`

## Quality Checks
- Python syntax: `python -m py_compile <file>` for each .py file changed
- Docker Compose: `docker-compose config` to validate compose file
- Type hints required on all function signatures
- Use Pydantic models for all request/response schemas

## Progress Report Format

APPEND to progress.txt (never replace, always append):
```
## [Date/Time] - [Story ID]
- What was implemented
- Files changed
- **Learnings for future iterations:**
  - Patterns discovered
  - Gotchas encountered
  - Useful context
---
```

## Codebase Patterns
- Services communicate via HTTP using httpx async client
- Each service runs on its own port: gateway=8000, catalog=8001, recommendation=8002, orders=8003
- Docker service names match directory names: gateway, catalog, recommendation, orders
- All endpoints use Pydantic models for request/response validation
- Environment variables for configuration (SERVICE_URL pattern)

## Stop Condition

After completing a user story, check if ALL stories have `passes: true`.
If ALL stories are complete, reply with: <promise>COMPLETE</promise>
