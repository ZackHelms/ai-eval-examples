# Test-site element inventory

The kinds of UI elements and page layouts the local test site should offer,
so Playwright scripts written against it meet what scripts for enterprise
analytics web apps meet. Generic by rule (CLAUDE.md § Project pins: generic
content only): it names no real product, and the site's UI is original.

First pass 2026-10-31: common patterns of enterprise single-page apps
(dashboards, reporting, investigation, data tooling). A hands-on pass on
real apps (TODO.md § Needs Zack) confirms which ones break scripts in
practice. It records pattern names only.

## Issue families

Each element below feeds one or both of the two families the evals grade
(rubric `script-fix-v0`):

- **Drift:** a release changes the DOM (labels, roles, structure), so a
  locator or assertion needs updating.
- **Timing:** the assertion that ends a transaction doesn't prove the page
  is ready, so the next transaction's first action (e.g. `click()`) times
  out. The fix is a better assertion at the end of the previous
  transaction.

## Elements

| Element | Why scripts break on it | Family |
|---|---|---|
| App switcher (hamburger → drawer), user menu | menu items render in a popup at the end of the page; clicking before it opens times out; role `menuitem` vs `link` drifts | timing, drift |
| Sign-in page, session cookies, session-expiry redirect | journey setup; a redirect in the middle of a journey | timing |
| Page or workspace tabs | a tab's panel loads lazily: assert its content before acting in it; tab names change | timing, drift |
| Collapsible side panes with tabs (data, objects, properties, …) | the same label appears in several panes (strict mode); hidden-pane elements are in the DOM but not visible | drift |
| Drag from a pane to a canvas; drag to rearrange | `drag_to` timing; drop targets that appear only while dragging | timing |
| Charts (bar, line, pie, treemap, …) | SVG marks may have weak or no accessible names; canvas charts have no DOM at all (then use coordinates or a data-table view); hover tooltips | drift |
| Data grids and crosstabs (virtualized rows, sticky and sortable headers) | rows exist only once scrolled into view; repeated cell text breaks strict mode; sorting reorders asynchronously | timing, drift |
| Custom drop-down (combobox, not a native `<select>`) | options render in a popup listbox; `select_option` doesn't work; roles `combobox`/`option` | drift, timing |
| Multi-select list with checkboxes; toggle-button bar (`aria-pressed`) | weak accessible names; asserting toggle state | drift |
| Filter text input (debounced); slider and range slider | results update after a delay; sliders need keyboard or drag | timing |
| Busy indicator or overlay while data loads | the classic timing failure: the next click hits the overlay and times out; the fix is to assert the overlay is hidden or the loaded content visible | **timing** |
| Filter panels, modal dialogs, multi-step wizards, confirmations | role `dialog`; focus trapping; Next/Finish buttons that are disabled until the form is valid | timing, drift |
| Toast notifications, status messages | they disappear on their own: assert them quickly or not at all | timing |
| Context (right-click) menus, per-object "more options" menus | icon-only buttons whose accessible name changes between releases | drift |
| Folder tree with expand and collapse (`tree`/`treeitem`), lazy children | children appear after an expand request | timing |
| Search with facets, a results list, a query builder (nested rule rows) | asynchronous results; repeated row controls (strict mode, `.nth`) | timing, drift |
| Detail pages: many labeled fields, view and edit modes, validation, date pickers, file upload | `get_by_label` drift; custom calendar popups; `set_input_files` | drift |
| Network (node-link) diagram: expand node, zoom, pan | usually canvas or SVG; coordinates or keyboard; layout animation | timing |
| Map with markers, area search | tile loading; markers as icons without names | timing |
| Timeline (horizontal scrolling, events) | off-screen items | drift |
| Code editor with autocomplete; a log tab | `fill` doesn't work on editor surfaces: type instead; autocomplete popups steal keys | drift |
| Flow canvas: nodes, ports, connections | dragging connections between ports | timing |
| Embedded content: iframes, web components | `frame_locator`; Playwright pierces open shadow DOM but not closed | drift |
| Generated IDs and class names (framework-made) | CSS or XPath locators break every release, while role and label locators survive | **drift** |
| Localized labels | name-based locators change with the locale | drift |

## Pages

1. **Shell:** sign-in, a top bar with an app-switcher drawer, user menu and
   toasts.
2. **Content:** a folder tree, a file grid with context menus, recent and
   favorite lists.
3. **Report viewer:**
   - page tabs and a canvas grid holding an SVG chart, a canvas chart, a
     virtualized table and a crosstab;
   - a filter row: combobox, multi-select list, toggle bar, text input,
     range slider;
   - a busy overlay whenever a filter changes.
4. **Report designer:** side panes (data items, objects) that drag onto the
   canvas, property-pane tabs (a form, field roles), a maximize toggle.
5. **Investigation:**
   - search with facets and a query builder, and a results grid;
   - record pages with tabs (fields, related records, a network diagram, a
     map, a timeline);
   - an alert queue with a decision dialog, and a case wizard with an
     attachment upload.
6. **Data studio:** a code editor, a log tab and a small flow canvas.

## Settings per component

- **Release switch:** a "next release" DOM, with renamed labels, changed
  roles, an extra wrapper, a new consent dialog or a moved control.
  These produce **drift** cases.
- **Fixed delay:** a seeded delay per component (data load, overlay time,
  lazy tab, tree children). The broken script then fails every time, and
  only a correct end-of-transaction assertion passes. These produce
  **timing** cases, the reliable kind the rubric needs for one-replay
  grading.

## Build notes (for the design step, not decided)

- Fully local: no CDN, seeded data, served on localhost or from a
  container.
- Open-source components with correct ARIA roles, e.g. for the grid,
  combobox, tree, tabs, dialog, charts (one SVG, one canvas), map with
  local tiles, network graph, code editor and flow canvas.
- One site serves single-user replays. Multi-user runs are out of scope
  for now (CD, 2026-10-31: single-user experiments first).
- New element kinds can come from any app type. Each one is added as an
  original component of that kind, never a copy of a product's look,
  names, icons or text.
