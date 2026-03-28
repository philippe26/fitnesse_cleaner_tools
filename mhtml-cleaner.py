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
                 verbose: bool = False):
        """
        Initialise le nettoyeur.
        
        Args:
            input_file: Chemin du fichier MHTML à nettoyer
            output_file: Chemin du fichier de sortie
            level: Niveau de nettoyage ('light', 'moderate', 'strict')
            preserve_fitnesse: Conserver les liens FitNesse (liens cassés)
            preserve_css: Conserver les imports CSS même si inaccessibles
            verbose: Mode verbeux
        """
        self.input_file = input_file
        self.output_file = output_file
        self.level = level
        self.preserve_fitnesse = preserve_fitnesse
        self.preserve_css = preserve_css
        self.verbose = verbose
        
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
        if self._is_fitnesse_resource(url) or not self.preserve_fitnesse:
            if self.level in ['moderate', 'strict']:
                return None  # Supprimer le lien
        
        return url
    
    def _process_html_attributes(self, html_content: str) -> str:
        """Traite les attributs href et src du HTML"""
        
        def replace_href(match):
            tag_start = match.group(1)
            attr_name = match.group(2)
            quote = match.group(3)
            url = match.group(4)
            tag_end = match.group(5)
            
            # Vérifier si c'est un lien à supprimer
            if self._should_remove_link(url):
                if self.verbose:
                    print(f"  ❌ Suppression: {url}")
                return f'{tag_start} href={quote}#{quote}{tag_end}'
            
            # Normaliser les liens localhost
            if 'localhost:50020' in url:
                normalized = self._normalize_localhost_link(url)
                if normalized is None:
                    if self.verbose:
                        print(f"  ⚠️  Désactif: {url}")
                    return f'{tag_start} href={quote}#{quote}{tag_end}'
                else:
                    if self.verbose and normalized != url:
                        print(f"  ✓ {url} → {normalized}")
                    return f'{tag_start} {attr_name}={quote}{normalized}{quote}{tag_end}'
            
            return match.group(0)
        
        # Pattern pour href et src
        pattern = r'(<[^>]*?\s)(href|src)(=)(["\'])([^"\']*?)\4([^>]*?>)'
        html_content = re.sub(pattern, replace_href, html_content, flags=re.IGNORECASE)
        
        return html_content
    
    def _process_form_actions(self, html_content: str) -> str:
        """Traite les attributs action des formulaires"""
        
        def replace_action(match):
            tag_start = match.group(1)
            quote = match.group(2)
            url = match.group(3)
            tag_end = match.group(4)
            
            if self._should_remove_link(url):
                if self.verbose:
                    print(f"  ❌ Action supprimée: {url}")
                return f'{tag_start} action={quote}#{quote}{tag_end}'
            
            if 'localhost:50020' in url:
                normalized = self._normalize_localhost_link(url)
                if normalized is None or normalized == "#":
                    return f'{tag_start} action={quote}#{quote}{tag_end}'
                if self.verbose and normalized != url:
                    print(f"  ✓ action: {url} → {normalized}")
                return f'{tag_start} action={quote}{normalized}{quote}{tag_end}'
            
            return match.group(0)
        
        pattern = r'(<form[^>]*?\s)(action)(=)(["\'])([^"\']*?)\4([^>]*?>)'
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
    

    def clean(self) -> bool:
        """
        Nettoie le fichier MHTML.
        
        Returns:
            True si succès, False sinon
        """
        try:
            if self.verbose:
                print(f"📖 Lecture: {self.input_file}")
                print(f"📄 Page principale détectée: {self.main_page}")
                print(f"🔧 Niveau de nettoyage: {self.level}")
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
            
            # ÉTAPE 3: Reconstruire le fichier
            # On doit garder le fichier original mais avec le HTML remplacé
            cleaned_content = full_content[:html_start] + html_cleaned + full_content[html_end:]
            
            # Écrire le fichier de sortie
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
        verbose=args.verbose
    )
    
    success = cleaner.clean()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
