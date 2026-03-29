# CHANGELOG - mhtml-cleaner.py

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
