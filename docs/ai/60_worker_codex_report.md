# Worker Report

## Summary
SOT-1248 is ACTIONABLE for IMPLEMENT. The human selected 案A → 案B → (必要に応じ)案C.

**Fallback disclosure (audit):** Codex CLI was non-responsive (usage-limit cooldown, run_codex.sh
exit 75). Per the Worker Non-Response Fallback Policy, Claude Code performed this initial task-check
investigation directly (read-only). Implementation will be attempted via Gemini first.

booking-monitor is **FastAPI + Jinja2** (not Flask). 7 templates each carry a large duplicated
inline `<style>` block. Static is already mounted at `/static` — so a shared `/static/app.css` is viable.

## Changed Files
- none (read-only task check)

## Commands Run
- `git checkout main && git pull` (clean tree, HEAD = 82b4754 Merge #52 SOT-1244)
- `find . -name '*.html'` ; per-template `<style>` line counts ; grep for StaticFiles/url_for

## Findings
- Templates (templates/*.html), inline `<style>` line counts:
  calendar=59, config=48, history=64, login=22, monitor=100, notification_history=138, status=118.
- Static serving: `booking_monitor/web/__init__.py` mounts `StaticFiles(directory=.../static)` at `/static`.
  Only `static/i18n.js` exists today (no CSS). Each template loads `<script src="/static/i18n.js" defer>`.
- Duplicated design tokens across templates:
  - background `#f5f5f5`, text `#333`
  - nav gradient `linear-gradient(90deg,#1f2d3d,#2c3e50)`, brand-mark gradient `#3b82f6→#14b8a6`
  - `.card` white / border `#e8eaed` / radius 12px / shadow `0 1px 2px rgba(16,24,40,.06)`
  - `.alert` / `.alert-error` (#ffebee/#ef9a9a/#c62828)
  - green availability `.slot-available #66bb6a`
  - mobile bottom-nav fixed bar at `@media (max-width:600px)`
- Quality gate: `ruff` (pyproject [tool.ruff]), `pytest` (e2e separated by `-m e2e` marker), Jinja compile.
  No npm/Node — FastAPI server-rendered.
- i18n constraint: static/i18n.js matches **visible Japanese text nodes**; CSS-only refactor (案A) and
  visual refresh (案B/C) must preserve visible Japanese strings and element IDs/classes used by JS.
- Files each option touches:
  - 案A: new `static/app.css`; add `<link rel=stylesheet>` to all 7 templates; move shared inline CSS out.
  - 案B: `static/app.css` (refresh tokens/components) + template markup tweaks (cards/badges/buttons).
  - 案C: `templates/calendar.html` (legend sticky, hover tooltip, mobile sticky col), `monitor.html`/`history.html`/`notification_history.html` (zebra rows, status badges) + app.css.

## Acceptance Criteria
- [x] Issue confirmed actionable (human selected A→B→C)
- [x] UI/CSS state reported

## Risks
- Large CSS consolidation across 7 templates risks subtle visual regression; mitigate by keeping 案A
  visually identical (tokens only) and verifying Jinja compile + pytest each step.
- Must not break i18n.js (visible JP text nodes + class/id hooks).

## Next Action
READY_FOR_REVIEW
