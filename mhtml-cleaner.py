#!/usr/bin/env python3
"""
MHTML Cleaner v2.2 - Nettoie les fichiers MHTML générés par Edge/FitNesse
- Remplace les liens localhost par des ancres locales
- Supprime les ressources inaccessibles
- Injecte les CSS et images base64
- Supprime les boutons FitNesse optionnellement
"""

import re
import argparse
import sys
import base64
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from typing import Tuple, Set


class MHTMLCleaner:
    """Nettoyeur de fichiers MHTML"""
    
    # Patterns pour détecter FitNesse et ses ressources
    FITNESSE_PATTERNS = [
        r'files/fitnesse/',
        r'files/bootstrap/',
        r'/FrontPage',
        r'/GaeL\.',
        r'/FitNesse\.',
        r'/RecentChanges',
    ]
    
    # Boutons FitNesse à supprimer
    FITNESSE_BUTTONS = [
        'Edit', 'Versions', 'Attributes', 'Review', 
        'Rationale', 'Expand', 'Collapse'
    ]
    
    def __init__(self, input_file: str, output_file: str, level: str = 'moderate', 
                 preserve_fitnesse: bool = False, preserve_css: bool = False,
                 verbose: bool = False, output_format: str = 'html',
                 remove_buttons: bool = False, remove_sidenav: bool = False):
        """
        Initialise le nettoyeur.
        
        Args:
            input_file: Chemin du fichier MHTML à nettoyer
            output_file: Chemin du fichier de sortie
            level: Niveau de nettoyage ('light', 'moderate', 'strict')
            preserve_fitnesse: Conserver les liens FitNesse (liens cassés)
            preserve_css: Conserver les imports CSS même si inaccessibles
            verbose: Mode verbeux
            output_format: Format de sortie ('html' ou 'mhtml')
            remove_buttons: Supprimer les boutons FitNesse
            remove_sidenav: Supprimer le panneau de navigation latéral
        """
        self.input_file = input_file
        self.output_file = output_file
        self.level = level
        self.preserve_fitnesse = preserve_fitnesse
        self.preserve_css = preserve_css
        self.verbose = verbose
        self.output_format = output_format.lower()
        self.remove_buttons = remove_buttons
        self.remove_sidenav = remove_sidenav
        
        # Extraire le nom de la page principale
        self.main_page = self._extract_main_page_name()
    
    def _extract_main_page_name(self) -> str:
        """Extrait le nom de la page principale depuis le fichier MHTML"""
        try:
            with open(self.input_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read(5000)
            
            match = re.search(r'Snapshot-Content-Location: [^/]*?([^/\s]+)[\s$]', content)
            if match:
                return match.group(1)
        except:
            pass
        
        return "Unknown"
    
    def _extract_html_section(self, content: str) -> Tuple[str, int, int]:
        """Extrait la section HTML principale du fichier MHTML"""
        # Chercher le DOCTYPE en priorité
        html_start = content.find('<!DOCTYPE')
        if html_start == -1:
            html_start = content.find('<!doctype')
        
        # Sinon chercher <html>
        if html_start == -1:
            html_start = content.find('<html')
        
        if html_start == -1:
            html_start = content.find('<HTML')
        
        # Trouver la fin (avant la prochaine limite de boundary)
        boundary_idx = content.find('\n------', html_start)
        if boundary_idx == -1:
            boundary_idx = len(content)
        
        return content[html_start:boundary_idx], html_start, boundary_idx
    
    def _create_placeholder_images(self) -> dict:
        """
        Crée des images SVG placeholders pour les images manquantes.
        
        Returns:
            Dictionnaire {filename: data_url}
        """
        placeholders = {}
        
        # Image pour collapsibleOpen (trait épais noir)
        svg_collapsible = '''<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">
  <line x1="2" y1="8" x2="14" y2="8" stroke="black" stroke-width="3" stroke-linecap="round"/>
</svg>'''
        
        # Image pour collapsibleClosed (trait + vertical)
        svg_collapsed = '''<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">
  <line x1="2" y1="8" x2="14" y2="8" stroke="black" stroke-width="3" stroke-linecap="round"/>
  <line x1="8" y1="2" x2="8" y2="14" stroke="black" stroke-width="3" stroke-linecap="round"/>
</svg>'''
        
        # Encoder en base64
        collapsible_b64 = base64.b64encode(svg_collapsible.encode()).decode()
        collapsed_b64 = base64.b64encode(svg_collapsed.encode()).decode()
        
        placeholders['collapsibleOpen.png'] = f'data:image/svg+xml;base64,{collapsible_b64}'
        placeholders['collapsibleClosed.png'] = f'data:image/svg+xml;base64,{collapsed_b64}'
        placeholders['collapse.gif'] = f'data:image/svg+xml;base64,{collapsible_b64}'
        placeholders['expand.gif'] = f'data:image/svg+xml;base64,{collapsed_b64}'
        
        if self.verbose:
            print(f"  🎨 {len(placeholders)} images SVG placeholder créées")
        
        return placeholders
    
    def _remove_fitnesse_buttons(self, html_content: str) -> str:
        """
        Supprime ou masque les boutons FitNesse spécifiés.
        
        Cherche les patterns comme:
        - <a ... title="Edit">Edit</a>
        - <button ... name="edit">Edit</button>
        """
        
        if not self.remove_buttons:
            return html_content
        
        removed_count = 0
        
        for button_name in self.FITNESSE_BUTTONS:
            # Pattern 1: <a ... title="...">buttonname</a>
            pattern1 = rf'<a[^>]*title=["\']?{button_name}["\']?[^>]*>[^<]*{button_name}[^<]*</a>'
            html_content = re.sub(pattern1, '', html_content, flags=re.IGNORECASE)
            
            # Pattern 2: <button ... name="...">buttonname</button>
            pattern2 = rf'<button[^>]*name=["\']?{button_name.lower()}["\']?[^>]*>[^<]*{button_name}[^<]*</button>'
            html_content = re.sub(pattern2, '', html_content, flags=re.IGNORECASE)
            
            # Pattern 3: <input type="button" value="buttonname">
            pattern3 = rf'<input[^>]*type=["\']?button["\']?[^>]*value=["\']?{button_name}["\']?[^>]*/?>|<input[^>]*value=["\']?{button_name}["\']?[^>]*type=["\']?button["\']?[^>]*/?>]'
            html_content = re.sub(pattern3, '', html_content, flags=re.IGNORECASE)
            
            # Pattern 4: Lien avec texte exact
            pattern4 = rf'<a[^>]*>\s*{button_name}\s*</a>'
            html_content = re.sub(pattern4, '', html_content, flags=re.IGNORECASE)
        
        if self.verbose:
            print(f"  🗑️  Boutons FitNesse supprimés")
        
        return html_content
    
    def _decode_quoted_printable_section(self, content: str) -> str:
        """Décode une section encodée en quoted-printable"""
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
        """Extrait les CSS FitNesse du MHTML et les injecte en <style> tags"""
        
        css_sections = re.findall(
            r'Content-Location: (http://localhost:50020/files/fitnesse[^\n]+)\n\n(.+?)\n------',
            full_content,
            re.DOTALL
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
            print(f"  📝 Style tag injecté: {len(combined_css) // 1024}KB de CSS")
        
        return html_content
    
    def _clean_css_data_urls(self, html_content: str) -> str:
        """
        Nettoie les CSS contenant des data URLs malformées.
        Corrige les patterns comme: url("../../images/data:image/...")
        En: url("data:image/...")
        """
        # Pattern: url("...chemin.../data:image/...")
        # Extraire juste la partie data: en supprimant le chemin avant
        pattern = r'url\(["\']([^"\']*?)(data:image/[^"\']*)["\']'
        html_content = re.sub(
            pattern,
            r'url("\2")',
            html_content,
            flags=re.IGNORECASE
        )
        
        # Pattern 2: url(data:image/...) sans guillemets (rare mais possible)
        pattern2 = r'url\(([^)]*?)(data:image/[^)]+)\)'
        html_content = re.sub(
            pattern2,
            r'url("\2")',
            html_content,
            flags=re.IGNORECASE
        )
        
        if self.verbose:
            print(f"  🔧 CSS data URLs nettoyées")
        
        return html_content
    
    def _remove_sidenav(self, html_content: str) -> str:
        """
        Supprime le panneau de navigation latéral (sidenav/sidebar).
        """
        if not self.remove_sidenav:
            return html_content
        
        # Pattern 1: <div id="sidenav" ...>...</div>
        html_content = re.sub(
            r'<div[^>]*(?:id|class)=["\']?[^"\']*sidenav[^"\']*["\']?[^>]*>.*?</div>',
            '',
            html_content,
            flags=re.IGNORECASE | re.DOTALL
        )
        
        # Pattern 2: <nav class="sidenav" ...>...</nav>
        html_content = re.sub(
            r'<nav[^>]*sidenav[^>]*>.*?</nav>',
            '',
            html_content,
            flags=re.IGNORECASE | re.DOTALL
        )
        
        # Pattern 3: <aside id="sidebar" ...>...</aside>
        html_content = re.sub(
            r'<aside[^>]*(?:id|class)=["\']?[^"\']*(?:sidebar|sidenav)[^"\']*["\']?[^>]*>.*?</aside>',
            '',
            html_content,
            flags=re.IGNORECASE | re.DOTALL
        )
        
        # Pattern 4: Éléments avec class contenant "sidenav" ou "sidebar"
        html_content = re.sub(
            r'<[^>]*class=["\']([^"\']*(?:sidenav|sidebar)[^"\']*)["\'][^>]*>.*?</[^>]+>',
            '',
            html_content,
            flags=re.IGNORECASE | re.DOTALL
        )
        
        # Également supprimer le CSS associé
        html_content = re.sub(
            r'/\*[\s\S]*?\.sidenav[\s\S]*?\*/|\.sidenav[^{]*{[^}]*}',
            '',
            html_content,
            flags=re.IGNORECASE
        )
        
        html_content = re.sub(
            r'/\*[\s\S]*?\.sidebar[\s\S]*?\*/|\.sidebar[^{]*{[^}]*}',
            '',
            html_content,
            flags=re.IGNORECASE
        )
        
        if self.verbose:
            print(f"  🗑️  Panneau sidenav supprimé")
        
        return html_content
    
    def _extract_and_inject_images(self, full_content: str, html_content: str) -> str:
        """Extrait les images du MHTML et les injecte en data URLs base64"""
        
        pattern = r'Content-Type: (image/\w+).*?\r?\nContent-Transfer-Encoding: base64\r?\nContent-Location: ([^\r\n]+)\r?\n\r?\n((?:[A-Za-z0-9+/=\r\n]+))'
        
        image_map = {}
        
        for match in re.finditer(pattern, full_content, re.MULTILINE | re.DOTALL):
            mime_type = match.group(1)
            location = match.group(2).strip()
            base64_data_raw = match.group(3)
            
            base64_data = ''.join(base64_data_raw.split())
            
            if location.startswith('cid:'):
                filename = location
            else:
                filename = location.split('/')[-1]
            
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
        else:
            # Remplacer les images extraites
            for location, img_info in image_map.items():
                mime_type = img_info['mime']
                base64_data = img_info['base64']
                data_url = f'data:{mime_type};base64,{base64_data}'
                
                # Remplacer l'URL complète (avec &amp;, paramètres, etc.)
                escaped_location = re.escape(location)
                html_content = re.sub(
                    rf'(["\'])({escaped_location}|{re.escape(location.replace("&", "&amp;"))})(["\'])',
                    rf'\1{re.escape(data_url)}\3',
                    html_content,
                    flags=re.IGNORECASE
                )
                
                # Remplacer par nom de fichier simple
                filename = img_info['filename']
                if filename and not filename.startswith('cid:'):
                    escaped_filename = re.escape(filename)
                    html_content = re.sub(
                        escaped_filename,
                        data_url,
                        html_content,
                        flags=re.IGNORECASE
                    )
            
            if self.verbose:
                print(f"  ✅ {len(image_map)} images injectées en base64")
        
        # Ajouter les images placeholder
        placeholders = self._create_placeholder_images()
        for filename, data_url in placeholders.items():
            escaped_filename = re.escape(filename)
            html_content = re.sub(
                escaped_filename,
                data_url,
                html_content,
                flags=re.IGNORECASE
            )
        
        return html_content
    
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
        if not url.startswith('http://localhost:50020/'):
            return None
        
        path = url[24:]  # Enlever "http://localhost:50020/"
        
        if self.main_page in path:
            # Même page - utiliser une ancre
            match = re.search(rf'{self.main_page}([^/&]*)', path)
            if match:
                anchor = match.group(1)
                if anchor.startswith('?') or anchor.startswith('#'):
                    return f"#{anchor.lstrip('?#')}"
                return '#'
        
        return None
    
    def _process_html_attributes(self, html_content: str) -> str:
        """Remplace les attributs href/src dans le HTML"""
        
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
        html_content = re.sub(pattern, replace_action, html_content, flags=re.IGNORECASE)
        
        return html_content
    
    def _process_form_actions(self, html_content: str) -> str:
        """Remplace les action=... dans les formulaires"""
        
        def replace_action(m):
            action = m.group(1)
            if self._should_remove_link(action):
                return ''
            
            normalized = self._normalize_localhost_link(action)
            if normalized:
                return f' action="{normalized}"'
            return m.group(0)
        
        pattern = r' action=(["\'])([^"\']*?)\1'
        html_content = re.sub(pattern, replace_action, html_content, flags=re.IGNORECASE)
        
        return html_content
    
    def _replace_remaining_localhost_links(self, html_content: str) -> str:
        """Remplace les URLs localhost restantes par #"""
        pattern = r'((?:src|href)\s*=\s*["\'])([^"\']*?localhost:50020[^"\']*?)(["\'])'
        
        def replacer(m):
            prefix = m.group(1)
            url = m.group(2)
            suffix = m.group(3)
            
            url_normalized = url.replace('&amp;', '&')
            
            if self._should_remove_link(url_normalized):
                return ''
            else:
                return f'{prefix}#{suffix}'
        
        html_content = re.sub(pattern, replacer, html_content, flags=re.IGNORECASE)
        
        return html_content
    
    def _clean_malformed_tags(self, html_content: str) -> str:
        """Nettoie les tags HTML mal formés"""
        html_content = re.sub(r'<head>\s*<head[^>]*>', '<head>', html_content, flags=re.IGNORECASE)
        head_close_count = html_content.count('</head>')
        if head_close_count > 1:
            parts = html_content.split('</head>')
            html_content = '</head>'.join(parts[:-1]) + '</head>' + parts[-1]
        
        html_content = re.sub(r'<body>\s*<body[^>]*>', '<body>', html_content, flags=re.IGNORECASE)
        html_content = re.sub(r'</body>\s*</body>', '</body>', html_content, flags=re.IGNORECASE)
        
        return html_content
    
    def clean(self) -> bool:
        """Nettoie le fichier MHTML et le convertit en HTML pur"""
        try:
            if self.verbose:
                print(f"📖 Lecture: {self.input_file}")
                print(f"📄 Page principale détectée: {self.main_page}")
                print(f"🔧 Niveau de nettoyage: {self.level}")
                print(f"📝 Format de sortie: {self.output_format.upper()}")
                if self.remove_buttons:
                    print(f"🗑️  Suppression des boutons: OUI")
                if self.remove_sidenav:
                    print(f"🗑️  Suppression du sidenav: OUI")
                print()
            
            with open(self.input_file, 'r', encoding='utf-8') as f:
                full_content = f.read()
            
            html_section, html_start, html_end = self._extract_html_section(full_content)
            
            if self.verbose:
                print("🧹 Nettoyage en cours...")
            
            html_decoded = self._decode_quoted_printable_section(html_section)
            html_decoded = self._clean_malformed_tags(html_decoded)
            
            html_cleaned = self._process_html_attributes(html_decoded)
            html_cleaned = self._process_form_actions(html_cleaned)
            
            html_cleaned = self._extract_and_inject_css(full_content, html_cleaned)
            html_cleaned = self._extract_and_inject_images(full_content, html_cleaned)
            html_cleaned = self._replace_remaining_localhost_links(html_cleaned)
            html_cleaned = self._clean_css_data_urls(html_cleaned)
            html_cleaned = self._remove_fitnesse_buttons(html_cleaned)
            html_cleaned = self._remove_sidenav(html_cleaned)
            
            if self.output_format == 'html':
                if self.verbose:
                    print("  🔄 Conversion: MHTML → HTML pur")
                
                html_cleaned = re.sub(
                    r'<link[^>]*href=["\']cid:[^"\']+["\'][^>]*>',
                    '',
                    html_cleaned,
                    flags=re.IGNORECASE
                )
                
                with open(self.output_file, 'w', encoding='utf-8') as f:
                    f.write(html_cleaned)
            else:
                if self.verbose:
                    print("  🔄 Format: MHTML multipart preservé")
                cleaned_content = full_content[:html_start] + html_cleaned + full_content[html_end:]
                with open(self.output_file, 'w', encoding='utf-8') as f:
                    f.write(cleaned_content)
            
            if self.verbose:
                print(f"\n✅ Succès! Fichier nettoyé: {self.output_file}")
            
            return True
            
        except Exception as e:
            print(f"❌ Erreur: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            return False


def main():
    """Point d'entrée CLI"""
    parser = argparse.ArgumentParser(
        description='MHTML Cleaner - Convertit les fichiers MHTML en HTML',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Niveaux de nettoyage:
  light     - Remplace seulement les liens localhost vers la même page par # (par défaut)
  moderate  - Désactive aussi les liens vers les ressources FitNesse inaccessibles
  strict    - Supprime tous les liens vers d'autres pages non disponibles

Exemples:
  %(prog)s input.mhtml -o output.html
  %(prog)s input.mhtml -o output.html --level strict --remove-buttons
  %(prog)s input.mhtml -o output.html --format html --verbose
        '''
    )
    
    parser.add_argument('input_file', help='Fichier MHTML à nettoyer')
    parser.add_argument('-o', '--output', dest='output_file', required=True,
                        help='Fichier de sortie')
    parser.add_argument('-l', '--level', choices=['light', 'moderate', 'strict'],
                        default='moderate',
                        help='Niveau de nettoyage (défaut: moderate)')
    parser.add_argument('-p', '--preserve-fitnesse', action='store_true',
                        help='Préserver les liens FitNesse (générer des liens cassés)')
    parser.add_argument('-c', '--preserve-css', action='store_true',
                        help='Préserver les imports CSS FitNesse')
    parser.add_argument('-f', '--format', choices=['html', 'mhtml'],
                        default='html',
                        help='Format de sortie: html (recommandé) ou mhtml (défaut: html)')
    parser.add_argument('-r', '--remove-buttons', action='store_true',
                        help='Supprimer les boutons FitNesse (Edit, Versions, Attributes, etc.)')
    parser.add_argument('-s', '--remove-sidenav', action='store_true',
                        help='Supprimer le panneau de navigation latéral (sidenav)')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Mode verbeux - affiche les transformations')
    
    args = parser.parse_args()
    
    if not Path(args.input_file).exists():
        print(f"❌ Erreur: fichier d'entrée non trouvé: {args.input_file}", file=sys.stderr)
        sys.exit(1)
    
    cleaner = MHTMLCleaner(
        input_file=args.input_file,
        output_file=args.output_file,
        level=args.level,
        preserve_fitnesse=args.preserve_fitnesse,
        preserve_css=args.preserve_css,
        verbose=args.verbose,
        output_format=args.format,
        remove_buttons=args.remove_buttons,
        remove_sidenav=args.remove_sidenav
    )
    
    success = cleaner.clean()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
