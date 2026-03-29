#!/usr/bin/env python3
"""
MHTML Cleaner v2.2.4 FINAL - Production Ready
✅ #1: Base64 sans sauts de ligne (et sans backslashes!)
✅ #2: URL CSS sans chemin relatif
✅ #3: Ancres numérotées conservées
✅ #4: Option --remove-sidenav
✅ #5: Détection dynamique du port
✅ #6: Suppression des boutons FitNesse CORRIGÉE
✅ #7: Décodage quoted-printable COMPLET avec quopri
"""

import re
import argparse
import sys
import quopri
from pathlib import Path
from typing import Tuple


class MHTMLCleaner:
    """Nettoyeur de fichiers MHTML"""
    
    FITNESSE_PATTERNS = [
        r'files/fitnesse/', r'files/bootstrap/', r'/FrontPage',
        r'/GaeL\.', r'/FitNesse\.', r'/RecentChanges',
    ]
    
    def __init__(self, input_file: str, output_file: str, level: str = 'moderate',
                 preserve_fitnesse: bool = False, preserve_css: bool = False,
                 verbose: bool = False,
                 remove_buttons: bool = False, remove_sidenav: bool = False):
        self.input_file = input_file
        self.output_file = output_file
        self.level = level
        self.preserve_fitnesse = preserve_fitnesse
        self.preserve_css = preserve_css
        self.verbose = verbose
        self.remove_buttons = remove_buttons
        self.remove_sidenav = remove_sidenav
        
        self.port = self._extract_port()
        self.main_page = self._extract_main_page_name()
    
    def _extract_port(self) -> int:
        """Détecte le port localhost utilisé dans le MHTML"""
        try:
            with open(self.input_file, 'r', encoding='utf-8', errors='ignore') as f:
                file_content = f.read(10000)
            
            match = re.search(r'http://localhost:(\d+)/', file_content)
            if match:
                port = int(match.group(1))
                if self.verbose:
                    print(f"  🔍 Port détecté: {port}")
                return port
        except:
            pass
        
        return 50020
    
    def _extract_main_page_name(self) -> str:
        """Extrait le nom de la page principale"""
        try:
            with open(self.input_file, 'r', encoding='utf-8', errors='ignore') as f:
                file_content = f.read(30000)
            
            # Méthode 1: Snapshot-Content-Location
            match = re.search(r'Snapshot-Content-Location:\s+.*\/([^\s\/]+)', file_content)
            if match:
                result = match.group(1).strip()
                if result and result != 'files':
                    return result
            
            # Méthode 2: URL localhost la plus courante (pas FitNesse)
            urls = re.findall(rf'http://localhost:{self.port}/([^/?&\s"\']+)', file_content)
            url_counts = {}
            for url in urls:
                if not any(x in url for x in ['files', 'FrontPage', 'RecentChanges', 'GaeL', 'FitNesse']):
                    url_counts[url] = url_counts.get(url, 0) + 1
            
            if url_counts:
                top_url = max(url_counts, key=url_counts.get)
                return top_url
            
            # Méthode 3: Titre HTML
            match = re.search(r'<title[^>]*>([^<]+)</title>', file_content, re.IGNORECASE)
            if match:
                title = match.group(1).split('.')[0].strip()
                if title:
                    return title
        except:
            pass
        
        return "Unknown"
    
    def _extract_html_section(self, content: str) -> Tuple[str, int, int]:
        """Extrait la section HTML principale"""
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
        """Détermine si un lien doit être supprimé"""
        if self.preserve_fitnesse:
            return False
        for pattern in self.FITNESSE_PATTERNS:
            if re.search(pattern, url, re.IGNORECASE):
                return True
        return False
    
    def _normalize_localhost_link(self, url: str) -> str:
        """Normalise les URLs localhost"""
        prefix = f'http://localhost:{self.port}/'
        if not url.startswith(prefix):
            return None
        
        path = url[len(prefix):]
        
        if self.main_page in path:
            match = re.search(rf'{self.main_page}([^/&]*)', path)
            if match:
                anchor = match.group(1)
                if anchor.startswith('?'):
                    anchor_num = anchor[1:]
                    return f"#{anchor_num}" if anchor_num else "#"
                elif anchor.startswith('#'):
                    return anchor
                else:
                    return '#'
            return '#'
        
        return None
    
    def _process_html_attributes(self, html_content: str) -> str:
        """Remplace href/src"""
        def replace_action(m):
            prefix = m.group(1)
            url = m.group(2)
            suffix = m.group(3)
            
            if self._should_remove_link(url):
                return ''
            
            normalized = self._normalize_localhost_link(url)
            if normalized:
                return f'{prefix}{normalized}{suffix}'
            
            return m.group(0)
        
        pattern = r'((?:href|src)\s*=\s*["\'])([^"\']*?)(["\'])'
        return re.sub(pattern, replace_action, html_content, flags=re.IGNORECASE)
    
    def _process_form_actions(self, html_content: str) -> str:
        """Remplace action=..."""
        def replace_action(m):
            action = m.group(1)
            if self._should_remove_link(action):
                return ''
            
            normalized = self._normalize_localhost_link(action)
            if normalized:
                return f' action="{normalized}"'
            return m.group(0)
        
        pattern = r' action=(["\'])([^"\']*?)\1'
        return re.sub(pattern, replace_action, html_content, flags=re.IGNORECASE)
    def _decode_quoted_printable_section(self, content: str) -> str:
        """✅ NOUVEAU: Décode quoted-printable COMPLETEMENT avec quopri"""
        try:
            # D'abord, enlever les sauts de ligne soft (=\n ou =\r\n)
            content = re.sub(r'=\r?\n', '', content)
            
            # Utiliser quopri pour décoder TOUS les =XX (pas juste une liste statique)
            # quopri travaille sur bytes, donc encoder puis décoder
            decoded = quopri.decodestring(content.encode()).decode('utf-8')
            return decoded
        except UnicodeDecodeError:
            # Si UTF-8 échoue, essayer latin-1
            try:
                content = re.sub(r'=\r?\n', '', content)
                decoded = quopri.decodestring(content.encode()).decode('latin-1')
                return decoded
            except:
                # Fallback: retourner le contenu non décodé
                if self.verbose:
                    print("  ⚠️  Erreur décodage quoted-printable")
                return content
            
    def _decode_quoted_printable_section_basic(self, content: str) -> str:
        """Décode quoted-printable"""
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
        """Extrait et injecte CSS"""
        css_sections = re.findall(
            rf'Content-Location: (http://localhost:{self.port}/files/fitnesse[^\n]+)\n\n(.+?)\n------',
            full_content, re.DOTALL
        )
        
        if not css_sections:
            if self.verbose:
                print("  ℹ️  Aucun CSS FitNesse à injecter")
            return html_content
        
        injected_css = []
        for location, css_body in css_sections:
            css_decoded = self._decode_quoted_printable_section(css_body)
            injected_css.append(css_decoded)
            
            if 'fitnesse_wiki' in location or 'fitnesse-bootstrap' in location:
                if self.verbose:
                    size_kb = len(css_decoded) // 1024
                    print(f"  ✅ CSS injecté: {location.split('/')[-1]} ({size_kb}KB)")
        
        combined_css = "\n\n".join(injected_css)
        style_tag = f'<style type="text/css">\n{combined_css}\n</style>'
        html_content = html_content.replace('</head>', f'{style_tag}\n</head>')
        
        if self.verbose:
            print(f"  📝 CSS injecté: {len(combined_css) // 1024}KB")
        
        return html_content
    
    def _extract_and_inject_images(self, full_content: str, html_content: str) -> str:
        """Extrait et injecte images en base64 (SANS échapper le contenu!)"""
        pattern = r'Content-Type: (image/\w+).*?\r?\nContent-Transfer-Encoding: base64\r?\nContent-Location: ([^\r\n]+)\r?\n\r?\n((?:[A-Za-z0-9+/=\r\n]+))'
        
        image_map = {}
        
        for match in re.finditer(pattern, full_content, re.MULTILINE | re.DOTALL):
            mime_type = match.group(1)
            location = match.group(2).strip()
            base64_data_raw = match.group(3)
            
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
                print(f"  🖼️  Image extraite: {filename} ({size_kb}KB)")
        
        if not image_map:
            if self.verbose:
                print("  ℹ️  Aucune image à injecter")
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
        
        html_content = re.sub(
            r'url\(\s*["\']([^"\']*?)data:image/',
            r'url("data:image/',
            html_content, flags=re.IGNORECASE
        )
        
        if self.verbose:
            print(f"  ✅ {len(image_map)} images injectées")
        
        return html_content
    
    def _replace_remaining_localhost_links(self, html_content: str) -> str:
        """Remplace URLs localhost restantes"""
        pattern = rf'((?:src|href)\s*=\s*["\'])([^"\']*?localhost:{self.port}[^"\']*?)(["\'])'
        
        def replacer(m):
            prefix = m.group(1)
            url = m.group(2)
            suffix = m.group(3)
            
            url_normalized = url.replace('&amp;', '&')
            
            if self._should_remove_link(url_normalized):
                return ''
            else:
                return f'{prefix}#{suffix}'
        
        return re.sub(pattern, replacer, html_content, flags=re.IGNORECASE)
    
    def _clean_malformed_tags(self, html_content: str) -> str:
        """Nettoie HTML"""
        html_content = re.sub(r'<head>\s*<head[^>]*>', '<head>', html_content, flags=re.IGNORECASE)
        if html_content.count('</head>') > 1:
            parts = html_content.split('</head>')
            html_content = '</head>'.join(parts[:-1]) + '</head>' + parts[-1]
        
        html_content = re.sub(r'<body>\s*<body[^>]*>', '<body>', html_content, flags=re.IGNORECASE)
        html_content = re.sub(r'</body>\s*</body>', '</body>', html_content, flags=re.IGNORECASE)
        
        return html_content
    
    def _remove_fitnesse_buttons(self, html_content: str) -> str:
        """✅ CORRIGÉ: Supprime boutons FitNesse - pattern simple <a>ButtonName</a>"""
        if not self.remove_buttons:
            return html_content
        
        buttons = ['Edit', 'Versions', 'Attributes', 'Review', 'Rationale', 'Expand', 'Collapse']
        
        for btn in buttons:
            # ✅ PATTERN CORRIGÉ: Chercher <a...>ButtonName</a> sans title attribute
            # Capture: <a[attributs optionnels]>[espaces]NomBouton[espaces]</a>
            pattern1 = rf'<a[^>]*?>\s*{re.escape(btn)}\s*</a>'
            html_content = re.sub(pattern1, '', html_content, flags=re.IGNORECASE)
            
            # Pattern 2: <button...>ButtonName</button>
            pattern2 = rf'<button[^>]*?>\s*{re.escape(btn)}\s*</button>'
            html_content = re.sub(pattern2, '', html_content, flags=re.IGNORECASE)
        
        if self.verbose:
            print(f"  🗑️  Boutons FitNesse supprimés")
        
        return html_content
    
    def _remove_sidenav_div(self, html_content: str) -> str:
        """Supprime <div class="sidenav">...</div>"""
        if not self.remove_sidenav:
            return html_content
        
        html_content = re.sub(
            r'<div[^>]*class=["\']?sidenav["\']?[^>]*>.*?</div>',
            '', html_content, flags=re.IGNORECASE | re.DOTALL
        )
        
        if self.verbose:
            print(f"  🗑️  Div sidenav supprimée")
        
        return html_content
    
    def clean(self) -> bool:
        """Nettoie le MHTML"""
        try:
            if self.verbose:
                print(f"📖 Lecture: {self.input_file}")
                print(f"🔌 Port: {self.port}")
                print(f"📄 Page: {self.main_page}")
                if self.remove_buttons:
                    print(f"🗑️  Boutons: OUI")
                if self.remove_sidenav:
                    print(f"🗑️  Sidenav: OUI")
                print()
            
            with open(self.input_file, 'r', encoding='utf-8') as f:
                full_content = f.read()
            
            html_section, _, _ = self._extract_html_section(full_content)
            
            if self.verbose:
                print("🧹 Nettoyage...")
            
            html_decoded = self._decode_quoted_printable_section(html_section)
            html_decoded = self._clean_malformed_tags(html_decoded)
            
            html_cleaned = self._process_html_attributes(html_decoded)
            html_cleaned = self._process_form_actions(html_cleaned)
            
            html_cleaned = self._extract_and_inject_css(full_content, html_cleaned)
            html_cleaned = self._extract_and_inject_images(full_content, html_cleaned)
            html_cleaned = self._replace_remaining_localhost_links(html_cleaned)
            html_cleaned = self._remove_fitnesse_buttons(html_cleaned)
            html_cleaned = self._remove_sidenav_div(html_cleaned)
            
            if self.verbose:
                print("  🔄 MHTML → HTML")

            html_cleaned = re.sub(
                r'<link[^>]*href=["\']cid:[^"\']+["\'][^>]*>',
                '', html_cleaned, flags=re.IGNORECASE
            )

            with open(self.output_file, 'w', encoding='utf-8') as f:
                f.write(html_cleaned)
            
            if self.verbose:
                print(f"\n✅ Fichier: {self.output_file}")
            
            return True
            
        except Exception as e:
            print(f"❌ Erreur: {e}", file=sys.stderr)
            return False


