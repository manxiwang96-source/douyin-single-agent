# Progress

- Scaffolded config, media, KB, clients.
- Rewrote graph to LangGraph get-started 1-5 shape (chatbot + tools, HITL in tools).
- FastAPI contract + Streamlit thin client delivered.
- Upgraded product identity to 个人超级助理 on the same chatbot + tools graph.
- Production memory is PostgresSaver + PostgresStore; tests keep InMemorySaver.
- FastMCP stdio weekday/weather tools join the existing ToolNode.
- SMTP morning brief + hydrate jobs, APScheduler, and POST /v1/assistant/jobs/run are in place.
- Default mocked pytest: 76 passed, 5 skipped.
- 阶段 0：目录/提示词/Dify Settings/demo KB/默认停调度已写入；现网图仍是个人超级助理。下一阶段是业务表与仓库。
