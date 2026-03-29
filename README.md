# MHTML Cleaner

Two scripts for converting MHTML files to standalone HTML and validating the output.

| Script | Description |
|--------|-------------|
| `mhtml-cleaner.py` | Converts an MHTML file to a self-contained HTML file |
| `test-html-validator.py` | Validates an HTML file produced by the cleaner |

---

# mhtml-cleaner.py

Converts an MHTML file into a standalone HTML file that displays correctly in a browser without a local server.

## Features

- **MHTML → HTML conversion**: extracts the HTML section and removes the multipart structure
- **Automatic CSS injection**: extracts embedded stylesheets from the MHTML and injects them into a `<style>` tag
- **Localhost link replacement**: converts `http://localhost:<port>/...` links into local anchors or removes them
- **Base64 image injection**: extracts embedded images and inlines them directly into the HTML
- **Automatic port detection**: dynamically identifies the port used in the MHTML file
- **Artifact database**: builds a cross-reference index of all artifact definitions (`Doc.Type.Object`)
- **Hover tooltips** _(optional)_: shows the full artifact definition when hovering over a link
- **Optional button removal**: strips editing buttons from the original interface
- **Optional sidebar removal**: strips the side navigation panel
- **HTML validation** _(optional)_: runs `test-html-validator.py` automatically on the output

---

## Requirements

- Python 3.7+
- No external dependencies

---

## Usage

```bash
python3 mhtml-cleaner.py input.mhtml [options]
```

### Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--output` | `-o` | input name with `.html` extension | Output file |
| `--level {light,moderate,strict}` | `-l` | `moderate` | Link cleaning level |
| `--preserve-fitnesse` | `-p` | off | Keep FitNesse links even if broken |
| `--remove-buttons` | `-b` | off | Remove editing buttons |
| `--remove-sidenav` | `-s` | off | Remove the side navigation panel |
| `--include-hovering` | `-H` | off | Inject JS hover tooltips for artifact links |
| `--all` | `-A` | off | Preset: enables `-b`, `-s`, `-v`, `-V`, `-H` |
| `--verbose` | `-v` | off | Print details of each transformation |
| `--validate` | `-V` | off | Run HTML validator on output after cleaning |
| `--database-file <file>` | | off | Export artifact database to a CSV file (`.csv` added if omitted) |
| `--version` | | | Show version number and exit |
| `--help` | `-h` | | Show help |

---

## Cleaning levels

### `--level light`

Replaces only links pointing to the main page with local anchors.

```
href="http://localhost:<port>/Doc.DocName#7"  →  href="#7"
```

### `--level moderate` (default)

In addition to `light`:
- Disables links to inaccessible resources (`/files/fitnesse/`, `/FrontPage`, etc.) → `#`
- Disables links to other pages → `#`

### `--level strict`

Same as `moderate`, but actively removes non-functional links instead of replacing them with `#`.

---

## Examples

### Standard conversion
```bash
python3 mhtml-cleaner.py input.mhtml
```

### Full cleanup: buttons, sidebar, hover tooltips, validation
```bash
python3 mhtml-cleaner.py input.mhtml -A
```

### Export artifact database
```bash
python3 mhtml-cleaner.py input.mhtml --database-file artifacts
# → writes artifacts.csv
```

### Hover tooltips only
```bash
python3 mhtml-cleaner.py input.mhtml -H
```

### Validate output without cleaning options
```bash
python3 mhtml-cleaner.py input.mhtml -V
```

---

## URL resolution logic

All localhost URLs follow the pattern:

```
http://localhost:<port>/<doc_prefix>.<doc_name>[?options][#fragment]
```

After quoted-printable decoding, the script applies these decision rules to every `href` and `src` attribute:

### Rule 1 — System resource → removed
URLs pointing to FitNesse system resources (`/files/fitnesse/`, `/FrontPage`, `/RecentChanges`, etc.) are stripped entirely.

### Rule 2 — Fragment present → local anchor
Any URL containing `#fragment` is converted to that anchor, regardless of the page it points to.

```
href="http://localhost:50020/Doc.DocName?flatPage#7"  →  href="#7"
href="http://localhost:50020/Doc.DocName#42"          →  href="#42"
```

### Rule 3 — Doc-level URL (2 dot-parts) → neutral anchor
URLs with exactly 2 dot-separated path parts (`Doc.DocName`) with no fragment become `#`.

```
href="http://localhost:50020/Doc.DocName?edit"  →  href="#"
```

### Rule 4 — Artifact URL (3+ dot-parts) → named anchor + database entry
URLs with 3 or more dot-separated parts (`Doc.Type.ObjectId`) point to a specific artifact. The query string is stripped and the path becomes the anchor. The object is recorded in the artifact database.

```
href="http://localhost:50020/PidS.DeF.EquipmentPosition"            →  href="#PidS.DeF.EquipmentPosition"
href="http://localhost:50020/PidS.DeF.EquipmentPosition?attributes" →  href="#PidS.DeF.EquipmentPosition"
```

### Special case — Image src
`src` attributes with `?file&name=<img_name>` are **not rewritten**. They are left intact for the base64 injection step.

```
src="http://localhost:50020/PidS.DeF.FrameEth?file&name=frame.png"
  →  src="data:image/png;base64,..."
```

