# Note — photomontage d'un dossier HelioScope + plan PDF (lot 2ter)

Rédigée le 24/09/2026 depuis la conversation du lot 2ter de `generateur-dp`
(commit `55c4b73`). Tout ce qui suit a été mesuré ce jour-là. Ce dépôt n'a pas
été modifié, à part l'ajout de cette note.

## En bref

- **Le lot 2ter ne produit pas de DXF.** Il écrit le contrat commun à tous les
  imports de `generateur-dp` : `geometries.gpkg` et `projet.json`, version 2,
  en Lambert 93, `origine: "plan_pdf"`. Tout ce que le montage reprojette s'y
  trouve : les tables HelioScope et les éléments lus sur le plan PDF.
- **`lecture_contrat.lire` refuse aujourd'hui ces contrats** avec
  `ErreurAltitudeAbsente` : une sortie de Gannay (lot 2ter) et
  `generateur-dp/sortie/ABO_55_Les-Islettes` (lot 2, HelioScope seul) butent
  au même endroit. Un export HelioScope est plat, ses tables n'ont pas de Z.
  Un DXF n'y changerait rien : `lecture_dxf` exige aussi des polylignes 3D.
- **Proposition** : quand le contrat est plat, reconstruire les tables en 3D
  ici, avec `terrain.py` et les paramètres de `projet.json`. Le contrat du
  générateur ne change pas, ni le lot 4 qui le lit.

## Ce que le contrat donne — Gannay-sur-Loire, lot 2ter

Toutes les couches sont en EPSG:2154, en deux dimensions, avec les colonnes
`calque` (libellé de légende du plan), `categorie`, `z_reel` (faux), `z_min`
et `z_max` (nuls).

| Couche | Entités | Contenu | Lu ici comme |
| --- | --- | --- | --- |
| `tables_pv` | 16 polygones | les **rangées** (tables réunies), pas les 264 tables | tables : refusé, pas de Z |
| `modules_pv` | 4 752 polygones | l'empreinte au sol de chaque module | écarté (« trop fin ») |
| `cloture` | 1 polygone | l'enceinte fermée | `cloture` |
| `portail` | 5 lignes | **un** portail : ouverture, deux vantaux, deux arcs | `portail` |
| `piste_lourde_existante`, `piste_lourde_a_creer` | 5 polygones | bandes de 5 m, virages de 11 m de rayon intérieur | `piste` (« lourde » trouvé par `SOL_TEINTES`) |
| `pdl_ptr`, `ptr` | 2 polygones | rectangles aux cotes du catalogue UNITe, orientés comme au plan | `pdl` |
| `bache_incendie` | 2 polygones | réserve incendie, calque « Réserve Incendie » | `sdis` |
| `local_technique` | 1 polygone | idem | `local` |
| `bess`, `bac_retention` | 1 + 1 | idem | écartés, et signalés comme tels |
| `haie` | 3 lignes | axes des haies à créer ou renforcer | `haie` |
| `zone_implantation_pv`, `recul_implantation`, `zone_evitee`, `ligne_coupe` | — | limites d'étude, coupe DP 3 | écartés |

Dans `projet.json` :

- `parametres.modules` : module de 1,134 × 2,382 m, inclinaison 15°, pose
  portrait, longueur projetée au sol 2,301 m.
- `parametres.structures` : 18 modules par table, 264 tables ;
  `point_bas_m` 1,1 et `point_haut_m` 3,0. Ce sont les valeurs lues au tableau
  du plan quand il en a un, sinon le standard UNITe. Celui de Gannay n'en a pas ;
  celui de Bray porte « 1,1 mètres min » et « 3 mètres max ».
  **Pas de `format_table`.**
- `parametres.generalites` : rangées à 0,436° en Lambert 93, 16 rangées au pas
  de 10,93 m, tables au pas de 7,37 m.
- `cotes_normalisees` : dimensions et hauteur des postes du catalogue, avec
  `ordre_cotes` (PDL/PTR 12 × 3 × 3 m, PTR 10 × 3 × 3 m…).

## Les trois écarts avec un contrat du plan BE

1. **Pas d'altitude.** Le plan du BE porte des tables 3D, dont le Z donne
   l'inclinaison ; l'export HelioScope est plat.
2. **Des rangées, pas des tables.** Pour HelioScope, `tables_pv` reçoit les
   rangées : c'est sur elles que se lit l'azimut de la coupe DP 3 (décision du
   03/09/2026). Les tables séparées ne se trouvent que dans `modules_pv`. À
   Gannay, une table fait 18 modules, 6 d'est en ouest sur 3 en profondeur,
   soit 6,87 × 6,93 m au sol. Les modules sont séparés par des joints de 1,2 cm,
   les tables de 0,49 m.
