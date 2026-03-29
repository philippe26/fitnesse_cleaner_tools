#!/usr/bin/env python3
"""
MHTML Cleaner - Converts MHTML files to standalone HTML
"""

__version__ = '2.6'

import re
import csv
import argparse
import sys
import quopri
from pathlib import Path
from typing import Tuple

# Optional: import validator if available in the same directory
try:
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location(
        'html_validator',
        Path(__file__).parent / 'test-html-validator.py'
    )
    _mod = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    HTMLValidator = _mod.HTMLValidator
except Exception:
    HTMLValidator = None


class MHTMLCleaner:
    """MHTML file cleaner"""

    FITNESSE_PATTERNS = [
        r'files/fitnesse/', r'files/bootstrap/', r'/FrontPage',
        r'/GaeL\.', r'/FitNesse\.', r'/RecentChanges',
    ]

    def __init__(self, input_file: str, output_file: str, level: str = 'moderate',
                 preserve_fitnesse: bool = False,
                 verbose: bool = False,
                 remove_buttons: bool = False, remove_sidenav: bool = False,
                 database_file: str = None,
                 include_hovering: bool = False,
                 include_review: bool = False):
        self.input_file = input_file
        self.output_file = output_file
        self.level = level
        self.preserve_fitnesse = preserve_fitnesse
        self.verbose = verbose
        self.remove_buttons = remove_buttons
        self.remove_sidenav = remove_sidenav
        self.database_file = database_file
        self.include_hovering = include_hovering
        self.include_review = include_review

        self.port = self._extract_port()
        self.main_page = self._extract_main_page_name()

    def _extract_port(self) -> int:
        """Detects the localhost port used in the MHTML file"""
        try:
            with open(self.input_file, 'r', encoding='utf-8', errors='ignore') as f:
                file_content = f.read(10000)

            match = re.search(r'http://localhost:(\d+)/', file_content)
            if match:
                port = int(match.group(1))
                if self.verbose:
                    print(f"  🔍 Port detected: {port}")
                return port
        except:
            pass

        return 50020

    def _extract_main_page_name(self) -> str:
        """Extracts the main page name from the MHTML file"""
        try:
            with open(self.input_file, 'r', encoding='utf-8', errors='ignore') as f:
                file_content = f.read(30000)

            # Method 1: Snapshot-Content-Location header
            match = re.search(r'Snapshot-Content-Location:\s+.*\/([^\s\/]+)', file_content)
            if match:
                result = match.group(1).strip()
                if result and result != 'files':
                    return result

            # Method 2: most frequent localhost URL (excluding system pages)
            urls = re.findall(rf'http://localhost:{self.port}/([^/?&\s"\']+)', file_content)
            url_counts = {}
            for url in urls:
                if not any(x in url for x in ['files', 'FrontPage', 'RecentChanges', 'GaeL', 'FitNesse']):
                    url_counts[url] = url_counts.get(url, 0) + 1

            if url_counts:
                top_url = max(url_counts, key=url_counts.get)
                return top_url

            # Method 3: HTML title tag
            match = re.search(r'<title[^>]*>([^<]+)</title>', file_content, re.IGNORECASE)
            if match:
                title = match.group(1).split('.')[0].strip()
                if title:
                    return title
        except:
            pass

        return "Unknown"

    def _extract_html_section(self, content: str) -> Tuple[str, int, int]:
        """Extracts the main HTML section from the MHTML content"""
        html_start = content.find('<!DOCTYPE')
        if html_start == -1:
            html_start = content.find('<!doctype')
        if html_start == -1:
            html_start = content.find('<html')
        if html_start == -1:
            html_start = content.find('<HTML')

        boundary_idx = content.find('\n------', html_start)
        if boundary_idx == -1:
            boundary_idx = len(content)

        return content[html_start:boundary_idx], html_start, boundary_idx

    def _should_remove_link(self, url: str) -> bool:
        """Returns True if the link should be removed"""
        if self.preserve_fitnesse:
            return False
        for pattern in self.FITNESSE_PATTERNS:
            if re.search(pattern, url, re.IGNORECASE):
                return True
        return False

    def _resolve_href(self, url: str) -> str:
        """Resolves a localhost href URL to a local anchor.

        Decision rules (applied on decoded URL, after &amp; → &):
          1. System resource (FitNesse CSS/JS, FrontPage…) → return '' (remove)
          2. URL contains #fragment → return '#fragment'
          3. Path has 2 dot-separated parts (doc-level, e.g. Doc.DocName) → return '#'
          4. Path has 3+ dot-separated parts (artifact, e.g. Doc.Type.Object) → return '#Doc.Type.Object'
             Query params (?attributes, ?responder=…) are stripped.
          5. Anything else → return '#'
        """
        url = url.replace('&amp;', '&')
        prefix = f'http://localhost:{self.port}/'
        if not url.startswith(prefix):
            return None

        if self._should_remove_link(url):
            return ''

        path = url[len(prefix):]

        # Rule 2: fragment present → use it as local anchor
        if '#' in path:
            frag = path.split('#', 1)[1]
            return f'#{frag}' if frag else '#'

        # Strip query string to classify path
        clean_path = path.split('?')[0]
        parts = clean_path.split('.')

        # Rule 3: 2 parts = doc-level URL (Doc.DocName) → neutral anchor
        if len(parts) == 2:
            return '#'

        # Rule 4: 3+ parts = artifact (Doc.Type.ObjectId[.sub…]) → local anchor
        if len(parts) >= 3:
            return f'#{clean_path}'

        return '#'

    def _is_image_url(self, url: str) -> bool:
        """Returns True if the URL is an image resource (src should not be rewritten)."""
        url = url.replace('&amp;', '&')
        return bool(re.search(r'[?&](?:file|name)=', url, re.IGNORECASE))

    def _process_html_attributes(self, html_content: str) -> str:
        """Rewrites localhost URLs in href and src attributes.

        - href: fully resolved via _resolve_href
        - src:  left unchanged if it is an image URL (handled later by base64 injection);
                otherwise resolved via _resolve_href
        """
        def replace_href(m):
            attr, url, quote = m.group(1), m.group(2), m.group(3)
            result = self._resolve_href(url)
            if result is None:
                return m.group(0)
            if result == '':
                return ''
            return f'{attr}{result}{quote}'

        def replace_src(m):
            attr, url, quote = m.group(1), m.group(2), m.group(3)
            if not url.startswith(f'http://localhost:{self.port}/'):
                return m.group(0)
            if self._is_image_url(url):
                return m.group(0)   # leave for base64 injection
            result = self._resolve_href(url)
            if result is None:
                return m.group(0)
            if result == '':
                return ''
            return f'{attr}{result}{quote}'

        html_content = re.sub(
            r'(href\s*=\s*["\'])([^"\']*?)(["\'])',
            replace_href, html_content, flags=re.IGNORECASE
        )
        html_content = re.sub(
            r'(src\s*=\s*["\'])([^"\']*?)(["\'])',
            replace_src, html_content, flags=re.IGNORECASE
        )
        return html_content

    def _process_form_actions(self, html_content: str) -> str:
        """Replaces localhost URLs in form action attributes"""
        def replace_action(m):
            url = m.group(2)
            result = self._resolve_href(url)
            if result is None:
                return m.group(0)
            if result == '':
                return ''
            return f' action="{result}"'

        pattern = r' action=(["\'])([^"\']*?)\1'
        return re.sub(pattern, replace_action, html_content, flags=re.IGNORECASE)

    def _decode_quoted_printable_section(self, content: str) -> str:
        """Fully decodes quoted-printable encoding using the quopri module"""
        try:
            # Remove soft line breaks (=\n or =\r\n)
            content = re.sub(r'=\r?\n', '', content)

            # Use quopri to decode all =XX sequences
            decoded = quopri.decodestring(content.encode()).decode('utf-8')
            return decoded
        except UnicodeDecodeError:
            # Fall back to latin-1 if UTF-8 decoding fails
            try:
                content = re.sub(r'=\r?\n', '', content)
                decoded = quopri.decodestring(content.encode()).decode('latin-1')
                return decoded
            except:
                # Last resort: return content as-is
                if self.verbose:
                    print("  ⚠️  quoted-printable decoding error")
                return content

    def _decode_quoted_printable_section_basic(self, content: str) -> str:
        """Basic quoted-printable decoder (fallback, static replacement table)"""
        lines = content.split('\n')
        decoded = []
        i = 0
        while i < len(lines):
            line = lines[i]
            while i < len(lines) and line.endswith('=') and not line.endswith('=='):
                line = line[:-1] + lines[i + 1]
                i += 1
            decoded.append(line)
            i += 1

        result = '\n'.join(decoded)

        replacements = {
            '=3D': '=', '=20': ' ', '=3B': ';', '=3A': ':',
            '=2F': '/', '=3F': '?', '=26': '&', '=22': '"',
            '=27': "'", '=0D': '\r', '=0A': '\n', '=09': '\t',
        }

        for encoded, decoded_char in replacements.items():
            result = result.replace(encoded, decoded_char)

        return result

    def _extract_and_inject_css(self, full_content: str, html_content: str) -> str:
        """Extracts embedded CSS sections from MHTML and injects them as a <style> tag"""
        css_sections = re.findall(
            rf'Content-Location: (http://localhost:{self.port}/files/fitnesse[^\n]+)\n\n(.+?)\n------',
            full_content, re.DOTALL
        )

        if not css_sections:
            if self.verbose:
                print("  ℹ️  No CSS to inject")
            return html_content

        injected_css = []
        for location, css_body in css_sections:
            css_decoded = self._decode_quoted_printable_section(css_body)
            injected_css.append(css_decoded)

            if 'fitnesse_wiki' in location or 'fitnesse-bootstrap' in location:
                if self.verbose:
                    size_kb = len(css_decoded) // 1024
                    print(f"  ✅ CSS injected: {location.split('/')[-1]} ({size_kb}KB)")

        combined_css = "\n\n".join(injected_css)
        style_tag = f'<style type="text/css">\n{combined_css}\n</style>'
        html_content = html_content.replace('</head>', f'{style_tag}\n</head>')

        if self.verbose:
            print(f"  📝 Total CSS injected: {len(combined_css) // 1024}KB")

        return html_content

    def _extract_and_inject_images(self, full_content: str, html_content: str) -> str:
        """Extracts base64 images from MHTML and inlines them as data URLs"""
        pattern = r'Content-Type: (image/\w+).*?\r?\nContent-Transfer-Encoding: base64\r?\nContent-Location: ([^\r\n]+)\r?\n\r?\n((?:[A-Za-z0-9+/=\r\n]+))'

        image_map = {}

        for match in re.finditer(pattern, full_content, re.MULTILINE | re.DOTALL):
            mime_type = match.group(1)
            location = match.group(2).strip()
            base64_data_raw = match.group(3)

            # Strip whitespace to get clean base64
            base64_data = ''.join(base64_data_raw.split())

            filename = location if location.startswith('cid:') else location.split('/')[-1]

            image_map[location] = {
                'mime': mime_type,
                'base64': base64_data,
                'filename': filename,
                'location': location
            }

            if self.verbose:
                size_kb = len(base64_data) // 1024
                print(f"  🖼️  Image extracted: {filename} ({size_kb}KB)")

        if not image_map:
            if self.verbose:
                print("  ℹ️  No images to inject")
            return html_content

        for location, img_info in image_map.items():
            mime_type = img_info['mime']
            base64_data = img_info['base64']
            data_url = f'data:{mime_type};base64,{base64_data}'

            escaped_location = re.escape(location)
            escaped_location_amp = re.escape(location.replace("&", "&amp;"))

            html_content = re.sub(
                rf'(["\'])({escaped_location}|{escaped_location_amp})(["\'])',
                lambda m: f'{m.group(1)}{data_url}{m.group(3)}',
                html_content, flags=re.IGNORECASE
            )

            filename = img_info['filename']
            if filename and not filename.startswith('cid:'):
                escaped_filename = re.escape(filename)
                html_content = re.sub(
                    escaped_filename,
                    data_url,
                    html_content, flags=re.IGNORECASE
                )

        # Fix malformed data URLs that may have a path prefix before "data:image/"
        html_content = re.sub(
            r'url\(\s*["\']([^"\']*?)data:image/',
            r'url("data:image/',
            html_content, flags=re.IGNORECASE
        )

        if self.verbose:
            print(f"  ✅ {len(image_map)} images injected")

        return html_content

    def _replace_remaining_localhost_links(self, html_content: str) -> str:
        """Replaces any remaining localhost URLs not handled in previous passes"""
        pattern = rf'((?:src|href)\s*=\s*["\'])([^"\']*?localhost:{self.port}[^"\']*?)(["\'])'

        def replacer(m):
            prefix = m.group(1)
            url = m.group(2)
            suffix = m.group(3)

            result = self._resolve_href(url)
            if result is None or result == '':
                return ''
            return f'{prefix}{result}{suffix}'

        return re.sub(pattern, replacer, html_content, flags=re.IGNORECASE)

    def _clean_malformed_tags(self, html_content: str) -> str:
        """Fixes duplicated or malformed HTML tags"""
        html_content = re.sub(r'<head>\s*<head[^>]*>', '<head>', html_content, flags=re.IGNORECASE)
        if html_content.count('</head>') > 1:
            parts = html_content.split('</head>')
            html_content = '</head>'.join(parts[:-1]) + '</head>' + parts[-1]

        html_content = re.sub(r'<body>\s*<body[^>]*>', '<body>', html_content, flags=re.IGNORECASE)
        html_content = re.sub(r'</body>\s*</body>', '</body>', html_content, flags=re.IGNORECASE)

        return html_content

    def _remove_fitnesse_buttons(self, html_content: str) -> str:
        """Removes editing buttons: matches <a>ButtonName</a> and <button>ButtonName</button>"""
        if not self.remove_buttons:
            return html_content

        buttons = ['Edit', 'Versions', 'Attributes', 'Review', 'Rationale', 'Expand', 'Collapse']

        for btn in buttons:
            # Match <a ...>ButtonName</a> (no title attribute needed)
            pattern1 = rf'<a[^>]*?>\s*{re.escape(btn)}\s*</a>'
            html_content = re.sub(pattern1, '', html_content, flags=re.IGNORECASE)

            # Match <button ...>ButtonName</button>
            pattern2 = rf'<button[^>]*?>\s*{re.escape(btn)}\s*</button>'
            html_content = re.sub(pattern2, '', html_content, flags=re.IGNORECASE)

        if self.verbose:
            print(f"  🗑️  Editing buttons removed")

        return html_content

    def _remove_sidenav_div(self, html_content: str) -> str:
        """Removes the sidenav panel and its associated CSS"""
        if not self.remove_sidenav:
            return html_content

        html_content = re.sub(
            r'<div[^>]*class=["\']?sidenav["\']?[^>]*>.*?</div>',
            '', html_content, flags=re.IGNORECASE | re.DOTALL
        )

        if self.verbose:
            print(f"  🗑️  Sidenav removed")

        return html_content

    def _build_artifact_database(self, html_content: str) -> dict:
        """Builds a database of artifact divs: {full_id: tooltip_text}

        Matches <div id="X.Y.ZZ"> where:
          - X  = doc prefix (must equal the doc prefix of main_page, e.g. "PidS")
          - Y  = object type, single camelCase word
          - ZZ = object id, one or more dot-separated camelCase words
                 e.g. "FrameEth" or "MibCont.TreeMain.FeLin"

        Extracts the short description from the nearest <b>...</b> after the div.
        """
        db = {}

        # Derive doc prefix from main_page (e.g. "PidS.DocumentView" → "PidS")
        doc_prefix = self.main_page.split('.')[0] if '.' in self.main_page else self.main_page

        # Pattern: X.Y.ZZ where X == doc_prefix, Y is one camelCase word,
        # ZZ is one or more dot-separated camelCase words (no digits, no spaces)
        pattern = rf'<div[^>]+id="({re.escape(doc_prefix)}\.[A-Za-z]+\.[A-Za-z]+(?:\.[A-Za-z]+)*)"'

        for m in re.finditer(pattern, html_content):
            full_id = m.group(1)

            # Extract tooltip from the nearest <b>...</b> in the following ~800 chars
            snippet = html_content[m.start():m.start() + 800]
            tooltip = ''
            title_m = re.search(r'<b>([^<]+)</b>', snippet)
            if title_m:
                tooltip = title_m.group(1).strip()

            db[full_id] = tooltip

        if self.verbose:
            print(f"  📚 Artifact database: {len(db)} entries (prefix: {doc_prefix})")

        return db

    def _export_database_csv(self, db: dict):
        """Exports the artifact database to a CSV file (id, type, object, description)"""
        with open(self.database_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'document', 'type', 'object', 'description'])
            for full_id, tooltip in sorted(db.items()):
                parts = full_id.split('.')
                doc   = parts[0]
                type_ = parts[1] if len(parts) > 1 else ''
                obj   = '.'.join(parts[2:]) if len(parts) > 2 else ''
                writer.writerow([full_id, doc, type_, obj, tooltip])
        if self.verbose:
            print(f"  💾 Database exported: {self.database_file} ({len(db)} entries)")

    def _add_artifact_tooltips(self, html_content: str, db: dict) -> dict:
        """Adds title= tooltip attributes to <a href="#Doc.Type.Object"> links
        using the description extracted from the database.
        """
        if not db:
            return html_content

        def add_title(m):
            full_tag = m.group(0)
            href_val = m.group(1)          # e.g. #PidS.DeF.EquipmentPosition
            artifact_id = href_val[1:]     # strip leading #

            if artifact_id not in db:
                return full_tag

            # When hovering is active, the JS tooltip replaces the native title —
            # skip adding title= to avoid showing both
            if self.include_hovering:
                return full_tag

            tooltip = db[artifact_id]
            if not tooltip:
                return full_tag

            if 'title=' in full_tag:
                return full_tag

            return full_tag.replace('<a ', f'<a title="{tooltip}" ', 1)

        pattern = r'<a\s[^>]*href="(#[A-Za-z]+\.[A-Za-z]+\.[A-Za-z]+)"[^>]*>'
        return re.sub(pattern, add_title, html_content, flags=re.IGNORECASE)

    def _inject_review_system(self, html_content: str) -> str:
        """Injects CSS + JS for a right-click review annotation system.

        Right-clicking any artifact div (with a non-empty artifact-type attribute)
        opens a context menu with Add Major / Add Minor / Add Comment.
        Reviews are persisted in localStorage and displayed below each artifact
        as <div class="review"> blocks.
        """
        css_js = r"""
<style id="review-system-style">
/* Context menu */
#review-context-menu {
  position: fixed;
  z-index: 10000;
  background: #fff;
  border: 1px solid #ccc;
  border-radius: 4px;
  box-shadow: 2px 4px 10px rgba(0,0,0,0.2);
  min-width: 175px;
  padding: 4px 0;
  font-size: 0.9em;
  font-family: sans-serif;
}
.review-menu-item {
  padding: 6px 16px;
  cursor: pointer;
  white-space: nowrap;
}
.review-menu-item:hover { background: #e8f0fe; }
.review-menu-sep { border-top: 1px solid #e0e0e0; margin: 4px 0; }
.review-menu-user { color: #666; font-style: italic; font-size: 0.85em; }
/* Review blocks */
div.review { margin: 0 0 6px 0; }
.review-entry {
  display: flex;
  align-items: baseline;
  gap: 6px;
  padding: 3px 8px;
  border-left: 3px solid #ccc;
  margin: 2px 0;
  font-size: 0.85em;
  font-family: sans-serif;
  background: #fafafa;
}
.review-entry.review-major   { border-left-color: #e53935; background: #fff5f5; }
.review-entry.review-minor   { border-left-color: #fb8c00; background: #fff8f0; }
.review-entry.review-comment { border-left-color: #1e88e5; background: #f0f4ff; }
.review-badge {
  font-weight: bold;
  font-size: 0.75em;
  text-transform: uppercase;
  padding: 1px 5px;
  border-radius: 3px;
  color: #fff;
  white-space: nowrap;
  flex-shrink: 0;
}
.review-major   .review-badge { background: #e53935; }
.review-minor   .review-badge { background: #fb8c00; }
.review-comment .review-badge { background: #1e88e5; }
.review-meta  { color: #888; font-size: 0.85em; white-space: nowrap; flex-shrink: 0; }
.review-text  { color: #333; }
</style>
<script id="review-system-script">
(function() {
  // localStorage keys — scoped to document title so multiple docs coexist
  var DOC_KEY   = 'mhtml-reviews:' + (document.title || location.pathname);
  var USER_KEY  = 'mhtml-review-user';

  // ── Persistence ──────────────────────────────────────────────────────────
  function loadReviews() {
    try { return JSON.parse(localStorage.getItem(DOC_KEY) || '[]'); }
    catch(e) { return []; }
  }
  function saveReviews(reviews) {
    localStorage.setItem(DOC_KEY, JSON.stringify(reviews));
  }
  function getUser() { return localStorage.getItem(USER_KEY) || ''; }
  function setUser(u) { localStorage.setItem(USER_KEY, u); }

  // ── Render review entries below an artifact div ───────────────────────────
  function renderReviews(artifactId) {
    var block = document.getElementById('review-block-' + CSS.escape(artifactId));
    if (!block) return;
    block.innerHTML = '';
    loadReviews()
      .filter(function(r) { return r.artifact === artifactId; })
      .forEach(function(r) {
        var entry = document.createElement('div');
        entry.className = 'review-entry review-' + r.context.toLowerCase();
        var badge = document.createElement('span');
        badge.className = 'review-badge';
        badge.textContent = r.context;
        var meta = document.createElement('span');
        meta.className = 'review-meta';
        meta.textContent = r.user + ' — ' + r.date;
        var text = document.createElement('span');
        text.className = 'review-text';
        text.textContent = r.text;
        entry.appendChild(badge);
        entry.appendChild(meta);
        entry.appendChild(text);
        block.appendChild(entry);
      });
  }

  // ── Insert review blocks after each non-container artifact div ────────────
  function initReviewBlocks() {
    document.querySelectorAll('[artifact-type][artifact]').forEach(function(div) {
      if (!div.getAttribute('artifact-type')) return;   // skip empty containers
      var aid = div.getAttribute('artifact');
      if (!aid) return;
      var block = document.createElement('div');
      block.id = 'review-block-' + CSS.escape(aid);
      block.className = 'review';
      div.parentNode.insertBefore(block, div.nextSibling);
      renderReviews(aid);
    });
  }

  // ── Context menu ──────────────────────────────────────────────────────────
  var menu = document.createElement('div');
  menu.id = 'review-context-menu';
  menu.style.display = 'none';
  document.body.appendChild(menu);

  function showMenu(x, y, artifactId) {
    menu.innerHTML = '';
    ['Major', 'Minor', 'Comment'].forEach(function(ctx) {
      var item = document.createElement('div');
      item.className = 'review-menu-item';
      item.textContent = 'Add ' + ctx;
      item.addEventListener('mousedown', function(e) { e.stopPropagation(); });
      item.addEventListener('click', function(e) {
        e.stopPropagation();
        hideMenu();
        addReview(artifactId, ctx);
      });
      menu.appendChild(item);
    });
    var sep = document.createElement('div');
    sep.className = 'review-menu-sep';
    menu.appendChild(sep);
    var userItem = document.createElement('div');
    userItem.className = 'review-menu-item review-menu-user';
    var u = getUser();
    userItem.textContent = u ? 'Change user (' + u + ')' : 'Set user name…';
    userItem.addEventListener('mousedown', function(e) { e.stopPropagation(); });
    userItem.addEventListener('click', function(e) {
      e.stopPropagation();
      hideMenu();
      promptUser(true);
    });
    menu.appendChild(userItem);

    menu.style.display = 'block';
    var mw = menu.offsetWidth, mh = menu.offsetHeight;
    var vw = window.innerWidth,  vh = window.innerHeight;
    menu.style.left = (x + mw > vw - 8 ? vw - mw - 8 : x) + 'px';
    menu.style.top  = (y + mh > vh - 8 ? vh - mh - 8 : y) + 'px';
  }

  function hideMenu() { menu.style.display = 'none'; }
  document.addEventListener('click', hideMenu);
  document.addEventListener('contextmenu', function(e) {
    // hide menu if click is outside an artifact div
    if (!e.target.closest('[artifact-type]')) hideMenu();
  });
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') hideMenu();
  });

  // ── User name ─────────────────────────────────────────────────────────────
  function promptUser(force) {
    var u = getUser();
    if (!force && u) return u;
    var name = window.prompt('Enter your user name (login):', u || '');
    if (name === null) return u;
    name = name.trim();
    if (name) setUser(name);
    return name || u;
  }

  // ── Add a review ──────────────────────────────────────────────────────────
  function addReview(artifactId, context) {
    var user = promptUser(false);
    if (!user) {
      window.alert('Please set your user name first (right-click → Set user name).');
      return;
    }
    var text = window.prompt('[' + context + '] ' + artifactId, '');
    if (text === null) return;
    text = text.trim();
    if (!text) return;

    var now = new Date();
    var pad = function(n) { return String(n).padStart(2, '0'); };
    var dateStr = now.getFullYear() + '-' + pad(now.getMonth()+1) + '-' + pad(now.getDate())
                + ' ' + pad(now.getHours()) + ':' + pad(now.getMinutes());

    var reviews = loadReviews();
    reviews.push({ user: user, artifact: artifactId, context: context, text: text, date: dateStr });
    saveReviews(reviews);
    renderReviews(artifactId);
  }

  // ── Attach right-click listeners ──────────────────────────────────────────
  function attachContextMenus() {
    document.querySelectorAll('[artifact-type][artifact]').forEach(function(div) {
      if (!div.getAttribute('artifact-type')) return;
      var aid = div.getAttribute('artifact');
      if (!aid) return;
      div.addEventListener('contextmenu', function(e) {
        e.preventDefault();
        e.stopPropagation();
        showMenu(e.clientX, e.clientY, aid);
      });
    });
  }

  // ── Bootstrap ─────────────────────────────────────────────────────────────
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() {
      initReviewBlocks();
      attachContextMenus();
    });
  } else {
    initReviewBlocks();
    attachContextMenus();
  }
})();
</script>
"""
        if '</body>' in html_content:
            html_content = html_content.replace('</body>', css_js + '\n</body>', 1)
        else:
            html_content += css_js

        if self.verbose:
            print("  📝 Review annotation system injected")
        return html_content

    def _inject_hovering(self, html_content: str) -> str:
        """Injects CSS + JS for artifact hover tooltips.

        On mouseenter over any <a href="#Doc.Type.Object">, a floating panel
        shows the full content of the target <div id="Doc.Type.Object">.
        The panel is capped at 20vh; if clipped, a '▼ truncated' indicator
        is shown at the bottom.
        """
        css_js = """
<style id="artifact-hover-style">
#artifact-hover-tooltip {
  display: none;
  position: fixed;
  max-width: 520px;
  max-height: 30vh;
  overflow: hidden;
  background: #fffde7;
  border: 1px solid #bbb;
  border-radius: 4px;
  padding: 8px 10px;
  z-index: 9999;
  font-size: 0.85em;
  line-height: 1.4;
  box-shadow: 3px 3px 8px rgba(0,0,0,0.25);
  pointer-events: none;
}
#artifact-hover-tooltip.clipped::after {
  content: "▼ truncated";
  display: block;
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  text-align: center;
  background: linear-gradient(transparent, #fffde7 60%);
  color: #888;
  font-size: 0.8em;
  padding-top: 12px;
}
</style>
<script id="artifact-hover-script">
(function() {
  var tip = document.createElement('div');
  tip.id = 'artifact-hover-tooltip';
  document.body.appendChild(tip);

  document.querySelectorAll('a[href^="#"]').forEach(function(link) {
    var href = link.getAttribute('href');
    if (!/^#[A-Za-z]+\\.[A-Za-z]+\\./.test(href)) return;
    var id = href.slice(1);
    var target = document.getElementById(id);
    if (!target) return;

    link.addEventListener('mouseenter', function(e) {
      tip.innerHTML = target.innerHTML;
      tip.style.display = 'block';
      // check if content overflows
      tip.classList.toggle('clipped', tip.scrollHeight > tip.clientHeight + 2);
      positionTip(e);
    });
    link.addEventListener('mousemove', positionTip);
    link.addEventListener('mouseleave', function() {
      tip.style.display = 'none';
    });
  });

  function positionTip(e) {
    var x = e.clientX + 14;
    var y = e.clientY + 14;
    // keep tooltip within viewport
    var vw = window.innerWidth, vh = window.innerHeight;
    var tw = tip.offsetWidth, th = tip.offsetHeight;
    if (x + tw > vw - 8) x = e.clientX - tw - 14;
    if (y + th > vh - 8) y = e.clientY - th - 14;
    tip.style.left = x + 'px';
    tip.style.top  = y + 'px';
  }
})();
</script>
"""
        # Inject just before </body>
        if '</body>' in html_content:
            html_content = html_content.replace('</body>', css_js + '\n</body>', 1)
        else:
            html_content += css_js

        if self.verbose:
            print("  🖱️  Hover tooltips injected")
        return html_content

    def clean(self) -> bool:
        """Runs the full cleaning pipeline"""
        try:
            if self.verbose:
                print(f"📖 Reading: {self.input_file}")
                print(f"🔌 Port: {self.port}")
                print(f"📄 Main page: {self.main_page}")
                if self.remove_buttons:
                    print(f"🗑️  Buttons: YES")
                if self.remove_sidenav:
                    print(f"🗑️  Sidenav: YES")
                print()

            with open(self.input_file, 'r', encoding='utf-8') as f:
                full_content = f.read()

            html_section, _, _ = self._extract_html_section(full_content)

            if self.verbose:
                print("🧹 Cleaning...")

            html_decoded = self._decode_quoted_printable_section(html_section)
            html_decoded = self._clean_malformed_tags(html_decoded)

            html_cleaned = self._process_html_attributes(html_decoded)
            html_cleaned = self._process_form_actions(html_cleaned)

            html_cleaned = self._extract_and_inject_css(full_content, html_cleaned)
            html_cleaned = self._extract_and_inject_images(full_content, html_cleaned)
            html_cleaned = self._replace_remaining_localhost_links(html_cleaned)
            artifact_db = self._build_artifact_database(html_cleaned)
            if self.database_file:
                self._export_database_csv(artifact_db)
            html_cleaned = self._add_artifact_tooltips(html_cleaned, artifact_db)
            html_cleaned = self._remove_fitnesse_buttons(html_cleaned)
            html_cleaned = self._remove_sidenav_div(html_cleaned)
            if self.include_hovering:
                html_cleaned = self._inject_hovering(html_cleaned)
            if self.include_review:
                html_cleaned = self._inject_review_system(html_cleaned)

            if self.verbose:
                print("  🔄 MHTML → HTML")

            # Remove cid: link tags (MHTML-specific, no longer valid in plain HTML)
            html_cleaned = re.sub(
                r'<link[^>]*href=["\']cid:[^"\']+["\'][^>]*>',
                '', html_cleaned, flags=re.IGNORECASE
            )

            with open(self.output_file, 'w', encoding='utf-8') as f:
                f.write(html_cleaned)

            if self.verbose:
                print(f"\n✅ Output: {self.output_file}")

            return True

        except Exception as e:
            print(f"❌ Error: {e}", file=sys.stderr)
            return False


