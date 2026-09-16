# Design Document

## Scope
Chat-based Xiaohongshu operations assistant. Users provide product facts; the agent writes notes, can generate one cheap image and one cheap video after HITL approval.

## Non-goals
Tavily search, Xiaohongshu login/publish, time travel, shipping tutorial chapters as product features.

## User journeys
1. User starts a thread in Streamlit chat.
2. If product facts are missing, assistant asks.
3. Assistant searches KB, then writes 【标题】【正文】【标签】.
4. If user asks for image/video, graph interrupts at review_media. User edits prompt/params and Approve/Skip.
5. Approved media is saved under outputs/images or outputs/videos and previewed inside the assistant bubble.

## State
MessagesState + last_image_path + last_video_path + media_items. SQLite checkpointer at data/checkpoints.sqlite.

## API contract
GET /health, GET /v1/config, POST /v1/threads, GET /v1/threads/{id}, POST /v1/threads/{id}/messages, POST /v1/threads/{id}/resume, GET /v1/media/{images|videos}/{file}.

## Acceptance
Mocked pytest green. Cheapest payloads asserted. HITL skip does not call media clients. Streamlit view model passes absolute media URLs to st.image/st.video.
