# PASSATION — reprendre le photomontage depuis une session cloud

> Écrit le 26/09/2026, au commit `9f4b9e0`. Fichier **jetable** : il décrit un état, pas
> une règle. Le supprimer dès qu'il ne décrit plus rien.
>
> À lire d'abord : `README.md`. Cette note ne le répète pas, elle dit seulement où on en
> est et ce qui est faisable sans le poste de travail.

---

## 1. La contrainte qui décide de tout le reste

`exemples/` (2,9 Go) et `projets/` sont **exclus du dépôt**, pour de bonnes raisons écrites
en tête de `.gitignore` : ce sont des plans, des photos de visite et des dossiers de permis
d'un bureau tiers. Le dossier local pèse 3,0 Go ; **le dépôt ne porte que le code.**

Une session cloud reçoit donc le code **et rien d'autre** : pas de DXF, pas de photo, pas
de tableau bilan, pas de Blender, pas de cache IGN.

La bonne nouvelle est que le code a été écrit en le sachant. **Les 157 tests sont
synthétiques** — ils fabriquent leur géométrie au lieu de lire un plan. Le seul fichier qui
touche aux données a son garde à `test_lecture_contrat.py:30` (`skipif` sur l'existence du
contrat et du DXF) : en cloud il se saute, et le reste tourne vert.

**Donc : tout ce qui se vérifie par un test est faisable en cloud. Tout ce qui se vérifie
par un rendu ne l'est pas.** C'est la seule question à se poser avant de lancer une tâche.

## 2. Les trois dépôts, et ce qu'ils se doivent

| Dépôt | GitHub | Rôle |
|---|---|---|
| `photomontage` | `eliott-mo/uniteoutilspv-photomontage` | celui-ci : lit un plan, monte la scène 3D, rend, compose |
| `generateur-dp` | `eliott-mo/uniteoutilspv-generateur-dp` | écrit le contrat `geometries.gpkg` + `projet.json` que `lecture_contrat.py` consomme ; compose la planche DP 6 depuis les montages |
| `photos-geoloc` | `eliott-mo/uniteoutilspv-rapport-photos` | produit les cartes `Photos géolocalisées.html`, d'où viennent position et cap des prises de vue |

## 3. Où en est le travail

Le dépôt est propre et poussé. Dernier commit : **le BESS est monté** — conteneur batterie
20 pieds (6 × 3 × 3 m), bâche souple de refroidissement (11,7 × 8,9 × 1,5 m), zone de
remise en surface dure, bac de rétention volontairement non monté. Tout est expliqué dans
`ouvrages_techniques.py`, `lecture_dxf.py` et `test_bess.py`.

### Les quatre projets chargés, et pourquoi aucun n'est montable

| projet | plan | vue photomontage | ce qui bloque |
|---|---|---|---|
| 88. Auzainvilliers | DXF APS lisible, 79 tables, + bilan | 1, OK (23,3 m, 19 % cadre) | la photo d'origine |
| 34. Bédarieux | DXF ESQ lisible, 131 tables, + bilan | 1, OK (7,4 m, 62 % cadre) | photo d'origine **+ DXF périmé** (le PDF ajoute un local BESS que le DXF n'a pas) |
| 03. Gannay | HelioScope brut, entité IMAGE géoréférençable | 2 | photo d'origine + contrat `generateur-dp` lot 2 |
| 71. Saint-Aubin | HelioScope brut, entité IMAGE | 1 | photo d'origine + contrat lot 2 ; pas de bilan → gabarits |

**Le blocage est le même sur les quatre : les photos.** Les cartes HTML embarquent des
copies en 1280 × 960 (1,23 Mpx) **sans EXIF**, donc sans focale. Sans focale, il faut la
résoudre avec la pose, et les deux sont dégénérées — 6 % de focale valent 100 m de recul.
C'est là que partent les allers-retours que toute la campagne cherche à supprimer.

## 4. Ce qui est faisable en cloud, par ordre d'intérêt

### (a) `photos-geoloc`, lot A — la tâche qui débloque les quatre projets

