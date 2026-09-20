# Progress

## Current task
Write the locked client entry (user → agent instance → thread) into `docs/modify/抖音运营智能体修改设计方案（1）.md`.

## Status
Design doc, document test, and memory-bank pointers are the delivery for this turn. No worker runtime code in this change.

## Done
- Locked client entry: 新建智能体 / 展示能力 / 用这个智能体. Capabilities are display-only.
- v1 one active `douyin_ops` instance per user. Added `agent_instances`; conversation/job/engage/media/account rows carry `agent_instance_id`.
- Graph still not changed. Official `checkpoints*` / `store` still not altered.
- Jobs remain cancellable from the client or from chat (`cancel_job` / disable definition).
- Kept classmate C confirmation list in the same design doc.

## Next
- Do not write worker business code until this doc remains the source of truth.
- Implement in the order listed in section 17 of the design doc.
