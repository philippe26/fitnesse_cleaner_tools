#!/usr/bin/env python3
"""
MHTML Cleaner - Converts MHTML files to standalone HTML
"""

__version__ = '2.7.1'

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
                 include_review: bool = False,
                 remove_traceability: bool = False):
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
        self.remove_traceability = remove_traceability

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

    # ------------------------------------------------------------------ traceability

    def _find_closing_tag(self, html: str, start: int, tag: str) -> int:
        """Return the index just after the </tag> that matches the opening <tag> at `start`.

        Counts nested open/close pairs so embedded tags of the same type are
        handled correctly (e.g. <ul> inside a <li> inside the outer <ul>).
        Returns -1 if no matching closing tag is found.
        """
        depth = 0
        pattern = re.compile(
            rf'<(/?)({re.escape(tag)})\b[^>]*>',
            re.IGNORECASE
        )
        for m in pattern.finditer(html, start):
            if m.group(1):   # closing tag  </tag>
                depth -= 1
                if depth == 0:
                    return m.end()
            else:            # opening tag  <tag ...>
                depth += 1
        return -1

    def _transform_traceability_navpills(self, html_content: str) -> str:
        """Finds <ul class="nav nav-pills"> traceability blocks and either:
          - removes them completely (--remove-traceability)
          - replaces them with clean static HTML using <details>/<summary> dropdowns

        The enclosing <div> is also consumed so no empty container is left.
        """
        CSS = """<style id="traceability-style">
/* Isolation: reset Bootstrap interference on our elements */
.trace-nav, .trace-nav * { box-sizing: border-box; }
.trace-nav {
  display: flex !important; flex-wrap: wrap; align-items: center; gap: 6px;
  margin: 4px 0 8px; padding: 0 !important;
  font-family: sans-serif !important; font-size: .82em;
  list-style: none !important; border: none !important;
  background: transparent !important;
}
.trace-title {
  font-weight: bold; color: #37474f; padding: 3px 10px;
  background: #eceff1 !important; border-radius: 3px;
  white-space: nowrap; border: none !important;
}
/* details element acting as dropdown */
.trace-dd {
  position: relative !important; display: inline-block !important;
  margin: 0 !important; padding: 0 !important;
  border: none !important; background: transparent !important;
}
.trace-dd > summary {
  display: inline-block !important; list-style: none !important;
  padding: 3px 10px !important; margin: 0 !important;
  background: #fff !important; border: 1px solid #b0bec5 !important;
  border-radius: 3px !important; cursor: pointer !important;
  color: #455a64 !important; white-space: nowrap !important;
  user-select: none; font-size: 1em !important;
  font-family: sans-serif !important; font-weight: normal !important;
  text-decoration: none !important;
}
.trace-dd > summary::-webkit-details-marker { display: none !important; }
.trace-dd > summary::marker { display: none !important; }
.trace-dd > summary::after { content: " \u25be"; color: #90a4ae !important; }
.trace-dd[open] > summary { background: #e3f2fd !important; border-color: #90caf9 !important; }
.trace-dd[open] > summary::after { content: " \u25b4"; }
/* badge inside summary */
.trace-badge {
  display: inline-block !important;
  background: #78909c !important; color: #fff !important;
  border-radius: 8px !important; padding: 0 5px !important;
  font-size: .76em !important; margin-left: 4px !important;
  min-width: 0 !important; font-weight: bold !important;
  vertical-align: middle !important; line-height: 1.5 !important;
}
.trace-badge.zero { background: #cfd8dc !important; color: #607d8b !important; }
/* dropdown list */
.trace-list {
  position: absolute !important; top: calc(100% + 2px) !important;
  left: 0 !important; z-index: 5000 !important;
  background: #fff !important; border: 1px solid #b0bec5 !important;
  border-radius: 3px !important;
  box-shadow: 2px 4px 10px rgba(0,0,0,.18) !important;
  padding: 4px 0 !important; list-style: none !important;
  min-width: 220px !important; margin: 0 !important;
  max-height: 50vh; overflow-y: auto;
}
.trace-list li {
  display: block !important; padding: 5px 14px !important;
  color: #37474f !important; white-space: nowrap !important;
  font-size: .9em !important; font-family: sans-serif !important;
  background: transparent !important; border: none !important;
  float: none !important; margin: 0 !important;
}
.trace-list li:hover { background: #f5f5f5 !important; }
.trace-none { color: #90a4ae !important; font-style: italic !important; }
</style>
<script id="traceability-close-script">
(function() {
  document.addEventListener('click', function(e) {
    if (!e.target.closest('.trace-dd')) {
      document.querySelectorAll('.trace-dd[open]').forEach(function(d) { d.open = false; });
    }
  });
})();
</script>
"""
        ul_re = re.compile(
            r'<ul\b[^>]*class=["\'][^"\']*\bnav\b[^"\']*\bpills\b[^"\']*["\'][^>]*>',
            re.IGNORECASE
        )
        css_done = False
        out = html_content
        pos = 0

        while True:
            m = ul_re.search(out, pos)
            if not m:
                break

            ul_start = m.start()
            ul_end = self._find_closing_tag(out, ul_start, 'ul')
            if ul_end == -1:
                pos = m.end()
                continue

            ul_html = out[ul_start:ul_end]

            # Find the wrapping <div> immediately before this <ul> (only whitespace between)
            pre = out[max(0, ul_start - 300):ul_start]
            div_matches = list(re.finditer(r'<div\b[^>]*>', pre, re.IGNORECASE))
            repl_start, repl_end = ul_start, ul_end
            if div_matches:
                last = div_matches[-1]
                if re.match(r'^\s*$', pre[last.end():]):
                    abs_div = max(0, ul_start - 300) + last.start()
                    div_end = self._find_closing_tag(out, abs_div, 'div')
                    if div_end != -1:
                        repl_start, repl_end = abs_div, div_end

            if self.remove_traceability:
                out = out[:repl_start] + out[repl_end:]
                pos = repl_start
            else:
                repl = self._build_traceability_block(ul_html)
                if repl and not css_done:
                    repl = CSS + repl
                    css_done = True
                out = out[:repl_start] + repl + out[repl_end:]
                pos = repl_start + len(repl)

        if self.verbose:
            action = 'removed' if self.remove_traceability else 'transformed'
            print(f"  🔗 Traceability nav-pills {action}")
        return out

    def _build_traceability_block(self, ul_html: str) -> str:
        """Parses a nav-pills <ul> block and returns clean static HTML."""

        # Title from <li class="active">
        title_m = re.search(
            r'<li\b[^>]*\bactive\b[^>]*>.*?<a\b[^>]*>(.*?)</a>',
            ul_html, re.DOTALL | re.IGNORECASE
        )
        title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip() if title_m else ''

        # Each <li class="dropdown"> — use _find_closing_tag for correct nesting
        dropdowns = []
        li_re = re.compile(r'<li\b[^>]*\bdropdown\b[^>]*>', re.IGNORECASE)
        li_pos = 0
        while True:
            lm = li_re.search(ul_html, li_pos)
            if not lm:
                break
            li_end = self._find_closing_tag(ul_html, lm.start(), 'li')
            if li_end == -1:
                li_pos = lm.end()
                continue
            inner = ul_html[lm.end():li_end]

            # Button label + badge from dropdown-toggle <a>
            toggle_m = re.search(
                r'<a\b[^>]*\bdropdown-toggle\b[^>]*>(.*?)</a>',
                inner, re.DOTALL | re.IGNORECASE
            )
            label, badge = '', ''
            if toggle_m:
                toggle_html = toggle_m.group(1)
                bm = re.search(r'<span\b[^>]*\bbadge\b[^>]*>(\d+)</span>',
                               toggle_html, re.IGNORECASE)
                badge = bm.group(1) if bm else ''
                # Remove all <span>...</span> before stripping tags so that
                # the badge number and caret text don't appear in the label
                toggle_no_spans = re.sub(r'<span\b[^>]*>.*?</span>', '',
                                         toggle_html, flags=re.DOTALL | re.IGNORECASE)
                label = re.sub(r'<[^>]+>', '', toggle_no_spans).strip()

            # Items from <ul class="dropdown-menu"> — skip dividers and edit links
            items = []
            menu_m = re.search(
                r'<ul\b[^>]*\bdropdown-menu\b[^>]*>(.*?)</ul>',
                inner, re.DOTALL | re.IGNORECASE
            )
            if menu_m:
                for item_m in re.finditer(
                    r'<li(\b[^>]*)>(.*?)</li\s*>',
                    menu_m.group(1), re.DOTALL | re.IGNORECASE
                ):
                    if 'divider' in item_m.group(1):
                        continue
                    if re.search(r'<a\b[^>]*\bedit\b', item_m.group(2), re.IGNORECASE):
                        continue
                    text = re.sub(r'<[^>]+>', '', item_m.group(2)).strip()
                    if text:
                        items.append(text)

            dropdowns.append((label, badge, items))
            li_pos = li_end

        if not title and not dropdowns:
            return ''

        parts = ['<div class="trace-nav">']
        if title:
            parts.append(f'<span class="trace-title">{title}</span>')
        for label, badge, items in dropdowns:
            zero = badge == '0'
            badge_cls = 'trace-badge zero' if zero else 'trace-badge'
            badge_html = f' <span class="{badge_cls}">{badge}</span>' if badge else ''
            if items:
                lis = ''.join(f'<li>{i}</li>' for i in items)
            else:
                lis = '<li class="trace-none">(none)</li>'
            parts.append(
                f'<details class="trace-dd">'
                f'<summary>{label}{badge_html}</summary>'
                f'<ul class="trace-list">{lis}</ul>'
                f'</details>'
            )
        parts.append('</div>')
        return '\n'.join(parts)

    def _inject_review_system(self, html_content: str) -> str:
        """Injects CSS + JS for a right-click review annotation system.

        A prominent "CONNECT JSON REVIEW FILE" banner is placed at the very top.
        The context menu is greyed out until a file is connected.

        Persistence strategy (two layers):
          - localStorage: fast cache, loaded on every boot for instant display
          - JSON file on disk (File System Access API): source of truth, written
            on every add; read on connect (overrides localStorage cache)

        File handle stored in IndexedDB for auto-reconnect across sessions.
        Default filename: <html-basename>_review.json
        User name: auto-detected from OS path (/home/user or /Users/user).

        Visual: bent-arrow connector + framed block with vertical REVIEW sidebar.
        """
        # Banner injected right after <body> opening tag (plain string, not raw)
        connect_bar = (
            '<div id="rv-bar">'
            '<button id="rv-btn" onclick="window._rvConnect()">'
            '&#128194; CONNECT JSON REVIEW FILE'
            '</button>'
            '<span id="rv-label"></span>'
            '</div>\n'
        )

        css_js = r"""
<style id="review-system-style">
/* ── Connect banner ───────────────────────────────── */
#rv-bar {
  position: sticky; top: 0; z-index: 10003;
  display: flex; align-items: center; gap: 12px;
  padding: 5px 14px;
  background: #cfd8dc; border-bottom: 1px solid #90a4ae;
  box-shadow: 0 1px 4px rgba(0,0,0,.15);
  font-family: sans-serif;
}
#rv-btn {
  padding: 4px 16px; font-size: .88em; font-weight: bold;
  background: #c62828; color: #fff;
  border: 1px solid #b71c1c; border-radius: 4px;
  cursor: pointer; letter-spacing: .4px; transition: background .15s;
  white-space: nowrap;
}
#rv-btn:hover { background: #b71c1c; }
#rv-btn.connected { background: #2e7d32; border-color: #1b5e20; }
#rv-btn.connected:hover { background: #1b5e20; }
#rv-label { color: #455a64; font-size: .82em; }

/* ── File-picker dialog ───────────────────────────── */
#rv-picker-overlay {
  position: fixed; inset: 0; z-index: 10010;
  background: rgba(0,0,0,.4);
  display: flex; align-items: center; justify-content: center;
}
#rv-picker-box {
  background: #fff; border-radius: 8px; padding: 24px 28px;
  box-shadow: 0 8px 32px rgba(0,0,0,.3); min-width: 320px;
  font-family: sans-serif;
}
#rv-picker-box h3 {
  margin: 0 0 6px; font-size: 1em; color: #263238;
}
#rv-picker-box p {
  margin: 0 0 18px; font-size: .83em; color: #607d8b; line-height: 1.4;
}
.rv-picker-btn {
  display: block; width: 100%; margin: 0 0 10px;
  padding: 9px 14px; font-size: .9em; font-weight: bold;
  border: 1px solid #b0bec5; border-radius: 5px;
  background: #eceff1; color: #263238; cursor: pointer;
  text-align: left; transition: background .12s;
}
.rv-picker-btn:hover { background: #cfd8dc; }
.rv-picker-cancel {
  display: block; width: 100%; padding: 6px;
  font-size: .8em; color: #90a4ae; background: none;
  border: none; cursor: pointer; text-align: center; margin-top: 4px;
}
.rv-picker-cancel:hover { color: #546e7a; }

/* ── Context menu ─────────────────────────────────── */
#review-context-menu {
  position: fixed; z-index: 10002;
  background: #fff; border: 1px solid #ccc;
  border-radius: 4px; box-shadow: 2px 4px 10px rgba(0,0,0,.22);
  min-width: 185px; padding: 4px 0;
  font-size: .88em; font-family: sans-serif;
}
.review-menu-item { padding: 7px 16px; cursor: pointer; white-space: nowrap; }
.review-menu-item:hover:not(.review-menu-disabled) { background: #e8f0fe; }
.review-menu-disabled { color: #bdbdbd; cursor: not-allowed; }
.review-menu-warn { color: #e65100; font-size: .85em; }
.review-menu-sep  { border-top: 1px solid #e0e0e0; margin: 4px 0; }
.review-menu-user { color: #78909c; font-style: italic; font-size: .85em; }

/* ── Review container: L connector + frame ─────────── */
.review-container {
  display: flex; align-items: flex-start;
  margin: 0 0 10px 28px; position: relative;
}
/* L shape: vertical segment down then turns right — no arrowhead */
.review-container::before {
  content: ''; position: absolute;
  left: -20px; top: -6px;
  width: 14px; height: calc(50% + 6px);
  border-left: 3px solid #78909c;
  border-bottom: 3px solid #78909c;
  border-bottom-left-radius: 3px;
}
/* Framed box */
.review-frame {
  display: flex; border: 1px solid #b0bec5; border-radius: 4px;
  overflow: hidden; width: 100%; background: #f9fafb;
  box-shadow: 1px 1px 4px rgba(0,0,0,.07);
}
/* Vertical "REVIEW" banner */
.review-sidebar {
  writing-mode: vertical-lr; transform: rotate(180deg);
  background: #455a64; color: #fff;
  font-size: .62em; font-weight: bold; letter-spacing: 3px;
  text-align: center; padding: 10px 4px;
  font-family: sans-serif; user-select: none; flex-shrink: 0;
}
.review-entries { padding: 4px 8px; flex: 1; min-width: 0; }

/* ── Individual review rows ───────────────────────── */
.review-entry {
  display: flex; align-items: baseline; gap: 6px;
  padding: 3px 0; font-size: .83em; font-family: sans-serif;
  border-bottom: 1px solid #eceff1;
}
.review-entry:last-child { border-bottom: none; }
.review-badge {
  font-weight: bold; font-size: .7em; text-transform: uppercase;
  padding: 1px 5px; border-radius: 3px; color: #fff;
  white-space: nowrap; flex-shrink: 0;
}
.review-operational .review-badge { background: #6a1b9a; }
.review-significant .review-badge { background: #ad1457; }
.review-major       .review-badge { background: #c62828; }
.review-minor       .review-badge { background: #ef6c00; }
.review-typo        .review-badge { background: #558b2f; }
.review-comment     .review-badge { background: #1565c0; }
.review-meta { color: #90a4ae; font-size: .82em; white-space: nowrap; flex-shrink: 0; }
.review-text { color: #37474f; }
</style>
<script id="review-system-script">
(function() {
  'use strict';

  /* ── Config ─────────────────────────────────────────────────────── */
  var _base = decodeURIComponent(location.pathname).split('/').pop()
                .replace(/\.html?$/i, '');
  var SUGGESTED = _base + '_review.json';
  var IDB_KEY   = 'rv:' + _base;
  var LS_KEY    = 'rv-data:' + _base;
  var USER_KEY  = 'rv-user';

  /* ── State ──────────────────────────────────────────────────────── */
  var _handle    = null;   // FileSystemFileHandle
  var _reviews   = [];     // [{user, artifact, context, text, date}]
  var _connected = false;

  /* ── OS user detection ──────────────────────────────────────────── */
  function _guessUser() {
    var p = decodeURIComponent(location.pathname);
    var m = p.match(/\/home\/([^\/]+)\//);
    if (m) return m[1];
    m = p.match(/\/Users\/([^\/]+)\//i);
    if (m) return m[1];
    return '';
  }
  function getUser() {
    var u = localStorage.getItem(USER_KEY) || '';
    if (!u) { u = _guessUser(); if (u) localStorage.setItem(USER_KEY, u); }
    return u;
  }
  function setUser(u) { if (u) localStorage.setItem(USER_KEY, u); }

  /* ── localStorage cache ─────────────────────────────────────────── */
  function _lsLoad() {
    try { return JSON.parse(localStorage.getItem(LS_KEY) || '[]'); } catch(e) { return []; }
  }
  function _lsSave() { localStorage.setItem(LS_KEY, JSON.stringify(_reviews)); }

  /* ── IndexedDB — persists file handle across sessions ───────────── */
  var _db = null;
  function _idbOpen(cb) {
    if (_db) return cb(_db);
    var r = indexedDB.open('mhtml-rv-db', 1);
    r.onupgradeneeded = function(e) { e.target.result.createObjectStore('h'); };
    r.onsuccess = function(e) { _db = e.target.result; cb(_db); };
    r.onerror   = function()  { cb(null); };
  }
  function _idbGet(cb) {
    _idbOpen(function(db) {
      if (!db) return cb(null);
      var r = db.transaction('h', 'readonly').objectStore('h').get(IDB_KEY);
      r.onsuccess = function(e) { cb(e.target.result || null); };
      r.onerror   = function()  { cb(null); };
    });
  }
  function _idbPut(h) {
    _idbOpen(function(db) {
      if (!db) return;
      try { db.transaction('h', 'readwrite').objectStore('h').put(h, IDB_KEY); } catch(e) {}
    });
  }

  /* ── File I/O ───────────────────────────────────────────────────── */
  async function _fileSave() {
    if (!_handle) return;
    try {
      var w = await _handle.createWritable();
      await w.write(JSON.stringify(_reviews, null, 2));
      await w.close();
    } catch(e) { console.warn('Review save failed:', e); }
  }

  async function _fileConnect(h) {
    try {
      var perm = await h.queryPermission({mode: 'readwrite'});
      if (perm !== 'granted') perm = await h.requestPermission({mode: 'readwrite'});
      if (perm !== 'granted') return false;
      var f = await h.getFile();
      if (f.size > 0) {
        // File already exists — load its content (source of truth), update LS cache
        _reviews = JSON.parse(await f.text());
        _lsSave();
      } else {
        // New empty file — initialise it from localStorage content
        _reviews = _lsLoad();
        await (async function() {
          var w = await h.createWritable();
          await w.write(JSON.stringify(_reviews, null, 2));
          await w.close();
        })();
      }
      _handle = h; _idbPut(h); return true;
    } catch(e) { return false; }
  }

  /* ── Connect button ─────────────────────────────────────────────── */
  function _setConnected(yes, fname) {
    _connected = yes;
    var btn = document.getElementById('rv-btn');
    var lbl = document.getElementById('rv-label');
    if (!btn) return;
    if (yes) {
      btn.textContent = '\u{1F4BE} CONNECTED: ' + (fname || 'review file');
      btn.classList.add('connected');
      if (lbl) { lbl.textContent = getUser() + ' \u2014 right-click any artifact to add a review'; }
    } else {
      btn.textContent = '\u{1F4C2} CONNECT JSON REVIEW FILE';
      btn.classList.remove('connected');
      if (lbl) { lbl.textContent = 'Reviews disabled \u2014 connect a file to enable editing'; }
    }
  }

  /* ── File-picker mini-dialog ────────────────────────────────────── */
  function _showPickerDialog() {
    return new Promise(function(resolve) {
      var overlay = document.createElement('div');
      overlay.id = 'rv-picker-overlay';
      overlay.innerHTML =
        '<div id="rv-picker-box">' +
          '<h3>\uD83D\uDCC2 Review file</h3>' +
          '<p>Choose whether to open an existing review file<br>or create a new one.</p>' +
          '<button class="rv-picker-btn" id="rv-pick-open">' +
            '\uD83D\uDCC2\u00a0Open existing file\u2026' +
          '</button>' +
          '<button class="rv-picker-btn" id="rv-pick-new">' +
            '\uD83C\uDD95\u00a0Create new file \u2014 ' + SUGGESTED +
          '</button>' +
          '<button class="rv-picker-cancel" id="rv-pick-cancel">Cancel</button>' +
        '</div>';
      document.body.appendChild(overlay);
      function done(choice) { overlay.remove(); resolve(choice); }
      document.getElementById('rv-pick-open').onclick   = function() { done('open'); };
      document.getElementById('rv-pick-new').onclick    = function() { done('new'); };
      document.getElementById('rv-pick-cancel').onclick = function() { done(null); };
      overlay.addEventListener('click', function(e) { if (e.target === overlay) done(null); });
    });
  }

  window._rvConnect = async function() {
    if (!window.showSaveFilePicker || !window.showOpenFilePicker) {
      alert('File System Access API not available.\nUse Chrome or Edge (v86+) for file persistence.');
      return;
    }
    var choice = await _showPickerDialog();
    if (!choice) return;
    var h = null;
    try {
      if (choice === 'open') {
        var picks = await window.showOpenFilePicker({
          types: [{ description: 'Review JSON', accept: {'application/json': ['.json']} }],
          multiple: false
        });
        h = picks[0];
      } else {
        h = await window.showSaveFilePicker({
          suggestedName: SUGGESTED,
          types: [{ description: 'Review JSON', accept: {'application/json': ['.json']} }]
        });
      }
    } catch(e) { return; /* user cancelled picker */ }
    var ok = await _fileConnect(h);
    if (ok) { _setConnected(true, h.name); _renderAll(); }
  };

  /* ── Render ─────────────────────────────────────────────────────── */
  function _render(aid) {
    var wrap = document.getElementById('rv-' + aid);
    if (!wrap) return;
    var mine = _reviews.filter(function(r) { return r.artifact === aid; });
    if (!mine.length) { wrap.style.display = 'none'; return; }
    wrap.style.display = 'flex';
    var en = wrap.querySelector('.review-entries');
    en.innerHTML = '';
    mine.forEach(function(r) {
      var row = document.createElement('div');
      row.className = 'review-entry review-' + r.context.toLowerCase();
      var bd = document.createElement('span'); bd.className = 'review-badge'; bd.textContent = r.context;
      var mt = document.createElement('span'); mt.className = 'review-meta';
      mt.textContent = r.user + ' \u2014 ' + r.date;
      var tx = document.createElement('span'); tx.className = 'review-text'; tx.textContent = r.text;
      row.appendChild(bd); row.appendChild(mt); row.appendChild(tx);
      en.appendChild(row);
    });
  }
  function _renderAll() {
    document.querySelectorAll('[artifact-type][artifact]').forEach(function(d) {
      var a = d.getAttribute('artifact'); if (a) _render(a);
    });
  }

  /* ── Review blocks (created once on boot) ───────────────────────── */
  function _initBlocks() {
    document.querySelectorAll('[artifact-type][artifact]').forEach(function(div) {
      if (!div.getAttribute('artifact-type')) return;
      var aid = div.getAttribute('artifact'); if (!aid) return;
      var wrap = document.createElement('div');
      wrap.id = 'rv-' + aid;
      wrap.className = 'review-container';
      wrap.style.display = 'none';
      var frame = document.createElement('div'); frame.className = 'review-frame';
      frame.innerHTML =
        '<div class="review-sidebar">REVIEW</div>' +
        '<div class="review-entries"></div>';
      wrap.appendChild(frame);
      div.parentNode.insertBefore(wrap, div.nextSibling);
    });
  }

  /* ── Context menu ───────────────────────────────────────────────── */
  var _menu = null;
  function _mkMenu() {
    _menu = document.createElement('div');
    _menu.id = 'review-context-menu';
    _menu.style.display = 'none';
    document.body.appendChild(_menu);
    document.addEventListener('click', function(e) {
      if (_menu && !_menu.contains(e.target)) _menu.style.display = 'none';
    });
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape' && _menu) _menu.style.display = 'none';
    });
  }

  function _showMenu(x, y, aid) {
    _menu.innerHTML = '';
    [['🟣','Operational'],['🔶','Significant'],['🔴','Major'],['🟠','Minor'],['🟢','Typo'],['🔵','Comment']].forEach(function(p) {
      var it = document.createElement('div');
      if (_connected) {
        it.className = 'review-menu-item';
        it.addEventListener('click', function(e) {
          e.stopPropagation(); _menu.style.display = 'none'; _add(aid, p[1]);
        });
      } else {
        it.className = 'review-menu-item review-menu-disabled';
      }
      it.textContent = p[0] + '\u00a0Add ' + p[1];
      _menu.appendChild(it);
    });

    var sep = document.createElement('div'); sep.className = 'review-menu-sep';
    _menu.appendChild(sep);

    if (!_connected) {
      var warn = document.createElement('div');
      warn.className = 'review-menu-item review-menu-warn';
      warn.textContent = '\u26a0\ufe0f\u00a0Connect a file first\u2026';
      warn.addEventListener('click', function(e) {
        e.stopPropagation(); _menu.style.display = 'none'; window._rvConnect();
      });
      _menu.appendChild(warn);
      var sep2 = document.createElement('div'); sep2.className = 'review-menu-sep';
      _menu.appendChild(sep2);
    }

    var ui = document.createElement('div');
    ui.className = 'review-menu-item review-menu-user';
    var u = getUser();
    ui.textContent = u ? '\u{1f464}\u00a0' + u + ' (change\u2026)' : '\u{1f464}\u00a0Set user name\u2026';
    ui.addEventListener('click', function(e) {
      e.stopPropagation(); _menu.style.display = 'none';
      var n = window.prompt('User name:', u || '');
      if (n !== null && n.trim()) { setUser(n.trim()); _setConnected(_connected, _handle && _handle.name); }
    });
    _menu.appendChild(ui);

    _menu.style.display = 'block';
    var mw = _menu.offsetWidth, mh = _menu.offsetHeight;
    var vw = window.innerWidth, vh = window.innerHeight;
    _menu.style.left = (x + mw > vw - 8 ? vw - mw - 8 : x) + 'px';
    _menu.style.top  = (y + mh > vh - 8 ? vh - mh - 8 : y) + 'px';
  }

  /* ── Add review ─────────────────────────────────────────────────── */
  async function _add(aid, ctx) {
    var u = getUser();
    if (!u) {
      u = window.prompt('Enter your user name:', '');
      if (!u || !u.trim()) return;
      setUser(u = u.trim());
    }
    var txt = window.prompt('[' + ctx + '] ' + aid + ':', '');
    if (txt === null || !txt.trim()) return;
    var now = new Date();
    var pad = function(n) { return String(n).padStart(2, '0'); };
    var d = now.getFullYear() + '-' + pad(now.getMonth()+1) + '-' + pad(now.getDate())
          + ' ' + pad(now.getHours()) + ':' + pad(now.getMinutes());
    _reviews.push({ user: u, artifact: aid, context: ctx, text: txt.trim(), date: d });
    _lsSave();          // fast local cache
    await _fileSave();  // persist to disk
    _render(aid);
  }

  /* ── Attach context menus ───────────────────────────────────────── */
  function _attach() {
    document.querySelectorAll('[artifact-type][artifact]').forEach(function(div) {
      if (!div.getAttribute('artifact-type')) return;
      var aid = div.getAttribute('artifact'); if (!aid) return;
      div.addEventListener('contextmenu', function(e) {
        e.preventDefault(); e.stopPropagation();
        _showMenu(e.clientX, e.clientY, aid);
      });
    });
  }

  /* ── Bootstrap ──────────────────────────────────────────────────── */
  async function _boot() {
    _mkMenu(); _initBlocks(); _attach();
    // Fast path: show cached reviews immediately from localStorage
    _reviews = _lsLoad();
    if (_reviews.length) _renderAll();
    _setConnected(false);
    // Try auto-reconnect via stored IndexedDB handle
    _idbGet(async function(h) {
      if (!h) return;
      var ok = await _fileConnect(h);   // reads file, overwrites LS cache
      if (ok) { _setConnected(true, h.name); _renderAll(); }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _boot);
  } else {
    _boot();
  }
})();
</script>
"""
        # Inject connect banner right after <body> opening tag
        body_m = re.search(r'<body[^>]*>', html_content, re.IGNORECASE)
        if body_m:
            pos = body_m.end()
            html_content = html_content[:pos] + '\n' + connect_bar + html_content[pos:]
        else:
            html_content = connect_bar + html_content

        # Inject CSS + JS before </body>
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
            html_cleaned = self._transform_traceability_navpills(html_cleaned)
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
    parser.add_argument('-t', '--remove-traceability', action='store_true',
                        help='Remove traceability nav-pills blocks entirely')
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
        remove_traceability=args.remove_traceability,
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
