# Search Doc Tool

Outil de recherche de termes dans des fichiers Word (.docx) et PDF. Disponible en application bureau (PyQt6) et application web (Django).

### Application web

| Mode sombre | Mode clair |
|---|---|
| ![Web mode sombre](screenshots/search_doc_tool_web_dark_mode.png) | ![Web mode clair](screenshots/search_doc_tool_web_light_mode.png) |

## Fonctionnalités

- Recherche dans des fichiers `.docx` et `.pdf` (récursivement ou non)
- Syntaxe de requête avancée :
  - Mots séparés par des espaces → mode **OU** (au moins un terme)
  - Opérateur `+` → mode **ET** (tous les termes présents)
  - `"phrase exacte"` → recherche de la phrase littérale
- Recherche insensible aux accents par défaut
- Options : sensibilité à la casse, correspondance sur mot entier
- Affichage du contexte autour de chaque occurrence (terme mis en évidence)
- Numéro de page avec lien direct vers la page dans le visualiseur PDF
- Barre latérale de favoris pour les dossiers fréquents (par utilisateur, redimensionnable)
- Index SQLite FTS5 pour des recherches quasi-instantanées sur les dossiers déjà indexés
- Indexation en arrière-plan avec barre de progression et bouton d'arrêt
- Bascule thème clair/sombre

## Application web — fonctionnalités supplémentaires

- Multi-utilisateurs : authentification Django (connexion requise)
- Index partagé par dossier : un index par chemin de dossier, partagé entre tous les utilisateurs
- Conversion DOCX → PDF via LibreOffice à l'indexation
- PDF affiché en ligne avec les termes trouvés surlignés
- Statut d'indexation persisté en base de données (survit aux redémarrages serveur)

## Prérequis

- Python 3.12+
- **Application web uniquement :** LibreOffice installé (conversion DOCX → PDF à l'indexation)

## Installation et lancement

### Bureau (PyQt6)

```bash
cd desktop
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python -m search_tool
```

### Web (Django) — développement

```bash
cd web
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
cd search_tool_project
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Puis ouvrir `http://127.0.0.1:8000` dans le navigateur.

### Web (Django) — production (Waitress)

```bash
cd web/search_tool_project
python manage.py collectstatic
DJANGO_DEBUG=false python run.py --host 0.0.0.0 --port 8000
```

## Utilisation

1. Sélectionner un dossier depuis la barre latérale des favoris ou saisir/parcourir un chemin
2. Cliquer sur **Indexer** pour construire l'index FTS5 (première fois ou après ajout de fichiers)
3. Saisir un ou plusieurs termes et cliquer sur **Lancer**
4. Cliquer sur un résultat pour ouvrir le PDF à la bonne page, avec le terme surligné

## Index et stockage des données

- Index stocké par dossier dans `.data/folders/<nom_dossier>_<hash>/index.db`
- PDFs convertis mis en cache dans `.data/pdf_cache/`
- Copies DOCX (contournement lecteur réseau) dans `.data/docx_copy/`
- Statut d'indexation (heure de début, compteurs, erreurs) persisté dans la base Django

## Configuration

Le dernier dossier et le paramètre de récursivité sont sauvegardés automatiquement dans `~/.search_tool_config.json`. Les favoris sont stockés par utilisateur dans la base de données Django.
