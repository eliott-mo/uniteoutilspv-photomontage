# Résultats — Prototype photomontage PV (Sarnois 10A, IMG_6941)

Validation du 07/09/2026. Fichiers d'entrée dans `exemples/sarnois-A/`.
Repère pixel : image embarquée en pleine résolution, 2 268 × 4 032 px.

## Livrables

| Fichier | Contenu |
|---|---|
| `proto_photomontage.py` | Script unique : extraction DXF (ezdxf) + photo + génération HTML |
| `photomontage.html` | Fichier autonome (2,9 Mo) : curseurs, couches, plan en encart, zoom, loupe vectorielle, export PNG |
| `geom.json` | Géométrie relative caméra : 85 tables, clôture, haie projetée, 12 pistes, 11 zones VRD, 2 repères |
| `photomontage_calage_final.png` | Rendu pleine résolution au calage final |
| `photomontage_calage_final_bande.jpg` | Bande du projet (v 1 380–1 660) à l'échelle 1 |
| `photomontage_calage_final_bande_gauche_x2.jpg`, `…_droite_x2.jpg` | Même bande agrandie 2×, moitié gauche et droite |
| `photomontage_plan_cone.png` | Plan L93 avec le cône de vue au calage |
| `photomontage_loupe_x4.jpg` | Loupe 4× sur une rangée (modules, pieds, clôture, piste) |
| `photomontage_etat_initial.png` | Rendu avec les curseurs initiaux du brief |

Exécution : `python proto_photomontage.py` puis ouvrir `photomontage.html`.

## Ce que dessine le HTML

- **Tables** : face modules bleu nuit (gris si face structure), contour, arête haute claire,
  lignes de colonnes (26 ou 13 modules selon le bloc PVcase) et ligne médiane (2 rangées portrait).
  Éclaircissement léger avec la distance pour distinguer les rangées.
- **Structure** (indicatif) : pieds avant sous le bord bas (1,50 m) et pieds arrière sous le bord haut
  (3,52 m), un couple tous les ~5 m.
- **Clôture** : poteau tous les 2,5 m, fil haut à 2 m, fil intermédiaire, ligne au sol.
- **Haie projetée** (couche `UNI_Haies`, désactivée par défaut car elle masque la clôture) : bande de 2 m.
- **Pistes** lourdes et légères, **zones techniques** (plateformes, voirie, PDL, local, base vie, stockage) :
  polygones au sol, Z par point topo le plus proche.
- **Tri en profondeur** de toutes les tables, panneaux de clôture et segments de haie.
- Ligne d'horizon, repères éoliennes, plan en encart avec le cône de vue, zoom d'affichage 100–400 %,
  loupe 3× à 8× redessinée en vectoriel, lecture souris (pixel, distance au sol plat, azimut, L93).

## Correction du 14/09/2026 : le « +1,50 m » du brief était en double

Le brief demandait d'ajouter 1,50 m aux Z du DXF (coins bas supposés au sol). Vérification sur la
topo : les coins bas du DXF V2 sont déjà à 1,500 m (± 0,006 m) au-dessus du TIN des 4 044 points
topo, et les coins hauts à 3,48 m. PVcase exporte donc les tables déjà rehaussées. Les rendus du
07/09 dessinaient les tables 1,5 m trop haut (16 à 24 px). Le script mesure désormais l'écart
coins bas / sol et n'ajoute que le complément (0 m ici). Emprise des tables au calage final :
v ∈ [1 501, 1 575] au lieu de [1 482, 1 552]. Les autres chiffres ci-dessous sont mis à jour.

## Étape 1 — Extraction DXF : conforme au brief, sauf le point bas

- 85 quadrilatères via `virtual_entities()`, X ∈ [621 760, 622 013], Y ∈ [6 954 341, 6 954 527],
  Z ∈ [190,8, 196,8] m (point bas à 1,50 m du sol, sans rehausse supplémentaire). Blocs 2P26 et 2P13.
- Largeur de table le long de la pente 4,784 m. 15 rangées au pas de 10,33 m (± 0,02 m) mesuré
  sur le DXF, avec trois écarts plus grands (12,1 et 14,5 m) là où passe une piste.
