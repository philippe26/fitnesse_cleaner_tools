# CHANGELOG - mhtml-cleaner.py
---

## v2.8.0 — 2026-04-02

### Fix: export date fallback from XLS file
When a row's date annotation (column C) is empty on export, the script now falls back to the file's `return_date` value (cell F5) as the date for that JSON entry. A `(fallback date)` marker is shown in verbose mode.

### New: standalone executables in `Releases/`

| Platform | File | Notes |
|----------|------|-------|
| Linux x86-64 | `Releases/Linux/mhtml-cleaner` | Built with PyInstaller, no Python required |
| Linux x86-64 | `Releases/Linux/SyncReviewExcel` | Built with PyInstaller, no Python required |
| Windows x86-64 | `Releases/windows/mhtml-cleaner.exe` | PE32+ console EXE, cross-compiled via Wine+PyInstaller |
| Windows x86-64 | `Releases/windows/SyncReviewExcel.exe` | PE32+ console EXE, cross-compiled via Wine+PyInstaller |

Usage on Windows (command prompt or PowerShell):
```
mhtml-cleaner.exe input.mhtml -R -A
SyncReviewExcel.exe import reviews.json --import-mode merge -v
```

---

### New: `SyncReviewExcel.py` — Excel ↔ JSON synchronisation script
New standalone script (replaces `review-xls-sync.py`) for importing and exporting review data between the JSON file produced by `mhtml-cleaner -R` and Excel peer-review forms (`.xls`).

#### Import modes (`--import-mode`)
| Mode | Behaviour |
|------|-----------|
| `merge` (default) | New entries appended; existing entries with changed date updated; unchanged skipped |
| `append` | New entries appended; existing entries (same artifact+text+context) skipped |
| `overwrite` | All data rows cleared, then JSON entries written from scratch |

Verbose reporting (`-v`) prints each row action (➕ new / 🔄 updated / ⏭ unchanged / 🗑️ cleared).

#### Export
Reads all valid XLS files, exports rows with at least Description or Severity. Empty placeholder rows (`Req :` with no Description/Severity) are skipped.

#### Summary cells updated on import
- **F3** `nb_items` — total rows in table
- **F4** `review_duration` — formatted `HH:MM` (max date − min date for this user)
- **F5** `return_date` — formatted `DD/MM/YYYY` (most recent review date)

#### Other features
- Auto-match JSON `user` → `reviewer_full_name` (substring, case-insensitive); `--map user:Full Name` to override
- `-y` / `--proceed` to skip confirmation prompt
- `--dir` to specify XLS folder independently of JSON file location

---

## v2.7.2 — 2026-04-02

### Fix: "Change status" prompt showed nothing (REVIEW_TAGS not defined)
`REVIEW_TAGS` was injected by Python only as an inline array literal in the `.forEach` call, leaving it undefined everywhere else in the script. It is now declared as a named JS variable (`var REVIEW_TAGS = [...]`) so `_changeStatus`, `_showMenu`, and any future function can all reference it.

---

### New: `--review-extra-tags`
When `-R` is active, the context menu shows only **Major**, **Minor**, **Comment** by default.
Adding `--review-extra-tags` extends the menu with **Operational**, **Significant**, and **Typo**.

| Tag | Colour | Meaning |
|-----|--------|---------|
| Operational | 🟣 purple | Impacts operation or safety |
| Significant | 🔶 orange | Significant non-conformity requiring resolution before approval |
| Major | 🔴 red | Blocking issue, non-conformity, or requirement violation |
| Minor | 🟠 amber | Non-blocking issue, suggestion, or improvement |
| Typo | 🟢 green | Typographical or formatting error |
| Comment | 🔵 blue | General remark, question, or observation |

### New: chapter/heading review (`-R`)
Headings `<h1>`–`<h5>` that carry both an `id` and a `title-numbering` attribute with dotted numeric values (e.g. `<h2 id="1.2" title-numbering="1.2">`) are now automatically made reviewable when `-R` is active. They receive the same right-click context menu as artifact divs, and review blocks appear inline below them. Reviews are stored with `artifact-type = "Section"` and `artifact = <title-numbering value>`.

### New: session-aware file connection logic
The behaviour when clicking **CONNECT JSON REVIEW FILE** now depends on whether `localStorage` already contains review data from an active session:

| Session state | Action | Behaviour |
|--------------|--------|-----------|
| Fresh (no LS data) | Open file | Load file directly |
| Fresh (no LS data) | New file | Create empty file |
| Active (LS has data) | Open file | Dialog: **Merge** (union, no duplicates) or **Replace** (file wins) |
| Active (LS has data) | New file | Dialog: **Save session data** into new file or **Discard** and start fresh |

