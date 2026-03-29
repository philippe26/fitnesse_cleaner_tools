# MHTML Cleaner

`mhtml-cleaner.py` is a Python utility that converts an MHTML file into a standalone HTML file that displays correctly in a browser without a local server.

## Features

- **MHTML → HTML conversion**: extracts the HTML section and removes the multipart structure
- **Automatic CSS injection**: extracts embedded stylesheets from the MHTML and injects them into a `<style>` tag
- **Localhost link replacement**: converts `http://localhost:<port>/...` links into local anchors `#` or removes them
- **Base64 image injection**: extracts embedded images and inlines them directly into the HTML
- **Automatic port detection**: dynamically identifies the port used in the MHTML file
- **Main page detection**: automatically identifies the reference page for anchor conversion
- **Optional button removal**: strips editing buttons from the original interface
- **Optional sidebar removal**: strips the side navigation panel

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
| `--remove-all` | `-A` | off | Preset: enables `-b`, `-s`, `-v` |
| `--verbose` | `-v` | off | Print details of each transformation |
| `--validate` | `-V` | off | Run HTML validator on output after cleaning |
| `--database-file <file>` | | off | Export artifact database to a CSV file |
| `--version` | | | Show version number and exit |
| `--help` | `-h` | | Show help |

---

## Cleaning levels

### `--level light`

Replaces only links pointing to the main page with local anchors.

```html
<!-- Before -->
<a href="http://localhost:<port>/MyDocument#section1">Section 1</a>

<!-- After -->
<a href="#section1">Section 1</a>
```

### `--level moderate` (default)

In addition to `light`:
- Disables links to inaccessible resources (`/files/...`, `/FrontPage`, etc.) → `#`
- Disables links to other pages → `#`

### `--level strict`

Same as `moderate`, but actively removes non-functional links instead of replacing them with `#`.

---

## Examples

### Standard conversion (output defaults to `input.html`)
```bash
python3 mhtml-cleaner.py input.mhtml
```

### Specify output file
```bash
python3 mhtml-cleaner.py input.mhtml -o output.html
```

### Full cleanup with verbose output
```bash
python3 mhtml-cleaner.py input.mhtml -A
```

### Buttons and sidebar removed, strict level
```bash
python3 mhtml-cleaner.py input.mhtml -b -s --level strict
```

### Keep original links (even broken ones)
```bash
python3 mhtml-cleaner.py input.mhtml --preserve-fitnesse
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
URLs with 3 or more dot-separated parts (`Doc.Type.ObjectId`) point to a specific artifact. The query string is stripped and the path becomes the anchor. The object is also recorded in the artifact database.

```
href="http://localhost:50020/PidS.DeF.EquipmentPosition"            →  href="#PidS.DeF.EquipmentPosition"
href="http://localhost:50020/PidS.DeF.EquipmentPosition?attributes" →  href="#PidS.DeF.EquipmentPosition"
```

### Special case — Image src
`src` attributes matching the pattern `?file&name=<img_name>` are **not rewritten**. They are left intact for the base64 injection step, which extracts the corresponding multipart section and replaces the URL with a `data:image/...;base64,...` inline value.

```
src="http://localhost:50020/PidS.DeF.FrameFamous?file&name=frame.png"
  →  src="data:image/png;base64,..."
```

---

## Processing pipeline

The script applies transformations in the following order:

1. Read the MHTML file and detect the port
2. Extract the HTML section + decode quoted-printable encoding
3. Clean malformed HTML tags
4. Replace localhost links (according to the chosen level)
5. Inject embedded CSS into a `<style>` tag
6. Extract and inject images as base64
7. Clean data URLs in CSS
8. Remove buttons _(if `-b` or `-A`)_
9. Remove sidebar _(if `-s` or `-A`)_
10. Remove `cid:` references (MHTML-specific)
11. Save as plain HTML

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

Anchor links point to sections that no longer exist in the document. This is expected for links that referenced other pages — they are replaced with `#`.

### Main page not detected correctly

Use `-v` to check the `Main page` line. The script attempts three detection methods in sequence: MHTML header, most frequent URLs, HTML title tag.

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
    verbose=True
)

success = cleaner.clean()
```
