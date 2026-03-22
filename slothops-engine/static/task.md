# static/ — Dashboard UI

This folder contains the single-page dashboard served by the FastAPI engine.

---

## Responsibilities

- Show all tracked issues and their current pipeline stage
- Connect to the SSE stream for real-time updates
- Display PR links when status = `pr_created`
- Serve directly from FastAPI — NO build step required

---

## Checklist

### `index.html`
- [ ] Load TailwindCSS via CDN (no npm, no build)
- [ ] Load Google Font (e.g., Inter) for clean typography
- [ ] On page load: `fetch('/issues')` → render issue list
- [ ] Open `EventSource('/stream')` for real-time updates
- [ ] On SSE event: update the relevant issue card in the DOM
- [ ] Each issue card shows:
  - [ ] Error type + message (truncated)
  - [ ] Pipeline status badge (color-coded):
    - `received` → gray
    - `triaging` → blue
    - `classified` → blue
    - `fixing` → yellow
    - `pr_created` → green (link to PR)
    - `pr_creation_failed` / `fixing_failed` → red
    - `recommendation_only` → purple
  - [ ] Confidence badge (high / medium / low)
  - [ ] Occurrence count
  - [ ] Timestamp
- [ ] Clicking a card expands to show root cause and file changes
- [ ] Infra / unknown issues shown in a separate "skipped" section

---

## Implementation Notes

- Use `EventSource` (not WebSocket) — matches server-sent events on the backend
- Keep JS vanilla — no React, no Vue, no build toolchain
- Dashboard should work even if opened mid-demo after some issues have already been processed
