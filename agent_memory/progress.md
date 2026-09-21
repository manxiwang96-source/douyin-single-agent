# Progress

## Current task
Continue plaza/sidebar design discussion on top of `docs/modify/抖音运营智能体修改设计方案（1）.md`. Discussion only. Do not rewrite the modify doc until the user says so. No worker SQL/Dify client unless separately asked.

## Status
Table product decisions are confirmed in conversation (not yet in the modify doc). Current open topic: later custom agents that can pick classmate C Dify workflows — ToolNode vs MCP.

## Confirmed (conversation only)
- Unlock many douyin_ops instances per user
- Name unique per user, case-insensitive, no whitespace, archived names reusable
- Sidebar capability copy is catalog capability_description, not SYSTEM_PROMPT, not user intro
- Mode display-only single
- Build empty agent_knowledge_documents now; current vector search is process-local InMemoryStore
- Opening chat does not bump updated_at

## Next
- Lock: keep Dify in ToolNode + DifyClient + catalog/binding; do not wrap Dify as MCP
- After remaining technical logic is confirmed, update modify doc plus architecture Next redesign, then tests