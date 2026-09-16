# Architecture

## Layout
- app/config.py: Settings from env, cheapest image/video params, provider validation
- app/media_paths.py: outputs/images and outputs/videos, reject drive/project root
- app/embeddings.py / app/knowledge.py: hashing embed in tests; InMemoryStore RAG
- app/image_client.py: Gateway POST /images/generations
- app/video_client.py: DashScope async video-synthesis + poll
- app/tools.py: search_kb executes immediately; generate_image/generate_video call interrupt then Command(update=...)
- app/graph.py: tutorial graph — chatbot + tools (ToolNode) + tools_condition; custom last_image_path / last_video_path
- app/runtime.py: wires LLM, store, checkpointer (SqliteSaver prod, InMemorySaver tests)
- app/main.py: FastAPI factory create_app(runtime=None); no import-time live boot
- app/serialize.py: thread JSON with media URLs and review_media interrupt
- ui/view_model.py: maps media URLs to image/video widgets; HITL card vs chat history
- ui/streamlit_app.py: thin HTTP client, st.chat_message + st.chat_input, HITL above chat
- knowledge/*.md: demo KB
- tests/: mocked suite + optional live smokes

## Graph
START -> chatbot -> tools_condition -> tools -> chatbot
                              \-> END
Media tools interrupt inside ToolNode. Resume with Command(resume=...).
parallel_tool_calls=False.

## Runtime processes
1. uvicorn app.main:create_app --factory
2. streamlit run ui/streamlit_app.py
