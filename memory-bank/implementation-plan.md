# Implementation Plan

1. Add .env.example, gitignore, pytest.ini, requirements, memory files. Validate files exist.
2. Implement Settings with provider validation, cheapest defaults, trailing-slash strip.
3. Implement media path resolver that creates outputs/images and outputs/videos and rejects drive/project root.
4. Implement markdown chunking + InMemoryStore indexing with embed wrapper and fake embeddings in tests.
5. Implement gateway image client and DashScope video client using env params only.
6. Implement StateGraph: assistant, search_kb tools, review_media interrupt, approve/skip media.
7. Implement FastAPI contract and Streamlit HTTP client with HITL card.
8. Add mocked tests covering cheapest payloads, path rules, KB hit, HITL, API media URLs, Streamlit preview mapping. Run pytest.
