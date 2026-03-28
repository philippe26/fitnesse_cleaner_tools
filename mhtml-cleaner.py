#!/usr/bin/env python3
"""
MHTML Cleaner - Nettoie les fichiers MHTML générés par Edge/FitNesse
Remplace les liens localhost par des ancres locales et supprime les ressources inaccessibles.
"""

import re
import argparse
import sys
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
    
    def __init__(self, input_file: str, output_file: str, level: str = 'moderate', 
                 preserve_fitnesse: bool = False, preserve_css: bool = False,
                 verbose: bool = False, output_format: str = 'html'):
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
        """
        self.input_file = input_file
        self.output_file = output_file
        self.level = level
        self.preserve_fitnesse = preserve_fitnesse
        self.preserve_css = preserve_css
        self.verbose = verbose
        self.output_format = output_format.lower()
        
        # Extraire le nom de la page principale
        self.main_page = self._extract_main_page_name()
        
    def _extract_main_page_name(self) -> str:
        """Extrait le nom de la page principale depuis l'en-tête MHTML"""
        try:
            with open(self.input_file, 'r', encoding='utf-8') as f:
                content = f.read(2000)  # Lire seulement le début
                # Chercher la première occurence de Snapshot-Content-Location
                match = re.search(r'Snapshot-Content-Location:\s*http://localhost:\d+/([^\s\?#]+)', content)
                if match:
                    page_name = match.group(1)
                    if page_name:
                        return page_name
        except Exception as e:
            if self.verbose:
                print(f"Avertissement: impossible d'extraire le nom de page: {e}")
        return "index"
    
    def _is_fitnesse_resource(self, url: str) -> bool:
        """Vérifie si une URL est une ressource FitNesse"""
        for pattern in self.FITNESSE_PATTERNS:
            if re.search(pattern, url, re.IGNORECASE):
                return True
        return False
    
    def _should_remove_link(self, url: str) -> bool:
        """Détermine si un lien doit être supprimé"""
        # IMPORTANT: Ne JAMAIS supprimer les liens cid: (ressources MHTML embarquées)
        if url.startswith('cid:'):
            return False
        
        # Ne rien supprimer en mode light
        if self.level == 'light':
            return False
        
        # Ressources FitNesse
        if self._is_fitnesse_resource(url) and not self.preserve_fitnesse:
            return True
        
        # Liens vers d'autres pages FitNesse (pas la page courante)
        if 'localhost:50020/' in url:
            # Extraire le chemin
            match = re.search(r'localhost:50020/(.+?)(?:\?|#|$)', url)
            if match:
                page_name = match.group(1)
                if page_name != self.main_page:
                    if self.level == 'strict':
                        return True
        
        return False
    
    def _normalize_localhost_link(self, url: str) -> str:
        """
        Normalise un lien localhost.
        
        Si le lien pointe vers la même page: #
        Si le lien pointe vers une autre page et doit être supprimé: retourne None
        Sinon: retourne l'ancre ou le lien original
        """
        # Extraire la partie du lien
        match = re.search(r'localhost:50020/(.+?)(?:\?|#|$)', url)
        
        if not match:
            return url
        
        page_and_anchor = match.group(1)
        
        # Vérifier si c'est la même page
        if page_and_anchor.startswith(self.main_page):
            # Extraire l'ancre si présente
            anchor_match = re.search(r'#(\w+)', url)
            if anchor_match:
                return f"#{anchor_match.group(1)}"
            return "#"
        
        # Lien vers une autre page
        if self._is_fitnesse_resource(url) and not self.preserve_fitnesse:
            if self.level in ['moderate', 'strict']:
                return None  # Supprimer le lien
        
        return url
    
    def _process_html_attributes(self, html_content: str) -> str:
        """Traite les attributs href et src du HTML"""
        
        def replace_href(match):
            before = match.group(1)
            attr_name = match.group(2)
            quote_char = match.group(3)
            url = match.group(4)
            after = match.group(5)
            
            # Vérifier si c'est un lien à supprimer
            if self._should_remove_link(url):
                if self.verbose:
                    print(f"  ❌ Suppression: {url}")
                return f'{before}{attr_name}={quote_char}#{quote_char}{after}'
            
            # Normaliser les liens localhost
            if 'localhost:50020' in url:
                normalized = self._normalize_localhost_link(url)
                if normalized is None:
                    if self.verbose:
                        print(f"  ⚠️  Désactif: {url}")
                    return f'{before}{attr_name}={quote_char}#{quote_char}{after}'
                else:
                    if self.verbose and normalized != url:
                        print(f"  ✓ {url} → {normalized}")
                    return f'{before}{attr_name}={quote_char}{normalized}{quote_char}{after}'
            
            return match.group(0)
        
        # Pattern simplifié: (avant)(href|src)(=)(quote)(url)(quote)(après)
        # Chercher href ou src suivi de = et d'une URL entre guillemets
        pattern = r'((?:href|src)\s*=\s*)(["\'])([^"\']*?)\2'
        
        def replace_simple(m):
            attr_with_eq = m.group(1)
            quote_char = m.group(2)
            url = m.group(3)
            
            # Vérifier si c'est un lien à supprimer
            if self._should_remove_link(url):
                if self.verbose:
                    print(f"  ❌ Suppression: {url}")
                return f'{attr_with_eq}{quote_char}#{quote_char}'
            
            # Normaliser les liens localhost
            if 'localhost:50020' in url:
                normalized = self._normalize_localhost_link(url)
                if normalized is None:
                    if self.verbose:
                        print(f"  ⚠️  Désactif: {url}")
                    return f'{attr_with_eq}{quote_char}#{quote_char}'
                else:
                    if self.verbose and normalized != url:
                        print(f"  ✓ {url} → {normalized}")
                    return f'{attr_with_eq}{quote_char}{normalized}{quote_char}'
            
            return m.group(0)
        
        html_content = re.sub(pattern, replace_simple, html_content, flags=re.IGNORECASE)
        
        return html_content
    
    def _process_form_actions(self, html_content: str) -> str:
        """Traite les attributs action des formulaires"""
        
        pattern = r'(action\s*=\s*)(["\'])([^"\']*?)\2'
        
        def replace_action(m):
            attr_with_eq = m.group(1)
            quote_char = m.group(2)
            url = m.group(3)
            
            if self._should_remove_link(url):
                if self.verbose:
                    print(f"  ❌ Action supprimée: {url}")
                return f'{attr_with_eq}{quote_char}#{quote_char}'
            
            if 'localhost:50020' in url:
                normalized = self._normalize_localhost_link(url)
                if normalized is None or normalized == "#":
                    return f'{attr_with_eq}{quote_char}#{quote_char}'
                if self.verbose and normalized != url:
                    print(f"  ✓ action: {url} → {normalized}")
                return f'{attr_with_eq}{quote_char}{normalized}{quote_char}'
            
            return m.group(0)
        
        html_content = re.sub(pattern, replace_action, html_content, flags=re.IGNORECASE)
        
        return html_content
    
    def _decode_quoted_printable_section(self, content: str) -> str:
        """Décode une section encodée en quoted-printable"""
        # Étape 1: joindre les lignes avec = final (soft line break)
        # Un = à la fin signifie que la ligne continue
        lines = content.split('\n')
        decoded = []
        i = 0
        while i < len(lines):
            line = lines[i]
            # Si la ligne finit par =, c'est une continuation
            while i < len(lines) and line.endswith('=') and not line.endswith('=='):
                line = line[:-1] + lines[i + 1]
                i += 1
            decoded.append(line)
            i += 1
        
        result = '\n'.join(decoded)
        
        # Étape 2: remplacer les séquences encoded-quoted-printable
        replacements = {
            '=3D': '=',
            '=20': ' ',
            '=3B': ';',
            '=3A': ':',
            '=2F': '/',
            '=3F': '?',
            '=26': '&',
            '=22': '"',
            '=27': "'",
            '=0D': '\r',
            '=0A': '\n',
            '=09': '\t',
        }
        
        for encoded, decoded_char in replacements.items():
            result = result.replace(encoded, decoded_char)
        
        return result
    
    def _extract_html_section(self, content: str) -> Tuple[str, int, int]:
        """Extrait la section HTML principale du fichier MHTML"""
        # Trouver le début du HTML
        html_start = content.find('<!DOCTYPE html')
        if html_start == -1:
            html_start = content.find('<html')
        
        # Trouver la fin (avant la prochaine limite de boundary)
        boundary_idx = content.find('\n------', html_start)
        if boundary_idx == -1:
            boundary_idx = len(content)
        
        return content[html_start:boundary_idx], html_start, boundary_idx
    
    def _extract_and_inject_css(self, full_content: str, html_content: str) -> str:
        """Extrait les CSS FitNesse du MHTML et les injecte en <style> tags"""
        
        # Extraire toutes les sections CSS FitNesse du fichier MHTML
        css_sections = re.findall(
            r'Content-Location: (http://localhost:50020/files/fitnesse[^\n]+)\n\n(.+?)\n------',
            full_content,
            re.DOTALL
        )
        
        if not css_sections:
            if self.verbose:
                print("  ℹ️  Aucun CSS FitNesse à injecter")
            return html_content
        
        # Décoder et concaténer les CSS principaux
        injected_css = []
        for location, css_body in css_sections:
            # Décoder quoted-printable
            css_decoded = self._decode_quoted_printable_section(css_body)
            injected_css.append(css_decoded)
            
            # Montrer seulement les CSS importants en verbose
            if 'fitnesse_wiki' in location or 'fitnesse-bootstrap' in location:
                if self.verbose:
                    size_kb = len(css_decoded) // 1024
                    print(f"  ✅ CSS injecté: {location.split('/')[-1]} ({size_kb}KB)")
        
        combined_css = "\n\n".join(injected_css)
        
        # Injecter dans le HTML juste avant </head>
        style_tag = f'<style type="text/css">\n{combined_css}\n</style>'
        html_content = html_content.replace('</head>', f'{style_tag}\n</head>')
        
        if self.verbose:
            print(f"  📝 Style tag injecté: {len(combined_css) // 1024}KB de CSS")
        
        return html_content

    def clean(self) -> bool:
        """
        Nettoie le fichier MHTML et le convertit en HTML pur.
        
        Returns:
            True si succès, False sinon
        """
        try:
            if self.verbose:
                print(f"📖 Lecture: {self.input_file}")
                print(f"📄 Page principale détectée: {self.main_page}")
                print(f"🔧 Niveau de nettoyage: {self.level}")
                print(f"📝 Format de sortie: {self.output_format.upper()}")
                print()
            
            with open(self.input_file, 'r', encoding='utf-8') as f:
                full_content = f.read()
            
            # Extraire les différentes sections
            html_section, html_start, html_end = self._extract_html_section(full_content)
            
            if self.verbose:
                print("🧹 Nettoyage en cours...")
            
            # ÉTAPE 1: Décoder la section HTML
            html_decoded = self._decode_quoted_printable_section(html_section)
            
            # ÉTAPE 2: Appliquer les transformations
            html_cleaned = self._process_html_attributes(html_decoded)
            html_cleaned = self._process_form_actions(html_cleaned)
            
            # ÉTAPE 3: Injecter les CSS FitNesse pour que la page soit stylisée
            html_cleaned = self._extract_and_inject_css(full_content, html_cleaned)
            
            # ÉTAPE 4: Sauvegarder selon le format
            if self.output_format == 'html':
                # Convertir en HTML pur - extrait juste le HTML
                if self.verbose:
                    print("  🔄 Conversion: MHTML → HTML pur")
                
                # Supprimer les références cid: (ressources MHTML qui n'existent pas en HTML)
                html_cleaned = re.sub(
                    r'<link[^>]*href=["\']cid:[^"\']+["\'][^>]*>',
                    '',
                    html_cleaned,
                    flags=re.IGNORECASE
                )
                
                with open(self.output_file, 'w', encoding='utf-8') as f:
                    f.write(html_cleaned)
            else:
                # Garder le format MHTML - reconstruit avec la structure multipart
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
    """Point d'entrée du script"""
    parser = argparse.ArgumentParser(
        description='Nettoie les fichiers MHTML générés par Edge/FitNesse',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Niveaux de nettoyage:
  light     - Remplace seulement les liens localhost vers la même page par # (par défaut)
  moderate  - Désactive aussi les liens vers les ressources FitNesse inaccessibles
  strict    - Supprime tous les liens vers d'autres pages non disponibles

Exemples:
  %(prog)s input.mhtml -o output.mhtml
  %(prog)s input.mhtml -o output.mhtml --level strict
  %(prog)s input.mhtml -o output.mhtml --level strict --preserve-fitnesse --verbose
        """
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
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Mode verbeux - affiche les transformations')
    
    args = parser.parse_args()
    
    # Valider les fichiers
    if not Path(args.input_file).exists():
        print(f"❌ Erreur: fichier d'entrée non trouvé: {args.input_file}", file=sys.stderr)
        sys.exit(1)
    
    # Créer le nettoyeur et exécuter
    cleaner = MHTMLCleaner(
        input_file=args.input_file,
        output_file=args.output_file,
        level=args.level,
        preserve_fitnesse=args.preserve_fitnesse,
        preserve_css=args.preserve_css,
        verbose=args.verbose,
        output_format=args.format
    )
    
    success = cleaner.clean()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
