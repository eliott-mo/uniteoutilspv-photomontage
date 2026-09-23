# BRIEF — Prototype photomontage PV (Sarnois 10A, photo IMG_6941)

## Objectif

Prototype jetable, un seul cas. Valider que la projection géométrique d'un plan BE
sur une photo terrain donne un calage crédible. Pas de Streamlit, pas de généricité :
un script Python `proto_photomontage.py` qui produit un `photomontage.html` autonome.

Périmètre volontairement exclu : masquage végétation, ombres portées, calage
colorimétrique, éclairage solaire fin. On juge la géométrie d'abord.

## Fichiers d'entrée (dossier `proto/`)

- `IMG_6941.jpeg` — photo originale iPhone 16, 2268×4032 portrait, EXIF intact
- `2026_08_025-IMP-DEV-Fixe-IND10a_V2.dxf` — plan BE, L93, mètres

## Constantes déjà vérifiées (ne pas recalculer, ne pas "corriger")

| Paramètre | Valeur | Source |
|---|---|---|
| Position caméra L93 | X = 621 980, Y = 6 954 139 | EXIF GPS (49.68153 N, 1.91953 E) |
| Altitude sol caméra | 191,3 m | point topo DXF à 5 m |
| Hauteur prise de vue | 1,60 m → Z caméra = 192,9 m | hypothèse |
| Azimut de visée (yaw initial) | 321,6° | cône GPS Map Camera |
| Focale équivalente 35 mm | 26 mm | EXIF `FocalLengthIn35mmFilm` |
| Champ horizontal (portrait) | 2·atan(12/26) = 49,6° | déduit |
| Champ vertical (portrait) | 2·atan(18/26) = 69,4° | déduit |
| Point bas table | 1,50 m | tableau bilan BE |
| Point haut table | 3,53 m | tableau bilan BE (cohérent avec ΔZ bloc = 2,02 m) |
| Soleil à l'instant de la photo | azimut 244,9°, élévation 47,6° | pvlib, 02/06/2026 16:35:25 +02:00 |

Le `DigitalZoomRatio` EXIF vaut 1,012 : négliger.

## Étape 1 — Extraction géométrie DXF (`ezdxf`)

Couche `PVcase PV Modules (full frames)` : 85 INSERT de blocs PVCase.

**Piège OCS, obligatoire** : chaque INSERT porte son propre vecteur d'extrusion
(tables suivant la pente). Les coordonnées `e.dxf.insert` brutes sont en OCS et
donnent des valeurs absurdes (X ≈ 6 070 000, Y négatif). Ne jamais les utiliser.
Passer par `e.virtual_entities()`, qui renvoie les entités résolues en WCS.

Dans chaque bloc, une entité `POLYLINE` 3D (couche `PVcase PV Modules (optimised)`)
à 4 sommets = les 4 coins de la table en L93 avec altitude. Ordre observé :
coin haut, coin haut, coin bas, coin bas (les deux premiers ont Z ≈ +2,02 m).
Ignorer les `3DSOLID` (ACIS, non lisible).

Les coins bas sont posés au niveau du sol : **ajouter +1,50 m à tous les Z**
(point bas réel). Résultat attendu : 85 quadrilatères 3D, Z entre ~192 et ~199 m,
X ∈ [621 700, 622 100], Y ∈ [6 954 300, 6 954 600].

