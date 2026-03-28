# 🚀 Quick Start - MHTML Cleaner

## Problème résolu

Vous avez un fichier MHTML généré par Edge à partir de FitNesse, mais :
- ❌ Il affiche une **page blanche** dans Edge
- ❌ Les **liens cassés** vers localhost:50020
- ❌ Les **CSS ne chargent pas** (serveur FitNesse offline)

## Solution

Ce script **injecte automatiquement les CSS FitNesse** directement dans le HTML, créant un fichier **100% autonome**.

---

## ⚡ Utilisation rapide

### Cas standard (recommandé)

```bash
python3 mhtml-cleaner.py votrefichier.mhtml -o sortie.mhtml
```

✅ Niveau **moderate** (défaut) :
- Remplace tous les liens localhost par `#`
- Injecte 231KB de CSS FitNesse
- Neutralise les ressources inaccessibles
- **La page s'affiche parfaitement**

---

## 📋 Exemples concrets

### Exemple 1 : Nettoyage simple
```bash
python3 mhtml-cleaner.py PIDS_FAKE.mhtml -o PIDS_CLEAN.mhtml
```

Résultat: Page stylisée avec navigation locale, 0 erreur 404

### Exemple 2 : Avec rapport détaillé
```bash
python3 mhtml-cleaner.py PIDS_FAKE.mhtml -o PIDS_CLEAN.mhtml --verbose
```

Affiche chaque transformation:
```
✅ CSS injecté: fitnesse-bootstrap.css (206KB)
✅ CSS injecté: fitnesse_wiki.css (4KB)
📝 Style tag injecté: 231KB de CSS
✓ http://localhost:50020/PidS.AnnexeAtr?edit → #
...
```

### Exemple 3 : Nettoyage agressif (strict)
```bash
python3 mhtml-cleaner.py PIDS_FAKE.mhtml -o PIDS_CLEAN.mhtml --level strict
```

Supprime aussi les liens vers d'autres pages FitNesse (plus propre mais moins de navigation)

---

## 🎯 Résultat attendu

| Aspect | Avant | Après |
|--------|-------|-------|
| Affichage dans Edge | ❌ Page blanche | ✅ Page stylisée |
| CSS | ❌ Inexistants | ✅ 231KB injectés |
| Liens internes | ❌ Cassés | ✅ Ancres locales |
| Navigation | ❌ Complète mais cassée | ✅ Locale et fonctionnelle |
| Erreurs console | ❌ 100+ 404 | ✅ Aucune |

---

## 📌 Points importants

### ✅ Ce qui est PRÉSERVÉ
- Structure MHTML originale
- Ressources embarquées (cid:)
- Contenu de la page
- Images et ressources stockées localement

### ✅ Ce qui est TRANSFORMÉ
- `http://localhost:50020/PidS.AnnexeAtr?edit` → `#`
- `http://localhost:50020/files/fitnesse/...` → supprimé/neutralisé
- CSS FitNesse → injecté en `<style>` tag

### ✅ Ce qui fonctionne
- Ouverture dans Edge, Chrome, Firefox
- Navigation via ancres (table des matières)
- Visualisation complète avec styles
- Prêt à l'archivage

---

## 🐛 Troubleshooting

### Q: Le fichier s'ouvre mais la page est encore blanche

**A:** Vérifiez que le script a injecté le CSS:

```bash
grep -c "<style type" sortie.mhtml
```

Devrait afficher: `1` (une balise style)

### Q: Je veux conserver les liens FitNesse même s'ils sont cassés

**A:** Utilisez l'option `--preserve-fitnesse`:

```bash
python3 mhtml-cleaner.py input.mhtml -o output.mhtml --preserve-fitnesse
```

### Q: Je veux plus de détails sur les transformations

**A:** Activez le mode verbeux:

```bash
python3 mhtml-cleaner.py input.mhtml -o output.mhtml --verbose
```

---

## 📦 Fichiers livrés

| Fichier | Rôle |
|---------|------|
| `mhtml-cleaner.py` | **Le script principal** - exécutez-le |
| `README.md` | Documentation technique complète |
| `QUICKSTART.md` | **Ce fichier** - guide rapide |
| `PIDS_PERFECT.mhtml` | Exemple de sortie nettoyée |

---

## ✨ Résumé

1. Lancez le script sur votre fichier MHTML
2. Le script injecte automatiquement les CSS FitNesse
3. Ouvrez le fichier de sortie dans Edge
4. La page s'affiche avec tous les styles ✅
5. Naviguez via les ancres locales ✅

**C'est tout!** 🎉