**Le brief est déjà écrit** : `photos-geoloc/_briefs/BRIEF_export_photomontage.md`, non
commité (ce dépôt travaille par lot, c'est à sa conversation de le prendre). Il demande de
faire voyager l'optique dans le JSON de la carte : focale équivalente 35 mm, focale réelle,
dimensions **du fichier d'origine**, appareil, et le booléen « vignette GPS Map Camera ».
Format de carte 6 → 7.

C'est du code pur, testable avec des JPEG synthétiques écrits par PIL — donc parfaitement
faisable sans données. Le brief porte les numéros de ligne exacts, tous vérifiés.

### (b) Durcir ce dépôt-ci par les tests

Tout ce qui s'écrit et se vérifie en synthétique : nouvelles règles de lecture de plan,
garde-fou de prise de vue, reconstruction 3D d'un contrat plat. `test_bess.py` est le
modèle le plus récent de la forme attendue — chaque test porte la mesure qui l'a motivé.

### (c) Les points ouverts qui se raisonnent sans rendu

- `conformite.verifier` signale **30 m² de sol rendu hors polygone du plan sur 3 640** à
  Sarnois IND10b (0,8 %). Jamais expliqué. C'est probablement le débord de la
  triangulation de l'union dans `ouvrages_techniques.surfaces` — `shapely.ops.triangulate`
  travaille sur l'enveloppe convexe et on écarte les triangles dont le *centroïde* sort de
  l'union, ce qui laisse passer les triangles à cheval. Vérifiable par un test synthétique
  sur un polygone concave.
- Auzainvilliers : **12 m² de béton et 13 m² de couvertine hors enceinte** (12 % de leur
  emprise). Vérifié comme antérieur au BESS — 6 postes montés avant comme après.

## 5. Ce qui n'est PAS faisable en cloud

- **Tout rendu.** Blender n'est pas une dépendance pip, c'est écrit dans
  `requirements.txt`. Pas de rendu, pas de composition, pas de planche.
- **Tout calage.** Il faut la photo et l'outil de curseurs, et c'est de toute façon un
  geste humain — une passe par vue, que rien n'automatise.
- **`auditer_projets.py`**, qui lit `projets/`.
- **Faire tourner un plan réel** dans `lecture_dxf`. Une règle de lecture nouvelle peut
  s'écrire et se tester en synthétique, mais sa confrontation au corpus des sept plans
  devra attendre le poste de travail.

## 6. Ce qu'il ne faut surtout pas re-découvrir

Tout est écrit, et chaque piège porte la mesure qui l'a fait trouver :

- `README.md`, section **« Pièges mesurés, à ne pas réintroduire »** — la liste complète.
- `ouvrages_techniques.py`, en-tête — pourquoi un volume ne pose aucune surface, et
  pourquoi un portail est un segment de clôture.
- `tables_plates.py`, en-tête — pourquoi le sens de la pente se contraint au lieu de se
  deviner.
- `lecture_dxf.py` — les **quatre structures de plan** rencontrées, et le seuil
  `DETAIL_BLOC` qui sépare un symbole de plan d'un dessin de produit.
- `garde_prise_de_vue.py` — pourquoi un verdict sans cap porte sur la POSITION et non sur
  la photo.

Deux constantes qui reviennent sans cesse et qu'il vaut mieux avoir en tête d'emblée :
**`np.allclose` est un piège en Lambert 93** (rtol 1e-5 sur un nord de 6 750 000 vaut 67 m
— comparer en mètres, explicitement), et **un heredoc Bash de plus d'une centaine de
lignes se tronque** : écrire le fichier.

## 7. Ce qui attend une action humaine, pas une session

1. **Récupérer les JPEG d'origine** des vues marquées photomontage, pour les quatre
   projets. C'est le geste le plus rentable de tous.
2. **Demander à Bédarieux le DXF à jour**, celui qui porte le local BESS.
3. **Prendre le brief `photos-geoloc`** dans une conversation de ce dépôt, et le commiter
   là-bas.