3. **Pas de `format_table`** : `_attribuer_formats` ne fait rien. Le découpage
   en rangs et colonnes se lit sur les modules.

## Proposition

1. **Brancher `lecture_contrat`** dans `app.py`, `montage.py` et
   `preparer_vue.py`, qui lisent encore le DXF dans l'arbre de travail du
   24/09/2026.
2. **Si le contrat est plat** (`origine` à `helioscope` ou `plan_pdf`, `z_reel`
   faux), reconstruire les tables au lieu de lever :
   - **Tables** : regrouper `modules_pv` par contiguïté. Les joints de 1,2 cm
     et les écarts de 0,49 m entre tables les séparent sans ambiguïté. Ne pas
     se fier à l'ordre des entités, que le contrat ne garantit pas.
   - **Sens de la pente** : bord bas au sud. Sur Gannay et les deux designs des
     Islettes, le bloc module HelioScope descend vers −y, le sud du repère DXF,
     nord en haut. À Gannay, il descend de 0,617 m sur 2,301 m. Le contrat ne
     le dit pas explicitement : voir « Ce que le générateur peut ajouter ».
   - **Altitudes** : le sol au RGE ALTI (`terrain.py`) aux coins de chaque
     table. Le bord bas est à sol + `point_bas_m`. Le bord haut est au bord bas
     + profondeur projetée × tan(inclinaison), soit 3 × 2,301 × tan 15° =
     1,85 m à Gannay. Il arrive ainsi à 2,95 m, sous les 3,0 m de
     `point_haut_m`. Signaler un bord haut qui dépasserait `point_haut_m`.
3. **À vérifier au premier montage** :
   - le portail compte cinq entités : il ne doit pas en naître cinq portails ;
   - le BESS et le bac de rétention restent écartés ;
   - le calque « Réserve Incendie » ne contient pas « bache », donc
     `SOL_TEINTES` lui donne la teinte par défaut ;
   - la précision : les tables sont celles d'HelioScope, placées par le calage
     du dossier. Ce calage est à moins d'un mètre si le chef de projet a utilisé
     « Caler sur l'ortho », sinon il vaut ce que vaut son réglage à l'œil. Le
     reste vient du plan PDF calé sur ces tables, avec les ouvrages aux cotes
     du catalogue.

## Ce que le générateur peut ajouter si le photomontage en a besoin

- **Le sens de la pente**, par exemple l'azimut vers lequel les modules
  descendent, dans `projet.json`. Il ne s'écrit aujourd'hui nulle part.
- **Une couche des tables HelioScope séparées**, si le regroupement des modules
  s'avère fragile.

Ces deux demandes se traitent dans une conversation neuve de `generateur-dp`.
Toute couche ou colonne ajoutée l'est pour les trois producteurs à la fois :
le test `test_les_trois_producteurs_ecrivent_le_meme_schema` y veille.

## Produire un contrat d'essai

Deux contrats plats sont disponibles.

Celui de **Gannay (lot 2ter)** se produit depuis ce dépôt, sans l'application.
L'extrait a été vérifié le 24/09/2026 ; il écrit `geometries.gpkg` et
`projet.json` en une dizaine de secondes :

```python
import sys
sys.path.insert(0, r"..\generateur-dp")
from dp_socle.coupe import coupe_par_defaut
from dp_socle.plan_pdf import ChoixDuPlan, importer_plan_pdf
from tests.jeux_plan_pdf import EXPORT_GANNAY, LONGITUDE_GANNAY, NORD_SUD_GANNAY_M, PLAN_GANNAY

r = importer_plan_pdf(
    PLAN_GANNAY, EXPORT_GANNAY,
    longitude_origine=LONGITUDE_GANNAY, correction_nord_sud_m=NORD_SUD_GANNAY_M,
    choix=ChoixDuPlan(volume_citerne_m3=120, largeur_portail_m=7.0),
)
r.ligne_coupe = coupe_par_defaut(r.plan.azimut_tables_deg, r.plan.polygone_cloture, r.plan.tables)
r.ecrire("contrat_gannay")
```

Celui des **Islettes (lot 2)** est déjà écrit :
`generateur-dp/sortie/ABO_55_Les-Islettes`.

Sous Windows, préfixer la commande par `PYTHONIOENCODING=utf-8`.
