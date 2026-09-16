# Tech Stack

- Python 3.11, existing venv
- FastAPI + uvicorn: HTTP contract
- Streamlit: thin chat UI
- LangGraph StateGraph + interrupt HITL
- langgraph-checkpoint-sqlite
- LangGraph InMemoryStore + langchain-openai OpenAIEmbeddings (SiliconFlow bge-m3)
- httpx for gateway image and DashScope video
- pydantic-settings for env
- pytest with full mocks by default
