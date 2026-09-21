# Progress

## Current task
Continue plaza/sidebar design discussion. Discussion only. Do not rewrite the modify doc until the user says so.

## Status
User agreed: reserve agent_instance_workflows now; later more Dify workflows than douyin-lead-discovery. Open: explain bind_tools recommendation and whether current tables cover user/agent/thread/call-status.

## Confirmed (conversation only)
- Many instances per user; unique title; capability_description != SYSTEM_PROMPT; mode read-only single
- Empty agent_knowledge_documents; chat does not bump updated_at
- Dify stays in ToolNode + DifyClient; not MCP
- Reserve binding table; catalog stays server config; users pick from our catalog not arbitrary App IDs

## Next
- After remaining technical logic is confirmed, update modify doc plus architecture Next redesign, then tests