Clôture : couche `UNI_Cloture`, une LWPOLYLINE 2D de 21 points, non fermée.
Z de chaque sommet = altitude du point topo le plus proche (couche `-TopoNiveau`,
INSERT dont `insert.z` est l'altitude ; 4 044 points). Hauteur clôture 2,00 m.

Exporter tout ça en JSON : `{"tables": [[[x,y,z],…4], …], "cloture": [[x,y,z],…]}`.
Traduire les coordonnées en **relatif caméra** (X − Xcam, Y − Ycam, Z − Zcam)
avant export, pour garder des flottants courts et éviter les problèmes de
précision en JS.

## Étape 2 — HTML autonome (`photomontage.html`)

Un seul fichier. Photo embarquée en base64, **réduite à 1 200 px de large**
(sinon fichier > 4 Mo et canvas lent). JSON géométrie inline dans un `<script id="geom">`.

Canvas superposé à la photo, même dimensions. Curseurs :

| Curseur | Plage | Pas | Initial |
|---|---|---|---|
| Azimut | 321,6 ± 15° | 0,1° | 321,6 |
| Tangage | −15° à +15° | 0,1° | 0 |
| Roulis | −5° à +5° | 0,1° | 0 |
| Focale éq. 35 mm | 20 à 32 mm | 0,1 mm | 26 |
| Hauteur caméra | 1,0 à 2,5 m | 0,05 m | 1,60 |
| Opacité | 0 à 100 % | | 60 % |

Redessin à chaque `input` (pas `change`), sans throttling : 85 quadrilatères, c'est
instantané.

**Modèle sténopé.** Repère caméra : X à droite, Y en haut, Z vers l'avant.
Conversion monde (E, N, Up) → caméra :
1. yaw : rotation autour de Up de −azimut (0° = Nord, sens horaire)
2. pitch : rotation autour de X
3. roll : rotation autour de Z

Projection : `u = cx + f_px · Xc/Zc`, `v = cy − f_px · Yc/Zc`, avec
`f_px = (largeur_image_px / 24) · focale_mm` en portrait (le côté court du capteur
35 mm, 24 mm, correspond à la largeur de l'image). Rejeter tout point avec Zc ≤ 0,5 m.

**Algorithme du peintre** : trier les quadrilatères par distance décroissante du
centroïde, dessiner du plus loin au plus près.

**Face visible.** Les modules sont orientés vers l'azimut 155,5° (SSE). La caméra
est au sud du projet et regarde vers le NW : elle voit donc la **face modules**.
Calculer néanmoins la normale de chaque quadrilatère (produit vectoriel des deux
arêtes, orientée vers le haut/SSE) et remplir en bleu nuit (#1e2a44) si elle
pointe vers la caméra, en gris structure (#7a7a72) sinon. Sur cette photo, tout
doit ressortir bleu ; un quadrilatère gris signalerait une erreur d'ordre des
sommets ou de repère. C'est un contrôle, pas du réalisme.

Hypothèse générale pour la suite de l'outil : les modules sont toujours orientés
dans le secteur SE–S–SO. La face vue dépend uniquement de la position de la caméra
par rapport à la centrale, jamais d'un paramètre saisi.

Clôture : polyligne au sol + polyligne à +2 m + un montant vertical tous les 2,5 m,
trait gris 1 px, opacité 40 %.

Repère de contrôle : dessiner la ligne d'horizon théorique (pitch/roll appliqués,
distance infinie) en pointillé jaune. Au calage, elle doit coïncider avec la
ligne de haie de la photo.

Bouton « Exporter PNG » : `canvas.toBlob` de la photo + overlay, pleine résolution
du HTML (1 200 px).

## Étape 3 — Critères de validation (à me remonter tels quels)

1. À l'ouverture, curseurs initiaux, tangage 0 : l'horizon jaune est-il à moins de
   ~5 % de hauteur de la ligne de haie ? Sinon noter l'écart en pixels.
2. Les tables apparaissent-elles dans le tiers droit de l'image, au-delà du champ
   de betteraves ? (attendu : oui, centre du projet à +21° de l'axe)
3. Après calage manuel sur les deux éoliennes de l'horizon : valeurs finales des
   5 curseurs.
4. Capture d'écran du calage final.

## Interdits

- Ne pas utiliser `e.dxf.insert` brut, ni tenter de « corriger » les OCS à la main.
- Ne pas récupérer d'altitude via API IGN : le topo est dans le DXF.
- Ne pas ajouter de dépendance Python autre que `ezdxf`, `numpy`, `pillow`.
- Ne pas ajouter de masquage, d'ombres, de textures. Prototype géométrique.
