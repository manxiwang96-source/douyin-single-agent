# Progress

## Current task
Fix Streamlit not showing the latest user message while the live API request is in flight.

## Status
Complete. Pending user text is echoed immediately; tests 38 passed, 4 skipped.

## Done
- with_pending_user() echoes the in-flight user bubble
- streamlit_app keeps pending_user in session_state and shows a spinner during POST
- Reloaded Streamlit on :8501

## Next
- None for this task
