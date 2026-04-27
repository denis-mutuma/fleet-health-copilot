# Release Notes

## 2026-04-27

### Highlights

- Added a dedicated authenticated chat workspace at `/chat` for incident operations.
- Added persistent chat sessions and message history in orchestrator storage.
- Made retrieval visibly grounded in the UI via grouped RAG citations per assistant response.
- Added chat-driven operational actions for incident workflows.

### Chat Capabilities

- Ask RAG questions and receive citation-backed answers.
- Report incidents from chat using structured natural language:

```text
report incident metric=battery_temp_c device=robot-03 value=74.2 threshold=65
```

- Run operational commands:
  - `/list incidents`
  - `/open <incident_id>`
  - `/status <incident_id> <open|acknowledged|resolved>`
  - `/checklist [incident_id]`
  - `/simulate`

### API Additions

- `POST /v1/chat/sessions`
- `GET /v1/chat/sessions`
- `GET /v1/chat/sessions/{session_id}`
- `POST /v1/chat/sessions/{session_id}/messages`

### Web Additions

- New chat page: `apps/web/src/app/chat/page.tsx`
- New client chat workspace: `apps/web/src/app/chat/chat-client.tsx`
- New API proxy routes under `apps/web/src/app/api/chat/`
- New chat client library: `apps/web/src/lib/chat.ts`

### Validation

- `npm run quality:check` passed.
- Orchestrator tests passed including chat endpoint coverage.
- Web lint/build passed with production Next.js build.