def main():
    parser = argparse.ArgumentParser(description='MHTML Cleaner - Converts MHTML to HTML')

    parser.add_argument('input_file', help='Input MHTML file')
    parser.add_argument('-o', '--output', dest='output_file', default=None,
                        help='Output file (default: input name with .html extension)')
    parser.add_argument('-l', '--level', choices=['light', 'moderate', 'strict'], default='moderate')
    parser.add_argument('-p', '--preserve-fitnesse', action='store_true')
    parser.add_argument('-b', '--remove-buttons', action='store_true', help='Remove editing buttons')
    parser.add_argument('-s', '--remove-sidenav', action='store_true', help='Remove sidenav panel')
    parser.add_argument('-A', '--all', action='store_true', help='Preset: enable -b, -s, -v, -V, -H')
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('-H', '--include-hovering', action='store_true',
                        help='Inject JS hover tooltips showing artifact definitions')
    parser.add_argument('-R', '--include-review', action='store_true',
                        help='Inject review annotation system (right-click on artifacts)')
    parser.add_argument('--version', action='version', version=f'mhtml-cleaner {__version__}')
    parser.add_argument('-V', '--validate', action='store_true',
                        help='Run HTML validator on output file after cleaning')
    parser.add_argument('--database-file', default=None,
                        help='Export artifact database to a CSV file')

    args = parser.parse_args()

    if not Path(args.input_file).exists():
        print(f"❌ File not found: {args.input_file}", file=sys.stderr)
        sys.exit(1)

    if args.all:
        args.remove_buttons = True
        args.remove_sidenav = True
        args.verbose = True
        args.include_hovering= True
        args.validate = True
        
    if args.output_file is None:
        args.output_file = str(Path(args.input_file).with_suffix('.html'))

    cleaner = MHTMLCleaner(
        input_file=args.input_file,
        output_file=args.output_file,
        level=args.level,
        preserve_fitnesse=args.preserve_fitnesse,
        verbose=args.verbose,
        remove_buttons=args.remove_buttons,
        remove_sidenav=args.remove_sidenav,
        include_hovering=args.include_hovering,
        include_review=args.include_review,
        database_file=(
            str(Path(args.database_file).with_suffix('.csv'))
            if args.database_file and not args.database_file.endswith('.csv')
            else args.database_file
        )
    )

    success = cleaner.clean()

    if success and args.validate:
        if HTMLValidator is None:
            print("⚠️  test-html-validator.py not found — skipping validation", file=sys.stderr)
        else:
            validator = HTMLValidator(args.output_file, verbose=True)
            success = validator.validate()

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
