# Worker Report

## Summary
SOT-1255 (案A: 共有CSS化＋デザイントークン化) implemented.

**Fallback disclosure (audit):** Gemini CLI was non-responsive (IneligibleTierError —
"This client is no longer supported for Gemini Code Assist for individuals", run_gemini.sh exit 75)
and Codex CLI was in usage-limit cooldown (exit 75). Per the Worker Non-Response Fallback Policy,
Claude Code performed this implementation and verification directly. Quality gates applied unchanged.

Extracted the duplicated design shell from the 6 nav-based templates into a new shared stylesheet
`static/app.css` and converted the common values to CSS custom properties (design tokens). Appearance
is unchanged (tokens resolve to the prior literal values; page-specific CSS remains inline and still
wins where it differs).

## Changed Files
- `static/app.css` — NEW. `:root` design tokens + shared shell: `*`, `body`, full `nav` (+ mobile
  bottom-bar `@media`), `main`, `.alert/.alert-error/.alert-warning/.alert-success`, `.card`,
  `.card h2`, `.overflow-x`.
- `templates/calendar.html` — link app.css; removed shared shell rules + nav `@media` lines.
- `templates/config.html` — link app.css; kept page-unique `main { max-width: 900px }` override.
- `templates/history.html` — link app.css; removed shared shell; kept responsive-table mobile block.
- `templates/monitor.html` — link app.css; removed shared shell.
- `templates/notification_history.html` — link app.css; removed shared shell (incl. `.alert-success`).
- `templates/status.html` — link app.css; removed shared shell (kept slot-grid + `:has` mobile rule).

## Not changed (by design)
- `templates/login.html` — intentionally NOT linked to app.css. It is a self-contained centered-card
  auth page; its `.card` relies on the default `content-box` model, so inheriting app.css's global
  `* { box-sizing: border-box }` would shrink the card (visual regression). Left fully unchanged.

## Commands Run
- Jinja compile of all 7 templates → `jinja ok`
- `ruff check .` → All checks passed!
- `python -m pytest -q -m "not e2e"` → 91 passed, 22 skipped (async, pre-existing), 4 deselected
- CSS brace balance check per template → balanced

## Acceptance Criteria
- [x] `static/app.css` 新設、6つの nav テンプレが参照（login は意図的に対象外＝設計上の判断）
- [x] 主要トークンが CSS変数化（bg/text/nav-grad/brand-grad/card/alert/available 等）
- [x] 見た目は現状踏襲（トークンは従来の値に解決、ページ固有CSSはinline維持）
- [x] ruff / pytest / Jinja compile pass

## Risks
- Zero-visual-change relies on app.css loading before each page's inline `<style>`; verified the
  `<link>` is placed before `<style>` in all 6 templates.
- login.html consciously excluded; documented above.

## Next Action
READY_FOR_REVIEW
