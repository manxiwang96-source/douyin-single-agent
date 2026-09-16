# Bugs and Risks

## Open
- ~/.codex/templates/agent_memory/ is missing; agent_memory files were created without a local template copy.
- Live DashScope/Gateway calls are not a default delivery gate; cost and network can fail independently of mocked tests.
- Hashing embeddings are test-only; live retrieval quality depends on bge-m3.

## Closed
- Importing app.main used to call app_from_env() and could hit real embeddings during pytest.