Auto-reconnect (IndexedDB) always loads the file silently as source of truth.

### New: per-row actions in the review block
Each review entry now shows three small action buttons (visible only when a file is connected):
- **✏️** — edit the review text
- **🔄** — change the review status (choose from available tags)
- **❌** — delete this individual review

### New: Remove all in the right-click context menu
When reviews exist for an artifact, a **🗑️ Remove all reviews (N)** item appears at the bottom of the "add" section. A confirmation dialog is shown before deletion. Hidden when no reviews exist.

### New: chapter artifact id uses §-prefixed heading text
For headings (`<h1>`–`<h5>`), the JSON `artifact` field is now the visible heading text prefixed with `§` and with whitespace normalised:
- `<h1 title-numbering="7." ...>3        FUNCTIONAL DESCRIPTION</h1>` → `"artifact": "§3 FUNCTIONAL DESCRIPTION"`

The HTML attribute `artifact-label` carries this value; `artifact` holds a sanitised DOM slug for internal use.

### Fix: headings not matching for review (`-R`)
The regex for `title-numbering` now correctly handles trailing dots (e.g. `"5."`, `"1.2."`) and simple integer `id` values. Reviews on `<h1>`–`<h5>` headings now work as expected.

### New: hover indicator on reviewable elements
All elements with `artifact-type` and `artifact` attributes now show a dashed outline and `context-menu` cursor on hover, making reviewable headings and artifact divs clearly identifiable.

---

## v2.7.1 — 2026-03-31

### New: add types operational, significant to review

### New: add basic script for Excel VBA (& libreoffice)
Scripts import & export json in RPP excel files

---

## v2.7 — 2026-03-31

### New: traceability nav-pills transformation
`<ul class="nav nav-pills">` traceability blocks are now automatically transformed into clean static HTML dropdowns using `<details>`/`<summary>` elements — no JavaScript required:
- The "Traceability Links" label is rendered as a static badge
- Each dropdown button (Verified by, Allocated by, Complies, Satisfied by…) becomes a clickable `<details>` with its item list; edit links are stripped
- Item counts appear as coloured badges (grey when zero)

### New: `--remove-traceability` / `-t`
When active, traceability blocks are removed entirely instead of being transformed.

### New: `--include-review` / `-R` — file picker dialog
The `CONNECT JSON REVIEW FILE` button now opens an in-page dialog with two explicit choices:
- **Open existing file…** → `showOpenFilePicker` (no overwrite warning)
- **Create new file** → `showSaveFilePicker` (new file only)

This avoids the native browser "file will be overwritten" warning when opening an existing review file.

---

## v2.6 — 2026-03-29

### New: `--include-review` / `-R`
Injects a right-click review annotation system into the output HTML.

Right-clicking any artifact div (those with a non-empty `artifact-type` attribute) opens a context menu with three choices: **Add Major**, **Add Minor**, **Add Comment**. Clicking one prompts for a single line of text (OK / Cancel). On OK, the review is stored in `localStorage` with the following fields: user (login), artifact id, context (Major/Minor/Comment), text, and timestamp.

Reviews are loaded from `localStorage` on every page open and displayed inline below each artifact as `<div class="review">` blocks. Each entry shows a coloured badge (red = Major, orange = Minor, blue = Comment), the author name and date, and the review text.

The user name is set once via **Set user name…** in the menu (bottom item) and persisted across sessions. It can be changed at any time via **Change user (…)** in the same slot.

Review data is scoped to the document title, so multiple documents coexist in the same browser without interference.

---

## v2.5 — 2026-03-29

### New: `--include-hovering` / `-H`
Injects a JS + CSS hover tooltip system into the output HTML. Hovering over any `<a href="#Doc.Type.Object">` displays the full content of the target `<div>` in a floating panel capped at 30% of screen height, with a `▼ truncated` indicator when clipped. When active, the native `title=` attribute is suppressed to avoid double display.

### New: `-A` preset extended
`-A` / `--all` now enables `-b`, `-s`, `-v`, `-V`, and `-H`.

### Fix: validator output ordering
Test detail lines were printed before the ✅/❌ indicator. Details are now accumulated during the test and printed after the result line, so the indicator always appears first.

### Fix: validator false "0 unused" message
`Artifact definitions are all used` no longer prints `0 unused definition(s)` when everything is referenced — it now shows `all N definition(s) referenced`.

### New: validator section in README
`test-html-validator.py` is now documented with its full test list and an output example.

---

## v2.4 — 2026-03-29

