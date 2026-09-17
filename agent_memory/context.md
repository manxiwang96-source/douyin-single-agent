# Context

## Product
Xiaohongshu operations assistant MVP: chat copywriting, cheap image generation, cheap video generation.

## Locked constraints
- Architecture follows LangGraph get-started 1-5: StateGraph, tools, SQLite memory, HITL, custom state.
- Graph nodes are `chatbot` and `tools` only. Media HITL uses `interrupt()` inside generate_image / generate_video.
- Out of scope: Tavily, Xiaohongshu login/publish, time travel.
- Media only under project outputs/ subdirs; never D:\\ or project root.
- Demo KB: Markdown -> InMemoryStore + SiliconFlow BAAI/bge-m3.
- Streamlit is a thin HTTP client; FastAPI is the contract.
- Default pytest is fully mocked. RUN_LIVE_API=1 enables cheapest live smokes.

## Runtime
- Chat: OPENAI_API_BASE_URL + OPENAI_API_MODEL
- Image: IMAGE_PROVIDER=gateway only
- Video: VIDEO_PROVIDER=dashscope (aliyun_wan3 alias)
- HITL before image/video generation
- FastAPI factory: uvicorn app.main:create_app --factory

## Documentation
- MVP recap: docs/summary/小红书运营助手对话机器人MVP总结与逻辑复盘（1）.md
- LangGraph knowledge map: docs/knowledge/LangGraph智能体创建知识地图：多智能体协作与任务编排.md