def main():
    parser = argparse.ArgumentParser(description='MHTML Cleaner - Converts MHTML to HTML')

    parser.add_argument('input_file', help='Input MHTML file')
    parser.add_argument('-o', '--output', dest='output_file', default=None, help='Output file (default: input name with .html extension)')
    parser.add_argument('-l', '--level', choices=['light', 'moderate', 'strict'], default='moderate')
    parser.add_argument('-p', '--preserve-fitnesse', action='store_true')
    parser.add_argument('-c', '--preserve-css', action='store_true')
    parser.add_argument('-b', '--remove-buttons', action='store_true', help='Remove editing buttons')
    parser.add_argument('-s', '--remove-sidenav', action='store_true', help='Remove sidenav panel')
    parser.add_argument('-A', '--remove-all', action='store_true', help='Preset: enable -b, -s, -v')
    parser.add_argument('-v', '--verbose', action='store_true')

    args = parser.parse_args()

    if not Path(args.input_file).exists():
        print(f"❌ Fichier non trouvé: {args.input_file}", file=sys.stderr)
        sys.exit(1)

    if args.remove_all:
        args.remove_buttons = True
        args.remove_sidenav = True
        args.verbose = True

    if args.output_file is None:
        args.output_file = str(Path(args.input_file).with_suffix('.html'))

    cleaner = MHTMLCleaner(
        input_file=args.input_file,
        output_file=args.output_file,
        level=args.level,
        preserve_fitnesse=args.preserve_fitnesse,
        preserve_css=args.preserve_css,
        verbose=args.verbose,
        remove_buttons=args.remove_buttons,
        remove_sidenav=args.remove_sidenav
    )
    
    success = cleaner.clean()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
