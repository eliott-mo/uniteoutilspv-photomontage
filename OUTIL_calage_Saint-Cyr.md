# Outil de calage par points d'appui — Saint-Cyr-en-Val

Construit le 17/09/2026. Le calage ne dépend plus d'aucune métadonnée : le chef de projet clique
le même endroit sur la photo et sur l'orthophoto, et le programme calcule la position de la caméra,
son orientation et, si les points ne sont pas tous au sol, sa focale.

## Ce qui est livré

| Fichier | Rôle |
|---|---|
| `lecture_dxf.py` | Lecture générique d'un plan PVcase, testée sur Sarnois et Saint-Cyr |
| `terrain.py` | Altitude du sol et orthophoto de l'IGN, avec cache disque |
| `solveur.py` | Calcul de pose par moindres carrés, avec écarts-types et garde-fous |
| `gabarit_vue.html` | Gabarit de l'outil : deux vues, solveur, rendu, export |
| `preparer_vue.py` | Assemble le tout en un fichier autonome par point de vue |
| `calage/calage_PV1.html` … `PV9.html` | Les neuf outils prêts à l'emploi |
| `demo_saint-cyr_PV6_rendu.jpg` | Rendu au point de vue 6 après calage |

Pour régénérer : `python preparer_vue.py`. Pour un seul point de vue : `python preparer_vue.py 6`.

## Comment on s'en sert

Ouvrir un des fichiers `calage/calage_PVn.html` dans un navigateur. Rien à installer.

1. La photo est en haut, l'orthophoto en bas. Molette pour zoomer, glisser pour déplacer.
2. Cliquer un point reconnaissable sur la photo, puis le même endroit sur la carte. Un bord de
   piste, un angle de clôture, un poteau, une intersection. Recommencer au moins trois fois,
   idéalement six, bien répartis dans le champ.
3. Pour un point qui n'est pas au sol, saisir sa hauteur dans la colonne `h`. Deux points en
   hauteur suffisent à débloquer l'ajustement de la focale.
4. Cliquer « Résoudre ». L'écart moyen s'affiche en pixels, point par point. Sous 5 pixels le
   calage est bon, au-delà de 15 il faut reprendre un point.
5. Ajuster éventuellement à la main avec les curseurs, puis exporter le PNG.

Le nombre de degrés de liberté est affiché. À zéro, l'écart nul ne prouve rien : il faut plus de points.

## Ce que le solveur calcule

Position est et nord, hauteur de l'œil, azimut, tangage, roulis, et la focale en option. Le point
de départ vient du GPS de la photo, de l'orientation cardinale notée par le bureau d'études et de
la focale EXIF. L'altitude du sol vient du modèle de terrain de l'IGN, jamais du GPS du téléphone.

**Garde-fou important.** Si tous les points d'appui sont au sol et le terrain plat, la focale ne se
sépare pas du tangage et de la hauteur. Le solveur refuse alors de l'ajuster et le dit. C'est le
même piège que sur Sarnois, où deux éoliennes trop proches l'une de l'autre ne séparaient pas
l'azimut de la focale.

## Validation

**Solveur, cas synthétiques.** Pose connue, points projetés, bruit ajouté, départ volontairement
faux de 8 m et 20°. Sur 20 tirages à chaque configuration :

| Points | Bruit | Poses retrouvées à moins de 3 m et 1° |
|---|---|---|
| 4 | 0 px | 20 / 20 |
| 6 | 2 px | 20 / 20 |
| 10 | 2 px | 20 / 20 |
| 20 | 5 px | 20 / 20 |

Sur un cas détaillé à 8 points et 2 px de bruit : position à 0,2 m, azimut à 0,04°, tangage à
0,04°, roulis à 0,03°, tous dans leurs écarts-types calculés.

**Focale.** Refusée quand tous les points sont au sol. Avec des points en hauteur, retrouvée à
0,2 % (2 613 px pour 2 607 vrais, en partant de 2 400).

**Le solveur du navigateur contre celui de Python.** Deux implémentations écrites séparément, une
en JavaScript avec Levenberg-Marquardt et élimination de Gauss, l'autre en Python avec scipy. Sur
des données identiques elles convergent au même minimum : 0,2 mm sur la position, un millionième
de degré sur les angles, 0,0004 px sur la focale. Le modèle et le solveur du gabarit sont
verrouillés par empreinte, un test exige de rejouer la comparaison s'ils changent.

**Parcours complet dans l'interface.** Sept points placés, écart moyen de 226 px avant calage,
1,5 px après, en 12 ms. Pose retrouvée à 0,7 m et 0,26°.

La suite de tests compte 49 cas : `python -m pytest test_geometrie.py -v`.

## Ce que le matériel de Saint-Cyr apporte

Les photos d'Evinerude sont bien meilleures que celle de Sarnois : Samsung Galaxy A55,
4080 × 3060 en format natif non rogné, 23 mm équivalent soit 76° de champ, GPS sur les neuf.
Le shapefile donne la position, l'altitude et une orientation cardinale.

Deux pièges confirmés au passage.

- **L'altitude du shapefile est fausse.** Elle vaut 125 à 140 m alors que le terrain est plat à
  95 m. C'est l'altitude GPS du téléphone, ellipsoïdale et bruitée. L'outil prend celle de l'IGN.
- **Le point bas des tables se mesure, il ne se suppose pas.** Ici 1,72 m au-dessus du sol, contre
  1,50 m à Sarnois. Appliquer une valeur par défaut aurait décalé tout le rendu.

Le plan range aussi les tables différemment de Sarnois, en polylignes directes au lieu de blocs.
La lecture gère les deux.

