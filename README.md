# MHTML Cleaner - Documentation

## 📋 Aperçu

`mhtml-cleaner.py` est un utilitaire Python pour nettoyer les fichiers MHTML générés par Microsoft Edge à partir de pages FitNesse. Il crée un **document 100% autonome** qui s'affiche correctement sans serveur FitNesse.

### ✨ Fonctionnalités principales

- ✅ **Injection CSS automatique** : Extrait les 231KB de CSS FitNesse du fichier MHTML et les injecte dans une balise `<style>` → **la page s'affiche parfaitement**
- ✅ **Conversion des liens** : Remplace les liens `http://localhost:50020/PidS.AnnexeAtr` par des ancres locales `#`
- ✅ **Neutralise les liens cassés** : Remplace les ressources FitNesse inaccessibles par `#` (pas d'erreurs 404)
- ✅ **Gère les paramètres** : Traite les query strings (`.?edit`, `.?properties`, etc.)
- ✅ **Préserve les ressources** : Garde les fichiers embarqués (`cid:`)
- ✅ **Trois niveaux** de nettoyage (light, moderate, strict)

### 🎯 Résultat

Un fichier MHTML qui :
- ✅ S'ouvre dans Edge/Chrome/Firefox
- ✅ Affiche le contenu avec styles (231KB de CSS)
- ✅ Permet la navigation interne via ancres
- ✅ Fonctionne entièrement hors ligne

---

## 🎨 Comment fonctionne l'injection CSS

Le fichier MHTML original contient des **références à des ressources FitNesse** qui ne sont plus accessibles :

```html
<link rel="stylesheet" href="http://localhost:50020/files/fitnesse/css/fitnesse_wiki.css">
<link rel="stylesheet" href="http://localhost:50020/files/fitnesse/bootstrap/css/fitnesse-bootstrap.css">
```

**Le problème :** Sans serveur FitNesse, ces CSS ne se chargent pas → **page blanche**.

**La solution du script :**

1. ✅ **Extrait** les CSS du fichier MHTML (ils y sont embarqués)
2. ✅ **Décode** les sections quoted-printable  
3. ✅ **Injecte** les CSS dans une balise `<style>` unique
4. ✅ **Remplace** les liens `href="http://..."` par `href="#"` (inactifs mais harmless)

**Résultat :** Tous les 231KB de CSS sont présents dans le fichier, la page s'affiche parfaitement.

---

## 🚀 Installation & Utilisation

### Prérequis

- Python 3.7+
- Aucune dépendance externe

### Utilisation basique

```bash
python3 mhtml-cleaner.py input.mhtml -o output.mhtml
```

### Options complètes

```bash
python3 mhtml-cleaner.py input.mhtml -o output.mhtml [options]
```

| Option | Court | Effet |
|--------|-------|-------|
| `--level {light,moderate,strict}` | `-l` | Définit le niveau de nettoyage (défaut: `moderate`) |
| `--preserve-fitnesse` | `-p` | Conserve les liens FitNesse (même cassés) |
| `--preserve-css` | `-c` | Conserve les imports CSS FitNesse |
| `--verbose` | `-v` | Affiche toutes les transformations |
| `--help` | `-h` | Affiche l'aide |

## 📊 Exemple de résultat (PIDS_FAKE.mhtml)

**Avant nettoyage:**
- 121 liens `localhost:50020` non fonctionnels
- CSS inaccessibles → page blanche dans Edge
- Fichier: 597KB

**Après nettoyage (niveau moderate):**
- ✅ 84 liens supprimés (69%)
- ✅ 93 ancres locales créées pour navigation interne
- ✅ 231KB de CSS FitNesse injecté → **page stylisée**
- ✅ Fichier autonome: 823KB
- ✅ Fonctionne dans Edge sans serveur



### 1. **light** (Minimal)

**Comportement:**
- Remplace uniquement les liens `localhost:50020/PidS.AnnexeAtr` (ou votre page) par `#`
- Conserve tous les autres liens

**Cas d'usage:**
- Vous voulez juste rendre la page cliquable localement
- Vous gardez la structure d'origine

**Exemple:**
```bash
python3 mhtml-cleaner.py input.mhtml -o output.mhtml --level light
```

**Transformations:**
```html
<!-- Avant -->
<a href="http://localhost:50020/PidS.AnnexeAtr#section1">Aller à section 1</a>

<!-- Après -->
<a href="#section1">Aller à section 1</a>
```

---

### 2. **moderate** (Recommandé - par défaut)

**Comportement:**
- Remplace les liens vers la même page par `#`
- Désactive les liens vers les ressources FitNesse (`/files/fitnesse/`, etc.) → `#`
- Désactive les liens vers d'autres pages FitNesse → `#`

**Cas d'usage:**
- Cas standard : document autonome sans ressources externes
- Meilleur équilibre entre nettoyage et fonctionnalité

**Exemple:**
```bash
python3 mhtml-cleaner.py input.mhtml -o output.mhtml --level moderate
```

**Transformations:**
```html
<!-- Lien vers la même page -->
<a href="http://localhost:50020/PidS.AnnexeAtr?properties">Propriétés</a>
→ <a href="#">Propriétés</a>

<!-- Ressource FitNesse -->
<link href="http://localhost:50020/files/fitnesse/css/fitnesse.css" rel="stylesheet">
→ <link href="#" rel="stylesheet">

<!-- Lien vers autre page -->
<a href="http://localhost:50020/FrontPage">Accueil</a>
→ <a href="#">Accueil</a>
```

---

### 3. **strict** (Agressif)

**Comportement:**
- Identique à `moderate`
- Supprime activement tous les liens "cassés"

**Cas d'usage:**
- Nettoyage maximal pour une archive finale
- Vous ne voulez aucun lien non-fonctionnel

**Exemple:**
```bash
python3 mhtml-cleaner.py input.mhtml -o output.mhtml --level strict
```

---

## 💡 Exemples d'utilisation avancée

### Mode verbose pour déboguer

```bash
python3 mhtml-cleaner.py input.mhtml -o output.mhtml -v
```

**Résultat:**
```
📖 Lecture: input.mhtml
📄 Page principale détectée: PidS.AnnexeAtr
🔧 Niveau de nettoyage: moderate

🧹 Nettoyage en cours...
  ✓ http://localhost:50020/PidS.AnnexeAtr#section1 → #section1
  ❌ Suppression: http://localhost:50020/files/fitnesse/css/fitnesse.css
  ⚠️  Désactif: http://localhost:50020/FrontPage

✅ Succès! Fichier nettoyé: output.mhtml
```

### Conserver les ressources FitNesse (liens cassés)

```bash
python3 mhtml-cleaner.py input.mhtml -o output.mhtml \
  --level moderate \
  --preserve-fitnesse
```

Utile si vous voulez garder la structure complète même si les ressources ne sont plus disponibles.

### Nettoyage complet avec verbosité

```bash
python3 mhtml-cleaner.py input.mhtml -o output.mhtml \
  --level strict \
  --verbose
```

---

## 🔍 Détails techniques

### Détection de la page principale

Le script détecte automatiquement le nom de la page depuis l'en-tête MHTML:

```
Snapshot-Content-Location: http://localhost:50020/PidS.AnnexeAtr
                                                     ^^^^^^^^^^^^^^^^
                                                  Page détectée ici
```

Les liens pointant vers cette page sont convertis en ancres `#`.

### Ressources FitNesse reconnues

Le script désactive automatiquement les imports de :
- `/files/fitnesse/` - CSS, images, JavaScript FitNesse
- `/files/bootstrap/` - Bootstrap framework
- `/FrontPage` - Pages FitNesse standard
- `/GaeL.*` - Pages du projet GaeL
- `/FitNesse.*` - Pages système FitNesse
- `/RecentChanges` - Historique

### Décodage quoted-printable

Les fichiers MHTML utilisent souvent le codage quoted-printable (=3D pour =, =20 pour espace, etc.). Le script décode automatiquement ces séquences.

---

## 📊 Tableau de décision

Quel niveau choisir?

| Besoin | Niveau | Notes |
|--------|--------|-------|
| Rendre la page cliquable localement | **light** | Minimal, préserve la structure |
| Document autonome standard | **moderate** | ✓ Recommandé pour la plupart des cas |
| Archive finale, aucun lien cassé | **strict** | Nettoyage maximal |
| Conserver liens FitNesse cassés | **\+ --preserve-fitnesse** | Pour archivage fidèle |

---

## 🐛 Dépannage

### Le fichier de sortie n'est pas modifié

**Cause:** Le script détecte peut-être mal le nom de la page.

**Solution:**
```bash
python3 mhtml-cleaner.py input.mhtml -o output.mhtml --verbose
```

Vérifiez que la page détectée est correcte (ligne "Page principale détectée").

### Les liens d'ancre ne fonctionnent pas

**Cause:** Les ancres n'existaient que sur le serveur FitNesse.

**Solution:** C'est normal. Les liens `#` vides empêchent les erreurs 404.

### Le fichier MHTML n'est pas bien decodé

**Cause:** Encodage différent.

**Solution:**
```bash
# Vérifier l'encodage
file -i input.mhtml

# Forcer l'interprétation UTF-8 dans le script
```

---

## 📝 Format de sortie

Le fichier de sortie reste au format MHTML complet :
- ✓ Entête MIME préservée
- ✓ Structure multipart/related maintenue
- ✓ CSS embarqués conservés
- ✓ Liens locaux nettoyés
- ✓ Encodage UTF-8

Vous pouvez ouvrir le fichier `.mhtml` directement dans votre navigateur.

---

## 💻 Intégration en script

```python
from mhtml_cleaner import MHTMLCleaner

cleaner = MHTMLCleaner(
    input_file='input.mhtml',
    output_file='output.mhtml',
    level='moderate',
    verbose=True
)

success = cleaner.clean()
if success:
    print("Nettoyage réussi!")
```

---

## 📄 Licence & Notes

- Script autonome, pas de dépendances externes
- Compatible Python 3.7+
- Testé sur fichiers MHTML générés par Edge
- Préserve la structure MHTML d'origine

---

## 🆘 Support

Pour toute question ou bug report, consultez les logs en mode verbose:

```bash
python3 mhtml-cleaner.py input.mhtml -o output.mhtml -v 2>&1 | tee cleaning.log
```

Le fichier `cleaning.log` contient tous les détails des transformations.