---

## Artifact database

The script scans all `<div id="Doc.Type.Object">` elements and builds an in-memory database. The object id can have multiple dot-separated parts (`MibCont.TreeMain.FeLin` is valid).

Only artifacts whose doc prefix matches the current document are indexed (cross-document references are ignored).

When `--database-file` is specified, the database is exported as a CSV with columns:

| Column | Description |
|--------|-------------|
| `id` | Full artifact id (`PidS.DeF.EquipmentPosition`) |
| `document` | Doc prefix (`PidS`) |
| `type` | Artifact type (`DeF`) |
| `object` | Object id, may include sub-parts (`EquipmentPosition`) |
| `description` | Short description extracted from the `<b>` title |

---

## Hover tooltips (`--include-hovering` / `-H`)

When active, hovering over any `<a href="#Doc.Type.Object">` displays a floating panel with the full content of the target `<div>`. The panel is limited to 30% of the screen height; a `▼ truncated` indicator appears if the content is clipped.

The native browser `title=` tooltip is suppressed when this option is active (both would show simultaneously otherwise). Without `-H`, the short description remains visible as a standard `title=` attribute.

---

## Processing pipeline

1. Read MHTML file and detect port
2. Extract HTML section + decode quoted-printable encoding
3. Clean malformed HTML tags
4. Replace localhost links (according to chosen level)
5. Inject embedded CSS into a `<style>` tag
6. Extract and inject images as base64
7. Clean data URLs in CSS
8. Build artifact database
9. Add hover tooltips _(if `-H`)_ or native `title=` attributes
10. Remove buttons _(if `-b` or `-A`)_
11. Remove sidebar _(if `-s` or `-A`)_
12. Inject hover JS+CSS _(if `-H`)_
13. Remove `cid:` references (MHTML-specific)
14. Save as plain HTML
15. Run validator _(if `-V`)_

---

## Output

The generated HTML file is **100% self-contained**:
- Works offline, no server required
- Opens in Edge, Chrome, and Firefox
- CSS and images embedded inline
- Internal navigation via anchors

---

## Troubleshooting

### Page displays without styles
The CSS was not injected. Use `-v` to check that CSS sections are detected in the MHTML.

### Anchors do not work
Links that referenced other pages are replaced with `#` — this is expected.

### Main page not detected correctly
Use `-v` to check the `Main page` line. The script tries three detection methods in sequence: MHTML header, most frequent URLs, HTML title tag.

---

## Use as a Python module

```python
from mhtml_cleaner import MHTMLCleaner

cleaner = MHTMLCleaner(
    input_file='input.mhtml',
    output_file='output.html',
    level='moderate',
    remove_buttons=True,
    remove_sidenav=True,
    include_hovering=True,
    verbose=True
)
success = cleaner.clean()
```

---

---

# test-html-validator.py

Validates an HTML file produced by `mhtml-cleaner.py` and reports errors and warnings.

## Usage

```bash
python3 test-html-validator.py output.html [options]
```

### Options

| Option | Short | Description |
|--------|-------|-------------|
| `--quiet` | `-q` | Print summary only, no per-test details |
| `--version` | | Show version number and exit |
| `--help` | `-h` | Show help |

---

## Tests performed

| Test | Level | Description |
|------|-------|-------------|
| HTML structure | error | Checks for `<!DOCTYPE>`, `<html>`, `<head>`, `<body>` |
| No `cid:` references | error | MHTML-specific resource references must be absent |
| No multipart structure | error | The file must not contain MIME boundaries |
| Images injected | warning | Counts `data:image/...;base64,` inline images |
| CSS injected | error | A `<style>` tag must be present |
| No localhost in src/href | error | No unresolved `localhost:<port>` URLs remaining |
| No `file://` URLs | error | No local filesystem URLs |
| Tags properly closed | error | `<html>`, `<head>`, `<body>` must be balanced |
| Anchors present | warning | Numeric anchors (`#0`, `#1`…) must exist for navigation |
| Artifact links have a definition | error | Every `href="#Doc.Type.Object"` must have a matching `div id` |
| Artifact definitions are all used | warning | Every `div id="Doc.Type.Object"` should be referenced by at least one link |
| No unresolved `[?]` placeholders | warning | `[?]` markers indicate unresolved references |
| File size reasonable | warning | Flags files that are suspiciously small or very large |

---

## Output example

```
============================================================
  HTML Validator — output.html
============================================================

  ✅ HTML structure
  ✅ No cid: references
  ✅ No multipart structure
  ✅ Images injected
       → 7 base64 image(s)
  ✅ CSS injected
       → 244 KB of CSS injected
  ✅ No localhost in src/href
  ✅ No file:// URLs
  ✅ Tags properly closed
  ✅ Anchors present
       → 59 anchor link(s), 59 anchor target(s)
  ✅ Artifact links have a definition
       → 272 artifact link(s), 272 definition(s)
  ✅ Artifact definitions are all used
       → all 272 definition(s) referenced
  ✅ No unresolved [?] placeholders
  ✅ File size reasonable
       → 1.24 MB

============================================================
Result: 13 passed / 0 failed
============================================================

✅ All tests passed — file is ready.
```