## Distances des neuf points de vue

| Point de vue | Au centre du projet | À la table la plus proche | |
|---|---|---|---|
| 1 et 2 | 131 m | 18 m | hors emprise |
| 3 | 115 m | 27 m | dans l'emprise |
| 4 et 5 | 171 m | 21 m | hors emprise |
| 6 | 149 m | 10 m | hors emprise |
| 7 | 88 m | 13 m | dans l'emprise |
| 8 et 9 | 526 et 532 m | 388 m | hors emprise |

Sept des neuf points de vue sont à moins de 30 m de la première rangée. Le rendu y montre donc un
mur de modules, ce qui est géométriquement exact mais peu représentatif. Les points 8 et 9, à plus
de 500 m, donnent la vue lointaine classique d'un photomontage. Ce sont deux usages différents et
il serait utile d'en discuter avec le bureau d'études au moment de choisir les points de vue.

## Rendu (repris le 17/09/2026)

Le premier rendu était un aplat bleu uniforme, illisible. Il a été refait :

- **Soleil réel** calculé avec pvlib à partir de la date, de l'heure et du GPS de la photo.
  Saint-Cyr le 09/12/2025 : azimut 148 à 205°, hauteur 13 à 16°.
- **Verre photovoltaïque** : sombre vu de face, miroir du ciel en incidence rasante, selon la
  réflectance de Fresnel. C'est ce qui donne aux rangées leur variation de ton.
- **Couleur du ciel prise sur la photo elle-même**, en détectant les lignes réellement de ciel.
  La lumière du rendu suit donc celle de l'image, sans réglage.
- **Brume de distance** réglable, exprimée en atténuation à 1 km pour être lisible.
- **Découpe des modules** tant qu'elle reste visible, arête haute claire, arêtes basses sombres.
- **Pieds de structure** seulement quand leur écartement projeté dépasse quelques pixels, sinon
  ils formaient un peigne au loin. Même règle pour les poteaux de clôture.

Voir `comparaison_rendu_avant_apres.jpg`, sur la photo de Sarnois dont le calage est validé.

## Sarnois : la photo ne correspond pas au plan du brief

Vérification du 17/09/2026, déclenchée par une remarque d'Eliott sur le rendu.

| | IND10A (plan du brief) | IND10B |
|---|---|---|
| Clôture la plus proche | 187 m | **4 m** |
| Première table | 216 m | **19 m** |
| Position de la caméra | au sud, centrale au nord | **à l'angle est de l'emprise** |

La photo IMG_6941 est celle du site **IND10B**. Tout le travail de calage de Sarnois avait été
fait sur le plan de la variante A, qui n'est pas celle que montre la photo. Le plan 10B est
maintenant dans `exemples/sarnois-B/`, l'outil dans `calage_sarnois_B/`.

Même avec la bonne variante, la caméra vise le long de la limite nord-est de l'emprise (336,5°)
et non vers l'intérieur. Sur un champ de 39,4°, seules 23 des 90 tables entrent dans l'image, à
52 à 205 m, sur le tiers gauche. Les 67 autres, dont les plus proches, sont hors cadre à gauche.
Le point de clôture le plus proche, à 4 m, est à l'azimut 266°, soit 70° à gauche de l'axe.

**Leçon de méthode** : avant de caler, vérifier que l'emprise du plan est cohérente avec ce que
montre la photo. Distance à la clôture, parcelles concernées, présence d'une piste au premier
plan. Un calage géométriquement impeccable sur le mauvais plan reste faux.

## Masquage par la végétation (ajouté le 17/09/2026)

C'était le défaut qui faisait « léviter » le projet. Un calque de masquage a été ajouté.

- **Pinceau** et **gomme** à rayon et adoucissement réglables, pour peindre sur la photo les haies,
  arbres et buissons qui passent devant le projet.
- **Sous un trait** : on clique le haut d'une haie, tout ce qui est dessous est masqué d'un coup.
  C'est le geste le plus rapide sur une lisière.
- **Distance de la végétation** : seul ce qui est plus loin que cette distance est caché. Les tables
  situées en avant restent visibles. Sur Sarnois 10B, la haie est à 97 m et les tables visibles
  s'échelonnent de 52 à 205 m : les premières passent devant, les autres derrière.
- La clôture est filtrée segment par segment, sinon une haie lointaine effaçait la clôture entière,
  y compris sa partie à 4 m de l'objectif.
- L'export PNG applique le masque.

Voir `comparaison_masquage.jpg` et `demo_sarnois_10B_rendu.jpg`.

## Limites connues

- Le masquage est manuel. Une aide automatique par segmentation reste à faire, mais elle demande
  soit un modèle local, soit un service en ligne.
- Une seule distance de masquage par vue. Deux haies à des distances différentes demanderaient
  plusieurs calques.
- Pas d'ombres portées au sol, pas de texture d'herbe entre les rangées.
- OneDrive injecte des métadonnées SharePoint dans les fichiers HTML d'un dossier synchronisé.
  Le générateur les retire à chaque production.
- Le calage réel des neuf photos n'est pas fait. Il demande de reconnaître les détails du terrain,
  ce qui relève de quelqu'un qui y est allé. La mécanique, elle, est vérifiée.
- Générer ces fichiers de 2 à 3 Mo plusieurs fois de suite dans un dossier OneDrive provoque des
  conflits de synchronisation et peut corrompre les fichiers. Le script relit ce qu'il écrit et
  refuse de continuer si le fichier est abîmé. En cas de mise au point répétée, passer un dossier
  de sortie local en argument.