### Fix: artifact database — regex and doc prefix filter
- Object id (`ZZ`) now supports multiple dot-separated camelCase parts: `FrameEth` and `MibCont.TreeMain.FeLin` are both valid
- Only artifacts whose doc prefix matches the current document are indexed (e.g. `PidS.*` only, excluding cross-document references like `Etso2c153.*`)
- CSV export: `object` column now contains the full id including sub-parts (`MibCont.TreeMain.FeLin`)

### Fix: URL resolution rewrite (`_resolve_href`)
- Unified decision logic for all localhost href/src attributes
- `src` image URLs (`?file&name=…`) are preserved for base64 injection and never rewritten
- 3-part+ artifact paths (`Doc.Type.Object`) correctly resolve to `#Doc.Type.Object`

### New: `--validate` / `-V`
Runs `test-html-validator.py` automatically on the output file after cleaning.

### New: `--database-file <file>`
Exports the artifact database to a CSV file with columns: `id`, `document`, `type`, `object`, `description`.

### New: `--version`
Both `mhtml-cleaner.py` and `test-html-validator.py` now support `--version`.

---

## v2.3 — 2026-03-29

### Fix: anchor links broken on cross-page references
`_normalize_localhost_link` only extracted fragments when the URL contained `main_page`. Links to other pages (e.g. `PidS.DocumentView?flatPage#2`) fell through to the fallback and lost their fragment, resulting in `#` instead of `#2`.

New logic: any localhost URL containing a `#fragment` is converted to that anchor directly, regardless of which page it points to. The `main_page` check is now only used for fragment-less links.

| URL | Before | After |
|-----|--------|-------|
| `Page?flatPage#2` | `#` | `#2` ✅ |
| `Page#7` | `#7` | `#7` ✅ |
| `OtherPage?query#5` | `#` | `#5` ✅ |
| `Page?edit` | `#` | `#` ✅ |

---

## v2.2.5 — 2026-03-29

### Changes
- **`--preserve-css` option removed**: it was declared but never implemented (dead code)

---

## v2.2.4 — 2026-03-29

### Changes
- **`-o` is now optional**: if omitted, the output file defaults to the input filename with a `.html` extension
- **`--format` option removed**: output is always plain HTML
- **`-A` / `--remove-all` added**: preset that enables `-b` (remove buttons), `-s` (remove sidenav), and `-v` (verbose) in a single flag
- **Comments and messages translated to English** throughout the script

---

## v2.2.3 — 2026-03-28

### Fix: button removal not working
Buttons had no `title` attribute, but the regex was matching on it. The `_remove_fitnesse_buttons()` method was rewritten to identify buttons by their text content instead.

### New feature
- **`--remove-sidenav`**: removes the side navigation panel (`<div id="sidenav">`, `<nav class="sidenav">`, `<aside class="sidebar">`) along with its associated CSS

---

## v2.2.2 — 2026-03-28

### Fixes
- **Numbered anchors preserved**: internal navigation anchors (`#0`, `#1`, …) are now correctly kept
- **Dynamic port detection**: the localhost port is automatically detected from the MHTML header instead of being hardcoded

---

## v2.2.1 — 2026-03-28

### Fixes
- **Uncorrupted base64**: removed spurious line breaks (`\n`) and backslashes in image base64 data
- **CSS data URLs**: fixed malformed URLs of the form `url("../../images/data:image/png;base64,...")` → `url("data:image/png;base64,...")`
  New method: `_clean_css_data_urls()`

---

## v2.2 — 2026-03-28

### Fixes
- **Malformed image URLs**: the image URL replacement was producing paths like `file:///home/.../data:image/...`. Fixed the regex replacement pattern.
- **Missing images**: dynamic icons absent from the MHTML (`collapsibleOpen.png`, `collapsibleClosed.png`, `collapse.gif`, `expand.gif`) are now replaced by auto-generated SVG placeholders.

### New feature
- **`--remove-buttons`**: removes editing buttons (Edit, Versions, Attributes, Review, Rationale, Expand, Collapse)

---

## v2.1 — 2026-03-28

### New features
- Extraction of images embedded in the MHTML and injection as base64 in the HTML output
- Generation of SVG placeholders for missing images
- Initial version of `--remove-buttons` (corrected in v2.2.3)

---

## v2.0 — 2026-03-28

### Initial release

- MHTML → plain HTML conversion (multipart structure removed)
- Embedded CSS injected into a `<style>` tag
- `localhost:<port>` links replaced by local anchors `#`
- Three cleaning levels: `light`, `moderate`, `strict`
- `--preserve-fitnesse` and `--preserve-css` options
- `--verbose` mode
- `--format html|mhtml` output format option
