#!/usr/bin/env python3
"""
Validateur de fichiers HTML générés par mhtml-cleaner
Vérifie que le HTML est correct et prêt pour Edge
"""

import sys
import re
from pathlib import Path
from typing import Tuple, List

class HTMLValidator:
    """Validateur de fichiers HTML"""
    
    def __init__(self, html_file: str, verbose: bool = True):
        self.html_file = html_file
        self.verbose = verbose
        self.html = None
        self.issues = []
        self.warnings = []
        self.passed = 0
        self.failed = 0
        
    def load(self) -> bool:
        """Charge le fichier HTML"""
        try:
            with open(self.html_file, 'r', encoding='utf-8') as f:
                self.html = f.read()
            return True
        except Exception as e:
            print(f"❌ Erreur: Impossible de lire {self.html_file}: {e}")
            return False
    
    def validate(self) -> bool:
        """Lance tous les tests"""
        if not self.load():
            return False
        
        print(f"\n╔════════════════════════════════════════════════════════╗")
        print(f"║    🧪 TEST VALIDATION HTML                           ║")
        print(f"║    Fichier: {Path(self.html_file).name:<35} ║")
        print(f"╚════════════════════════════════════════════════════════╝\n")
        
        # Série de tests
        tests = [
            ("Structure HTML", self._test_structure),
            ("Pas de cid: (MHTML)", self._test_no_cid),
            ("Pas de multipart", self._test_no_multipart),
            ("Images injectées", self._test_images_injected),
            ("CSS injecté", self._test_css_injected),
            ("Pas localhost:50020", self._test_no_localhost),
            ("Pas file:// URLs", self._test_no_file_urls),
            ("Tags HTML fermés", self._test_closed_tags),
            ("Ancres fonctionnelles", self._test_anchors),
            ("Taille raisonnable", self._test_file_size),
        ]
        
        for test_name, test_func in tests:
            result = test_func()
            if result:
                self.passed += 1
                if self.verbose:
                    print(f"  ✅ {test_name}")
            else:
                self.failed += 1
                if self.verbose:
                    print(f"  ❌ {test_name}")
        
        # Afficher les résultats
        self._print_summary()
        
        return self.failed == 0
    
    def _test_structure(self) -> bool:
        """Vérifie la structure HTML basique"""
        checks = [
            ('<!DOCTYPE html', 'DOCTYPE'),
            ('<html', '<html>'),
            ('<head', '<head>'),
            ('<body', '<body>'),
        ]
        
        all_ok = True
        for marker, name in checks:
            if marker not in self.html:
                self.issues.append(f"Structure: {name} manquant")
                all_ok = False
        
        return all_ok
    
    def _test_no_cid(self) -> bool:
        """Vérifie l'absence de références cid: (MHTML)"""
        count = self.html.count('cid:')
        if count > 0:
            self.issues.append(f"Trouvé {count} références cid: (MHTML)")
            return False
        return True
    
    def _test_no_multipart(self) -> bool:
        """Vérifie l'absence de structure multipart"""
        if 'multipart' in self.html.lower():
            self.warnings.append("Trouvé 'multipart' dans le HTML")
            return False
        return True
    
    def _test_images_injected(self) -> bool:
        """Vérifie que les images sont injectées en base64"""
        data_urls = re.findall(r'data:image/\w+;base64,', self.html)
        if len(data_urls) < 1:
            self.issues.append("Aucune image en base64 trouvée")
            return False
        
        if self.verbose:
            print(f"    → {len(data_urls)} images en data URLs")
        return True
    
    def _test_css_injected(self) -> bool:
        """Vérifie que le CSS FitNesse est injecté"""
        if '<style' not in self.html or '</style>' not in self.html:
            self.issues.append("CSS <style> tag manquant")
            return False
        
        # Extraire le contenu CSS
        style_match = re.search(r'<style[^>]*>(.*?)</style>', self.html, re.DOTALL)
        if style_match:
            css_size = len(style_match.group(1)) // 1024
            if css_size < 100:
                self.warnings.append(f"CSS très petit ({css_size}KB)")
            if self.verbose:
                print(f"    → {css_size}KB de CSS injecté")
        
        return True
    
    def _test_no_localhost(self) -> bool:
        """Vérifie l'absence de localhost:50020"""
        count = self.html.count('localhost:50020')
        if count > 0:
            # Certaines références localhost peuvent être dans des commentaires/structures complexes
            # Compter seulement celles dans src ou href
            dangerous = re.findall(r'(?:src|href)\s*=\s*["\']([^"\']*localhost:50020[^"\']*)["\']', self.html)
            if dangerous:
                self.issues.append(f"Trouvé {len(dangerous)} références localhost:50020 dans src/href")
                return False
        
        if self.verbose and count > 0:
            print(f"    → {count} références localhost trouvées (acceptables si pas dans src/href)")
        
        return True
    
    def _test_no_file_urls(self) -> bool:
        """Vérifie l'absence de file:// URLs"""
        if 'file://' in self.html:
            self.issues.append("Trouvé des URLs file://")
            return False
        return True
    
    def _test_closed_tags(self) -> bool:
        """Vérifie que les tags importants sont bien fermés"""
        checks = [
            ('<html', '</html>', 'HTML'),
            ('<head', '</head>', 'HEAD'),
            ('<body', '</body>', 'BODY'),
        ]
        
        all_ok = True
        for open_tag, close_tag, name in checks:
            # Utiliser des patterns stricts pour éviter les faux positifs
            # <html> et </html> (pas <html...> qui pourrait matcher <htmlxyz>)
            if open_tag == '<html':
                open_count = len(re.findall(r'<html\s*>', self.html, re.IGNORECASE))
                close_count = self.html.count(close_tag)
            elif open_tag == '<head':
                open_count = len(re.findall(r'<head\s*>', self.html, re.IGNORECASE))
                close_count = self.html.count(close_tag)
            elif open_tag == '<body':
                open_count = len(re.findall(r'<body\s*[^>]*>', self.html, re.IGNORECASE))
                close_count = self.html.count(close_tag)
            else:
                open_count = self.html.count(open_tag)
                close_count = self.html.count(close_tag)
            
            if open_count != close_count:
                self.issues.append(f"{name}: {open_count} ouvert(s), {close_count} fermé(s)")
                all_ok = False
        
        return all_ok
    
    def _test_anchors(self) -> bool:
        """Vérifie la présence d'ancres # pour navigation"""
        anchors = len(re.findall(r'href="#[^"]*"', self.html))
        
        if anchors == 0:
            self.warnings.append("Aucune ancre # trouvée")
            return False
        
        if self.verbose:
            print(f"    → {anchors} ancres # trouvées")
        
        return True
    
    def _test_file_size(self) -> bool:
        """Vérifie que la taille du fichier est raisonnable"""
        size_kb = len(self.html) // 1024
        size_mb = size_kb / 1024
        
        if size_mb > 50:
            self.warnings.append(f"Fichier très gros ({size_mb:.1f}MB)")
        elif size_mb < 0.1:
            self.warnings.append(f"Fichier suspect ({size_mb:.2f}MB)")
        
        if self.verbose:
            print(f"    → Taille: {size_mb:.2f}MB")
        
        return True
    
    def _print_summary(self) -> bool:
        """Affiche le résumé des tests"""
        print(f"\n{'='*60}")
        print(f"RÉSULTAT: {self.passed} ✅  /  {self.failed} ❌")
        print(f"{'='*60}")
        
        if self.issues:
            print(f"\n⚠️  ERREURS ({len(self.issues)}):")
            for issue in self.issues:
                print(f"  ❌ {issue}")
        
        if self.warnings:
            print(f"\n⚠️  AVERTISSEMENTS ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"  ⚠️  {warning}")
        
        if self.failed == 0 and not self.issues:
            print(f"\n✅ TOUS LES TESTS RÉUSSIS!")
            print(f"Le fichier est prêt pour Edge.")
            return True
        else:
            print(f"\n❌ CERTAINS TESTS ONT ÉCHOUÉ")
            return False

def main():
    """Point d'entrée"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Validateur de fichiers HTML générés par mhtml-cleaner'
    )
    parser.add_argument('html_file', help='Fichier HTML à tester')
    parser.add_argument('-q', '--quiet', action='store_true', 
                        help='Mode silencieux (affiche seulement le résumé)')
    
    args = parser.parse_args()
    
    if not Path(args.html_file).exists():
        print(f"❌ Erreur: Fichier non trouvé: {args.html_file}")
        sys.exit(1)
    
    validator = HTMLValidator(args.html_file, verbose=not args.quiet)
    success = validator.validate()
    
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
