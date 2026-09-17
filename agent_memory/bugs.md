# Bugs and Risks

## Open
- Live ChatOpenAI against aitokens.website/gpt-5.6-sol can exceed 20s even for a short ping; morning brief now times out the graph and still sends facts by SMTP.

- ~/.codex/templates/agent_memory/ is missing; agent_memory files were created without a local template copy.
- Live DashScope/Gateway calls are not a default delivery gate; cost and network can fail independently of mocked tests.
- Hashing embeddings are test-only; live retrieval quality depends on bge-m3.
- The langgraph.com.cn mirror can lag upstream documentation or change routes; learning links should be revalidated periodically.

## Closed
- graph.ainvoke appeared to hang: PostgresSaver aget_tuple and scripted+postgres ainvoke were fine. The gateway request without max_tokens did not finish, so ChatOpenAI waited until the 90s live timeout. Fixed by max_tokens/timeout plus facts-email fallback.

- Importing app.main used to call app_from_env() and could hit real embeddings during pytest.
- Streamlit cleared chat_input on submit and only redrew bubbles after POST returned, so the latest user text vanished during the wait. Fixed by echoing pending_user immediately.
