# ADR 015 — Frontend Shell & Design System Foundation

**Status:** Accepted  
**Issue:** #13  
**Date:** 2026-05-15

---

## Context

Issue #13 establishes the shared foundation every other frontend screen builds on: CSS framework, design tokens, layout shell, sidebar, API client, and a small set of shared components. Several decisions made when the issue was written are now stale — no shadcn/ui is installed, and the issue references React Router v6 while v7 is installed.

---

## Decisions

### 1. CSS Framework — Tailwind CSS v4 (plain, no shadcn/ui)

**Decision:** Install Tailwind CSS v4 with the Vite plugin. No shadcn/ui. Custom component classes written directly with Tailwind utilities.

**Rationale:** shadcn/ui was never installed and importing it now adds Radix UI, class-variance-authority, and a large preset that fights the custom design system defined in `design-system/stow/MASTER.md`. Tailwind v4 uses CSS-native `@theme` variables instead of a `tailwind.config.js`, which maps cleanly to the token table in MASTER.md.

**Design tokens baked into `index.css`:**
- `--font-sans: "IBM Plex Sans"` / `--font-mono: "IBM Plex Mono"` (Google Fonts)
- Background: zinc-50 (`#FAFAFA`), Surface: white, Border: zinc-200
- Accent: blue-600, Income: emerald-600, Expense: red-600, GST: violet-600, Investments: cyan-600

---

### 2. API Client — thin `fetch` wrapper, no extra package

**Decision:** A single `frontend/src/lib/api.ts` module that wraps `fetch` with the base URL from `import.meta.env.VITE_API_BASE_URL`, throws on non-2xx, and returns JSON. No axios, no ky.

**Rationale:** The backend is local (Docker Compose); there are no auth headers, no retries needed at the client layer, and no streaming. A 20-line wrapper covers all requirements without adding a dependency. TanStack Query handles caching and error states.

**Query key factory:** co-located in `api.ts` — `queryKeys.transactions.list(filters)`, etc.

---

### 3. Sidebar — 56px icon-only, fixed

**Decision:** The sidebar is a fixed 56px icon-only strip. No expand/collapse toggle.

**Rationale:** All 8 HTML mockups show a `w-14` icon-only sidebar with no collapse control, and the issue description explicitly says "56px icon-only sidebar, fixed left." MASTER.md mentions a collapsible variant but the mockup is the implemented reference. Keeping it icon-only simplifies the component and matches every visual reference.

**Tooltip rule:** Shown on hover for all nav items (150ms opacity transition, absolute positioned right of icon).

---

### 4. Router Layout — React Router v7 nested layout route

**Decision:** `App.tsx` gains a single layout route (`<Route element={<Shell />}>`) that renders `<Sidebar />` + `<Outlet />`. All 8 page routes nest under it. Pages are imported directly (no lazy loading for now — the app is small).

**Layout structure:**
```
<Shell>               ← flex row, h-screen
  <Sidebar />         ← fixed width (240px / 56px), overflow-y auto
  <main>              ← flex-1, overflow-y auto
    <Header />        ← sticky, 56px, page title + FY badge
    <Outlet />        ← page content, max-w-7xl mx-auto px-6 py-6
  </main>
</Shell>
```

---

### 5. Shared components built in this issue

| Component | Description |
|---|---|
| `<MonoAmount>` | Formats paise → `₹X,XX,XXX.XX` (Indian locale), IBM Plex Mono, emerald/red colouring |
| `<TxnBadge>` | `payment\|receipt\|journal\|contra` pill badge |
| `<Sheet>` | Right-side sliding panel, 440px, overlay backdrop, click-outside close |
| `<EmptyState>` | Icon + heading + subtext, playful copy from MASTER.md |
| `<PageHeader>` | Title + optional action slot (right-aligned) |
| `<Tooltip>` | Hover tooltip for accounting terms, `?` trigger icon |

All components live in `frontend/src/components/`.

---

## Consequences

- All subsequent issues inherit Tailwind v4 tokens — no per-issue CSS setup needed.
- The `fetch` wrapper is thin; if streaming or auth is ever needed, swap to `ky` without touching call sites.
- Removing lazy loading keeps bundle tooling simple; add if initial load becomes slow.
- `<AccountDetail>` route (`/accounts/:id`) nests under the same shell — no extra layout needed.