- ΔZ haut–bas = 2,022 m sur les 85 tables. Normale modules : azimut 153,9°, inclinaison 25,0°.
- Centre projet à 300 m, azimut 343,1° (+21,5° de l'axe 321,6°).
- Clôture : 21 sommets, 187 à 407 m de la caméra, Z ∈ [189,4, 192,8] m.
- Point topo le plus proche de la caméra : 4,7 m, Z = 191,30 m (identique au brief).

## Étape 3 — Critères de validation

### 1. Horizon jaune vs ligne de haie à l'ouverture (tangage 0)

**Non.** Horizon jaune à v = 2 016 px (50,0 %), ligne de haie à v ≈ 1 545 px (38,3 %).
Écart : **471 px, soit 11,7 % de la hauteur**. La caméra était inclinée vers le bas d'environ 8,5°.

### 2. Tables dans le tiers droit, au-delà du champ de betteraves

**Partiellement, et seulement avec l'azimut du brief.**

- Curseurs initiaux : emprise tables u ∈ [967, 3 679] px (à partir de 43 % de la largeur, débordant
  à droite), v ∈ [1 972, 2 024], c'est-à-dire au milieu du champ de betteraves faute de tangage.
- Après calage sur les éoliennes : u ∈ [44, 3 062], **les tables occupent toute la largeur**,
  centre projet vers 66 % de la largeur, v ∈ [1 501, 1 575] soit à cheval sur la ligne de haie.
  Elles sont bien au-delà du champ de betteraves : la clôture sud (187–230 m) longe le bord du champ,
  les rangées sont derrière.

### 3. Valeurs finales après calage sur les deux éoliennes

| Curseur | Valeur finale | Initial |
|---|---|---|
| Azimut | **336,5°** | 321,6° |
| Tangage | **−8,5°** | 0° |
| Roulis | **0,0°** | 0° |
| Focale éq. 35 mm | **33,5 mm** | 26 mm |
| Hauteur caméra | **1,60 m** | 1,60 m |

Éoliennes identifiées dans OpenStreetMap : nœuds 7595939636 (L93 621 646 / 6 955 615, 1 513 m,
azimut 347,3°) et 7595939637 (621 732 / 6 956 035, 1 913 m, azimut 352,5°). Le rapport des tailles
apparentes (1,26) égale le rapport des distances. Au calage, les repères tombent sur les mâts
à 2–3 px près (repère 1 200 px) et l'horizon jaune est sur la ligne de haie. Le profil topo dans
l'axe (crête à 193,3 m vers 325 m, sol à 190–192 m au-delà) confirme que la ligne de haie est à
moins de 0,2° de l'horizon vrai.

### 4. Capture du calage final

`photomontage_calage_final.png` et les bandes agrandies.

## Pourquoi le projet ressemble à un « mur » depuis ce point de vue

Depuis 1,60 m de haut à 200–400 m, le bord bas des tables (1,50 m) est à hauteur d'œil et le bord
haut (3,52 m) à 0,5° au-dessus. Le pas entre rangées (~6 m) ne fait dépasser chaque rangée que d'environ
1 px au-dessus de la précédente (terrain montant de 0,12 m par rangée). L'ensemble des 85 tables tient
donc dans une bande de 70 px de haut sur 4 032, où la rangée de tête cache presque tout le reste.
C'est la géométrie réelle, pas un défaut de projection. Pour lire la disposition des tables depuis la
photo, il faut un point de vue plus haut ou plus proche ; en attendant, le plan en encart montre la
disposition et le cône de vue, et la loupe permet de vérifier la géométrie rangée par rangée.

## Deux constats à remonter (constantes du brief non modifiées)

1. **Photo rognée en 9:16 par GPS Map Camera.** 2 268 × 4 032 = 9:16, alors que le capteur sort du 3:4
   (3 024 × 4 032). La règle « 24 mm = largeur » donne f = 2 457 px ; les éoliennes imposent
   f ≈ 3 166 px, soit 33,5 mm dans la convention du brief. Curseur focale élargi à 20–40 mm.
   Pour l'outil futur : détecter le rognage par le ratio d'image et calculer f_px sur le côté non rogné.
2. **Azimut GPS Map Camera faux de ~15°** (321,6° → 336,5°). Aucune éolienne dans OSM à 332–337° à
   moins de 15 km, et la taille apparente impose 1,5–2 km. Curseur azimut élargi à ±20°.
   Le centre du projet est à +6,6° de l'axe, pas +21°.

## Contrôles internes

- 85 tables bleues, 0 grise, 0 rejetée à tous les réglages testés.
- Aucune erreur console. Redessin instantané à chaque `input` (canvas 2 268 × 4 032).
- L'export PNG redessine l'overlay à l'échelle 1 (traits fins), indépendamment du zoom d'affichage.
