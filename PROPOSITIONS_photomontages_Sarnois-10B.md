# Points de vue proposés — Sarnois IND10B

Établi le 17/09/2026 à partir du plan seul, sans photo. Le but est de savoir où aller et dans
quelle direction viser avant de se déplacer.

Produit par `python proposer_vues.py`. Résultats dans `propositions_sarnois-B/`.

## Ce que contient le plan comme éléments techniques

La quasi-totalité des équipements est groupée à l'entrée sud du site, sur une bande de 60 m.

| Élément | Emprise | Hauteur retenue | Position L93 |
|---|---|---|---|
| Portail et zone de contention | 8,0 × 10,7 m | 2,0 m | 621 874, 6 954 036 |
| Poste de transformation | 10,7 × 13,9 m | 2,6 m | 621 874, 6 954 065 |
| Batteries BESS et zone de remise | 18,9 × 20,3 m | 2,9 m | 621 893, 6 954 073 |
| Citerne incendie 120 m³ | 16,0 × 11,3 m | 2,5 m | 621 917, 6 954 088 |
| Local de stockage | 6,6 × 4,3 m | 3,0 m | 621 846, 6 954 079 |
| Base vie | 39,4 × 34,3 m | 3,0 m | 621 833, 6 954 332 |
| Bac d'équarrissage | 6,6 × 6,6 m | 1,5 m | 621 767, 6 954 293 |

S'y ajoutent 13 pistes lourdes et légères, 2 plateformes, 5 aires SDIS dont l'aire d'aspiration,
2 aires de grutage, 3 tronçons de voirie et 2 portails de paddock.

## Les sept points de vue

Chaque position est sur une route ou un chemin d'OpenStreetMap, donc accessible. La taille
apparente vise environ 12°, c'est-à-dire un élément occupant à peu près un sixième d'un cadre de
téléphone en paysage. Un cadrage plus serré perd le contexte, plus large rend l'équipement illisible.

| # | Élément visé | Position L93 | GPS | Azimut | Distance | Taille apparente | Tables dans le champ | Accès |
|---|---|---|---|---|---|---|---|---|
| 1 | Portail et zone de contention | 621 841, 6 954 003 | 49.68029, 1.91763 | 45° (NE) | 46 m | 13,1° | 43 | chemin |
| 2 | Poste de transformation | 621 872, 6 953 967 | 49.67996, 1.91807 | 1° (N) | 98 m | 8,1° | 90 | route |
| 3 | Batteries BESS | 621 794, 6 954 000 | 49.68025, 1.91698 | 54° (NE) | 123 m | 9,4° | 53 | chemin |
| 4 | Citerne incendie 120 m³ | 621 886, 6 954 030 | 49.68053, 1.91825 | 29° (NNE) | 66 m | 13,8° | 46 | chemin |
| 5 | Base vie | 621 679, 6 954 431 | 49.68412, 1.91531 | 123° (ESE) | 184 m | 12,2° | 90 | route |
| 6 | Bac d'équarrissage | 621 729, 6 954 335 | 49.68325, 1.91602 | 138° (SE) | 56 m | 6,8° | 90 | route |
| 7 | Local de stockage | 621 808, 6 954 122 | 49.68135, 1.91715 | 139° (SE) | 57 m | 6,5° | 6 | route |

Le point 7 est le plus faible : six tables seulement dans le champ, contre 43 à 90 ailleurs.
Il montre le local de stockage de près mais donne peu de contexte.

Carte : `propositions_sarnois-B/carte_points_de_vue.jpg`.
Aperçus : `propositions_sarnois-B/planche_apercus.jpg` et les sept fichiers `vue_*.jpg`.

## Comment lire ces propositions

Les points 1, 2, 3, 4 et 7 regardent tous le même groupe d'équipements, depuis le sud, le
sud-ouest et l'est. C'est voulu : un dossier retient en général trois à cinq vues, et ces
orientations différentes montrent l'entrée sous plusieurs angles avec la centrale derrière.
Les points 5 et 6 couvrent la partie nord, base vie et bac d'équarrissage.

Le point 2 est le plus complet : à 98 m depuis la route, vers le nord, il montre le poste de
transformation avec les 90 tables dans le champ. C'est le candidat naturel pour la vue
principale du dossier.

Le calcul écarte les positions d'où la centrale s'interpose entre l'œil et l'équipement, celles
où moins de cinq tables sont visibles, et pénalise le contre-jour en supposant un soleil au sud
vers le milieu de journée.

## Ce que ces aperçus ne sont pas

Ce sont des rendus du plan sur un fond de ciel et de sol uniformes. Il n'y a pas de photo, donc
pas de végétation existante, pas de bâti, pas de relief visible. Un chemin peut être bordé d'une
haie qui masque tout : l'aperçu ne le dira pas. Ils servent à préparer la sortie, pas à juger le
résultat.

Ce ne sont surtout pas des photos à choisir. Aucune photo de Sarnois ne couvre ces sept
directions : les deux clichés existants regardent l'est et le nord depuis l'angle sud-est. La
planche dit où se rendre et dans quelle direction viser, pour rapporter les photos qui manquent.

**Correction du 17/09 (élément visé au mauvais endroit).** La couche `UNI_SDIS_Bache_incendie`
porte deux objets éloignés de 70 m : le bloc `CIT_RIGID_120m3` de la citerne, à
621 917 / 6 954 088, et un contour d'aire plus au sud-ouest. Le filtre de points aberrants
posé la veille en retenait un au hasard, et c'est le mauvais qui l'emportait : la vue 4 visait
un point vide à 70 m de la citerne. Les points sont maintenant séparés en amas et les blocs
priment sur les contours de zone. Cela corrige aussi le portail, réduit à sa seule grille
(4,2 m) au lieu de la zone de contention (10,7 m), et fait porter la base vie sur ses bâtiments
plutôt que sur son emprise VRD. Les vues 1, 4, 5 et 7 ont changé de position.

**Correction du 17/09 (lévitation sur les vues 3, 4 et 5).** Le fond basculait du ciel au sol au
milieu de l'image, alors que la ligne d'horizon de la caméra, avec un tangage de −1,5°, remonte
de 30 px. Tout élément au-delà de 60 m posait donc le pied sur du ciel : 22 px d'écart pour la
base vie à 219 m, 16 px pour la citerne à 127 m, 0 px pour le portail à 45 m — ce qui explique
que seules les vues lointaines flottaient. Le fond bascule maintenant sur l'horizon réel. Au
passage, le pied d'un élément suit le terrain point par point au lieu d'une altitude unique
prise au centre, ce qui valait 0,70 m de dénivelé sous la base vie.

Deux vérifications à faire sur place : que le point est bien accessible, et que la vue n'est pas
fermée par une haie ou un talus. L'orthophoto de la carte donne déjà une idée des haies.

## Sur les photos existantes de Sarnois

Deux photos exploitables ont été retrouvées, toutes deux du 02/06/2026.

- **IMG_6941**, celle déjà calée. Prise à l'angle est, elle montre la limite depuis le chemin.
- **IMG_6942**, prise 2 minutes plus tard à 25 m de là. 5 712 × 4 284 en format natif non rogné,
  champ de 69°. Elle regarde vers le nord, donc pas vers la centrale, mais elle a servi à trancher
  une question restée ouverte.

Les quatre fichiers du dossier `DP_7` sont des vignettes de 320 pixels, inutilisables.

## Question de focale enfin tranchée

L'audit du 16/09 laissait la focale indéterminée entre 2 900 et 3 300 pixels, faute de repères
assez écartés. IMG_6942 montre quatre éoliennes réparties sur 1 300 pixels. Deux d'entre elles
ont pu être mesurées proprement, sur des mâts non masqués par une pale.

| | Valeur |
|---|---|
| Règle EXIF sur photo non rognée | 4 125 px |
| Mesurée sur les éoliennes | 4 130 px |
| Écart | +0,1 % |

**La focale EXIF est donc exacte tant que la photo n'est pas rognée.** Les positions prédites
pour les deux autres éoliennes tombent à 3 et 30 pixels des positions mesurées, ce qui confirme
la solution. Conséquence pratique : sur une photo au format natif, on peut fixer la focale et ne
résoudre que la pose, ce qui demande moins de points d'appui.

Pour IMG_6941, rognée en 9:16 par GPS Map Camera, la règle donne 2 912 px alors que la mesure
donne 3 071 px. L'écart de 5 % reste inexpliqué et justifie de laisser la focale ajustable sur
les photos rognées.

## Photos du reportage paysager du BE — ajout du 17/09

L'étude d'impact Antea `A135824 - Etude d'impact - Sarnois_v0 draft.docx` contient un
reportage paysager de 20 prises de vue, localisées sur sa figure 45. Les photos sont
récupérables dans le fichier Word.

Sur les vingt, douze portent la mention « le site n'est pas visible » : tout l'environnement
intermédiaire et éloigné est masqué par les haies, le bâti et les boisements. Restent huit
vues où le site apparaît, dont deux seulement où il occupe le premier plan :

| Photo | Sujet | Taille | Position estimée |
|---|---|---|---|
| 9 | Partie sud depuis l'accès au sud-ouest | 679 × 509 | 621 878, 6 954 005 |
| 10 | Partie sud depuis le chemin longeant le site à l'ouest | 752 × 565 | 621 786, 6 954 155 |

Les positions viennent de la figure 45, calée sur la pointe sud du parc. Pour la photo 10,
le chemin OSM le plus proche tombe à 11 m de cette estimation, ce qui la confirme.

Outils de calage produits : `calage_sarnois_BE/calage_PV9.html` et `calage_PV10.html`,
par `python preparer_vue.py sarnois-be`.

**Trois limites à connaître avant de s'en servir.**

1. Word a recompressé les images : 0,35 et 0,42 Mpx. Cela suffit pour une planche de
   travail, pas pour une pièce de dossier. Les originaux sont chez le BE.
2. L'EXIF a disparu : ni focale, ni GPS, ni date. La focale doit donc être résolue en même
   temps que la pose, ce qui exige deux points d'appui en hauteur et non au sol seul.
   Les éoliennes visibles à l'horizon sur les deux photos conviennent.
3. Sans date ni heure, la position du soleil est inconnue, donc pas d'ombres cohérentes.
   Les ombres portées au sol dans les photos donnent l'azimut solaire à l'œil.

## Calage des photos 9 et 10 — 18/09

Photomontages : `montage_PV9.jpg`, `montage_PV10.jpg`, avec les planches
`comparaison_PV9.jpg` et `comparaison_PV10.jpg`. Poses dans `pose_PV9.json` et
`pose_PV10.json`. Outils : `calage_paysage.py` pour la pose, `montage.py` pour le rendu.

Sans EXIF, la pose se résout sur deux signaux du paysage.

**Les mâts d'éoliennes** donnent l'azimut et la focale. Les 91 éoliennes dans 12 km viennent
d'OpenStreetMap. Trois mâts pour deux inconnues, cela laisse 3 487 solutions numériquement
bonnes et géométriquement absurdes : sur la photo 9, la meilleure plaçait les éoliennes à
3,7 km avec un champ de 105°. **C'est la taille apparente qui tranche.** Une éolienne à la
distance d doit voir sa hauteur de moyeu au-dessus de l'horizon varier comme 1/d ; le produit
doit rester constant d'un mât à l'autre, et le rapport donne la hauteur de moyeu, qui doit
rester plausible. Ce seul contrôle ramène 3 487 solutions à 142.

Contrôle croisé sur le rotor mesuré de la photo 9 : Ø 94 m sur un moyeu de 68 m, soit 115 m
en bout de pale — exactement la hauteur déclarée dans OSM, 114,9 m.

**La silhouette des boisements** donne la position. Le bas du ciel est extrait colonne par
colonne, puis comparé aux boisements détectés sur l'orthophoto IGN par un masque de texture.
OSM ne cartographie aucune haie dans ce secteur.

**Le tangage** vient de l'horizon mesuré dans l'image. `camera.horizon_v()` est la référence :
la formule réécrite à la main change de signe trop facilement, et le projet se retrouve alors
en lévitation. `proposer_vues.py` utilise désormais cette fonction.

| | Photo 9 | Photo 10 |
|---|---|---|
| Sujet | partie sud depuis l'accès au sud-ouest | partie sud depuis le chemin à l'ouest |
| Taille | 679 × 509 | 752 × 565 |
| Position | 621 869, 6 953 981 | 621 819, 6 954 097 |
| Azimut | 357,5° (N) | 33,9° (NNE) |
| Tangage | +3,40° | +0,98° |
| Focale | 530,7 px — 65,2° — 28,1 mm éq. | 552,9 px — 68,4° — 26,5 mm éq. |
| Écart sur les mâts | 0,52 px | 0,33 px |
| Accord de silhouette | 86,5 % | 74 % |
| Distance des tables | 110 à 311 m | 23 à 199 m |

Les deux focales, 28,1 et 26,5 mm éq., sont cohérentes entre elles : même appareil, même
reportage. C'est un contrôle indépendant qui n'entrait pas dans l'ajustement.

**Ce que valent ces calages.** L'azimut et la focale sont solides. La position l'est moins :
elle vient d'une comparaison de silhouettes en classes de 1,5°, **retenir ± 50 m**. Sur la
photo 9, le terrain du parc est 2 m plus bas que le point de vue, ce qui enfonce les tables
sous l'horizon : le projet n'y forme qu'une bande sombre de 16 px. Ce n'est pas un défaut de
rendu, c'est le résultat — depuis le sud, à 110 m et en contrebas, la centrale se voit à peine.

## Le rendu

`montage.py` construit l'image en deux couches.

**Le sol, par lancer de rayon.** Pour chaque pixel sous l'horizon, on cherche le point du
terrain visé en itérant trois fois contre le MNT, puis on teste s'il tombe dans l'emprise
clôturée ou sur une piste. C'est la seule méthode propre : projeter le contour de l'emprise
ne marche pas quand la caméra est juste à côté, car le polygone s'enroule autour du point de
vue. Sur la photo 10 la clôture passe à 3,8 m de l'objectif.

Ce sol donne l'**herbe rase** dans l'emprise et la **grave** sur les treize pistes, les deux
plateformes, les trois voiries et les cinq aires SDIS. La couleur d'herbe est échantillonnée
sur la photo elle-même, dans la bande verte près de l'horizon : 104, 128, 58 sur la photo 10,
contre 99, 113, 51 mesurés sur la vraie prairie visible à droite. On garde un quart de la
photo dans le mélange, pour que la couverture reste ancrée dans la lumière et les accidents du
terrain réel. Le grain s'atténue avec la distance : à 200 m une touffe de 10 cm fait moins d'un
tiers de pixel, la texture doit disparaître.

**Les volumes, triés par profondeur** : tables avec pieux et panne, clôture, haie prévue au plan.

**Les pieux étaient inclinés, et c'était un vrai bug.** Ils partaient du bord bas de la table
en suivant le vecteur de pente — lequel porte aussi l'horizontale, soit 2,17 m de décalage. Un
pieu se bat à l'aplomb de la panne qu'il porte : son pied est maintenant directement sous elle.

**Le grillage se dessine en fils tant qu'ils sont résolus.** À 3,8 m, une maille de 20 cm fait
29 px : elle se lit. Au-delà de 60 m, elle repasse en aplat léger. L'aplat seul, appliqué aux
56 segments dont un à 3,8 m, blanchissait le montage entier — c'est ce qui rendait la clôture
invisible dans la version précédente, puisque j'avais alors supprimé l'aplat de près sans rien
mettre à la place.

**Pas d'ombres portées, et c'est volontaire.** La date et l'heure ont disparu avec l'EXIF, donc
la position du soleil est inconnue. Sur les deux photos la lumière est diffuse — le piquet de
premier plan de la photo 10 ne porte aucune ombre nette — donc l'assombrissement de contact
sous les tables est la réponse physique correcte. Inventer une ombre directionnelle serait un
ajout gratuit qui se verrait.

**Ce qui reste discutable.** La clôture domine le premier plan de la photo 10 parce qu'elle
passe à 3,8 m du point de vue calculé ; avec ± 50 m d'incertitude sur la position, le vrai
point de vue peut être plus en retrait et la clôture beaucoup moins présente. Les rangées se
fondent en une nappe continue, ce qui est géométriquement juste sous cet angle rasant mais se
lit mal. Et l'herbe est un bruit procédural, pas de l'herbe.

## Équipements techniques — vues de synthèse du 18/09

`python fiche_equipements.py` produit trois vues sur fond neutre, dans
`equipements_sarnois-B/`. Le fond est un ciel dégradé et une prairie procédurale : on juge le
volume et l'échelle, pas le paysage. Une silhouette de 1,75 m donne l'échelle.

**Les dimensions ne sont pas inventées, elles sortent des blocs du plan.**

| | Source dans le DXF | Dimensions retenues |
|---|---|---|
| Poste de transformation | bloc `UNI_PTR`, polyligne intérieure | bâtiment 10,00 × 3,00 m, h 2,60 m, sur plateforme grave 13,5 × 7,0 m |
| Citerne incendie | bloc `CIT_RIGID_120m3`, deux arcs R = 3,90 m | cuve cylindrique Ø 7,80 m, h 2,51 m |
| Bac de rétention | emprise du même bloc | 16,0 × 11,3 m, merlon de 0,70 m |

La hauteur de la cuve n'est pas dans le plan : elle se déduit du volume, 120 / (π × 3,90²)
= 2,51 m. Et le bac de 16,0 × 11,3 m sous 0,70 m de merlon fait 127 m³, donc il contient bien
la cuve entière — c'est cohérent, ce qui conforte la lecture.

Le poste est rendu en préfabriqué béton : corps clair, acrotère débordant de 15 cm, double
porte métal et grille de ventilation en long pan. La citerne est une cuve cylindrique claire
au centre d'un merlon enherbé.

## Corrections du 18/09 sur la clôture

**Les poteaux n'étaient pas réguliers.** Chaque segment de la polyligne repartait à zéro,
donc les poteaux se resserraient à chaque sommet : deux côte à côte, puis un trou. La clôture
de Sarnois a 57 sommets, le défaut se voyait partout. Le pas de 3,00 m se mesure maintenant
sur l'abscisse curviligne de toute la ligne.

**Les poteaux sont des rondins d'acacia** de 13 cm, rendus en sept lamelles verticales avec
une ombre qui tourne sur le flanc. Un rond ne se dessine pas comme un rectangle plat : c'est
le dégradé latéral qui le fait lire comme un cylindre, pas le contour.

## Échelle des pistes

Vérifiée sur le plan. Les pistes simples font **4,0 à 4,3 m** de large : pistes 4 (4,0 m),
5 (4,1 m), 10 (4,3 m) et 12 (4,0 m). Les contours plus larges au tableau sont des tracés en
boucle, dont la boîte englobante ne dit rien de la largeur : la piste 7, par exemple, mesure
1 298 m² pour 210 m de long, soit 4 m de large après division. La voirie fait 3,0 m et les
plateformes 4,2 et 6,3 m. Le rendu est donc à l'échelle du plan.

## Apprendre des photomontages de référence — 18/09

Je ne peux pas m'entraîner sur des images. En revanche une paire avant / après est un
cadeau : elle isole au pixel près ce que le prestataire a peint, donc on peut **mesurer**
ses règles et s'en servir pour piloter le rendu. C'est `charte_rendu.py`, appliqué aux trois
paires HOCH déjà dans `exemples/references-HOCH/`.

| Mesure | HOCH | Mon rendu avant | Après calage |
|---|---|---|---|
| Luminance des panneaux / ciel | 0,309 | 0,384 | 0,317 |
| Teinte R, V, B | 1,04 / 1,09 / 0,87 | 0,91 / 1,01 / 1,08 | 1,01 / 1,07 / 0,92 |
| Rapport d'ombre au sol | 0,778 | 0,815 | 0,80 |
| Aération dans la bande | 0,895 | 0,931 | 0,93 |
| Écart-type dans la nappe | 20,2 | 13,4 | 13,0 |

**Deux enseignements qui ont changé le rendu.**

La teinte des panneaux chez HOCH est **chaude et neutre**, R ≈ V > B. La mienne était bleue,
parce que je faisais réfléchir le ciel. Vus de l'arrière et en rasant, les panneaux renvoient
surtout le paysage, pas le bleu du zénith.

Le rapport de luminance se transpose d'une photo à l'autre, contrairement à une couleur
absolue : c'est pour cela que la charte le stocke en fraction de la luminance du ciel de
l'image traitée, mesurée à chaque rendu.

**Ce qui reste hors d'atteinte du rendu vectoriel.** L'écart-type dans la nappe, 13 contre
20 : chez HOCH la centrale montre de la structure, des interstices, des variations de rangée
à rangée. C'est un rendu 3D avec matériaux et éclairage global, pas des facettes coloriées.
Le plafond de Fresnel est d'ailleurs devenu un paramètre calé, à 0,16, alors qu'un verre réel
renvoie bien davantage en incidence très rasante. C'est un compromis assumé, et il se recale :
`python charte_rendu.py` puis la constante `REFLEX_MAX` dans `montage.py`.

**Ce qu'apporteraient de nouvelles références.** Le format qui sert vraiment est la paire
avant / après du *même* cadrage, sans les mesures paysagères, plus les métadonnées du
`references.csv` : configuration, inclinaison, point bas, pas de rangées, date et heure. Avec
la date on récupère la position du soleil, donc des ombres portées, qui sont aujourd'hui le
manque principal. Avec plusieurs projets on peut aussi mesurer comment la charte varie selon
la lumière — ciel couvert contre soleil rasant — au lieu d'une valeur moyenne unique.

## Correction : la citerne est une bâche souple

Le bloc du plan s'appelle `CIT_RIGID_120m3`, ce qui m'a fait modéliser une cuve cylindrique
de 7,80 m de diamètre. C'est faux : il s'agit d'une **citerne bâche souple**, rectangulaire
en plan, dont la souplesse arrondit les arêtes et bombe le dessus.

Modèle retenu : 12,0 × 10,0 m au sol, 1,35 m au centre, profil de coussin s'affaissant
jusqu'au sol sur le pourtour, PVC vert sombre. Elle tient dans le bac de rétention de
16,0 × 11,3 m avec 2,0 m de garde. Conséquence sur le paysage : avec 1,35 m contre 2,51 m
pour une cuve rigide, et un merlon de 0,70 m devant, **elle ne dépasse presque pas**.

## Ce qu'apporteraient d'autres dossiers HOCH — et sous quelle forme

`ingerer_references.py` est prêt : il parcourt un dossier, ouvre les PDF, en extrait les
images assez grandes pour être des planches, **reconnaît tout seul les paires avant/après**
et les mesure. Le critère de reconnaissance est qu'un montage ne diffère de son état initial
que sur une bande, là où deux photos différentes diffèrent partout. Testé : sur un dossier
mêlant six images HOCH et un PDF de DP, il retrouve les deux paires et écarte le reste.

```bash
python ingerer_references.py "chemin/vers/les/dossiers" --conditions conditions.csv
```

**Le gain n'est pas dans le nombre, il est dans la diversité.** Les trois paires actuelles
donnent déjà des écarts considérables :

| Mesure | Vue A | Vue B | Vue C |
|---|---|---|---|
| Luminance panneaux / ciel | 0,332 | 0,321 | 0,273 |
| Rapport d'ombre au sol | 0,766 | 0,866 | 0,704 |
| Écart-type dans la nappe | 17,6 | 30,1 | 13,0 |
| Brume haut / bas | 1,27 | 0,74 | 0,92 |

La brume change carrément de sens d'une vue à l'autre, et l'écart-type varie du simple au
double. Aujourd'hui j'applique une moyenne unique à toutes les situations : c'est le vrai
défaut. Avec assez de cas on conditionne la charte par lumière, distance et angle aux
rangées, et chaque rendu prend la ligne qui lui correspond.

**Ce qu'il faut fournir, par ordre d'utilité :**

1. La **paire avant/après du même cadrage**, sans les mesures paysagères. C'est la seule
   chose indispensable ; sans l'avant, la mesure perd l'essentiel de sa précision.
2. La **date et l'heure de la prise de vue**. Elles donnent la position du soleil, donc les
   ombres portées — le manque principal du rendu actuel. Cinq dossiers datés valent mieux
   que vingt non datés.
3. La **configuration** : inclinaison, point bas, pas de rangées, orientation. Elle permet de
   vérifier que la géométrie mesurée correspond bien au plan.
4. Les **pages photomontage seules** suffisent : inutile d'envoyer les dossiers complets.

**Une douzaine de paires bien réparties suffit**, à condition de couvrir : ciel couvert et
soleil rasant ; vue proche (moins de 50 m), moyenne et lointaine (plus de 300 m) ; vue dans
l'axe des rangées et vue en travers. Au-delà, les mesures se répètent.

**Et ce que cela ne réglera pas.** L'écart-type dans la nappe restera autour de 13 contre 20 :
un rendu vectoriel colorie des facettes, il ne simule ni matériau ni éclairage global. Ce
plafond-là se lève avec un vrai moteur 3D ou une finition générative conditionnée par la
géométrie, pas avec plus de données.

## Vérifier les métadonnées avant de se poser la question

```bash
python ingerer_references.py "chemin/vers/les/dossiers" --metadonnees
```

Le relevé donne, pour chaque fichier, la date, l'heure, le GPS et l'appareil. Pour les PDF il
cherche en plus les dates **dans le texte**, avec la page et le contexte : dans un dossier de
PC, la date de prise de vue est souvent écrite en légende même quand l'EXIF a disparu.

Contrôle du détecteur : sur `exemples/sarnois-A` il retrouve bien IMG_6941 au 02/06/2026 à
16h35 avec ses coordonnées GPS, et sur un DP il remonte 31 dates avec leur page. Il ne rend
donc pas de faux négatifs.

Résultat sur les références HOCH actuelles : **0 image sur 9 porte la moindre métadonnée.**
Ce n'est pas surprenant. Une planche exportée par un outil de rendu perd son EXIF au
ré-encodage ; les états initiaux des vues A et B viennent de Google Earth, qui n'en a jamais
eu ; et même une vraie photo de terrain perd tout dès qu'elle passe par une mise en page.

**Conséquence pratique : envoyer les PDF, pas seulement les images exportées.** Le texte peut
porter ce que les pixels ont perdu. À défaut, la date peut aussi se retrouver autrement — sur
une vue Street View, le millésime de la prise de vue est affiché par Google ; sur une photo de
terrain, l'auteur s'en souvient ou l'a notée dans son rapport.

## Charte mesuree sur 18 dossiers HOCH — 18/09

`python ingerer_references.py exemples/references-HOCH --par-projet` : 182 fichiers,
156 images, **37 paires avant/apres reconnues automatiquement sur 15 projets**. Insming et
Sinard n'ont que le PDF, Albestroff n'a pas de paire.

| Mesure | n | Mediane | p10 | p90 | Sur 3 vues |
|---|---|---|---|---|---|
| Luminance panneaux / ciel | 37 | **0,266** | 0,195 | 0,391 | 0,309 |
| Rapport d'ombre au sol | 34 | 0,747 | 0,651 | 0,807 | 0,778 |
| Aération dans la bande | 37 | 0,873 | 0,753 | 0,968 | 0,895 |
| Écart-type dans la nappe | 37 | 18,5 | 12,4 | 24,7 | 20,2 |
| Brume haut / bas | 37 | 1,08 | 0,74 | 1,47 | 0,97 |

Teinte R/V/B médiane : **1,011 / 1,093 / 0,873**, contre 1,041 / 1,087 / 0,872 sur trois vues.

**Les trois premières vues étaient un peu claires** : 0,309 contre 0,266 en médiane sur 37,
soit 16 % d'écart. Le résumé est passé de la moyenne à la médiane, plus robuste à 37
échantillons qu'à 3.

**La teinte, elle, tient.** 1,01 / 1,09 / 0,87 contre 1,04 / 1,09 / 0,87 : à 37 paires comme à
3, les panneaux de HOCH sont chauds et neutres, jamais bleus. C'était la correction la plus
visible et elle est confirmée.

**Le rendu de Sarnois vue 10 mesure 0,298.** Au-dessus de la médiane, mais dans l'intervalle
p10-p90. Je n'ai volontairement pas poussé `REFLEX_MAX` à 0,05 pour coller à 0,266 : cette vue
est prise en incidence très rasante et de l'arrière, géométrie où le verre renvoie réellement
davantage. Forcer une statistique globale sur une géométrie particulière serait un
sur-ajustement. C'est exactement l'argument pour conditionner la charte plutôt que l'affiner.

## Soleil : 15 images exploitables

Sur 156 images, 37 portent une date et 15 un GPS. Pour ces 15, la position du soleil se
calcule :

| Vue | Prise de vue | Azimut soleil | Hauteur |
|---|---|---|---|
| Brigueil A | 03/10/2023 09h03 | 107° | 10,6° |
| Saint-Etienne C | 12/01/2022 11h22 | 158° | 17,1° |
| Saint-Etienne B | 13/10/2025 15h54 | 220° | 25,2° |
| Brigueil C | 25/07/2023 10h09 | 99° | 35,9° |
| La-Ville-au-Bois A/B/C | 24/07/2024 11h18-11h46 | 120-129° | 47-51° |
| Pontivy 1 | 07/08/2024 15h58 | 222° | 52,0° |
| Brigueil D | 25/07/2023 12h36 | 139° | 58,0° |

De 10,6° à 58,0° de hauteur, sur presque tout le tour d'horizon.

**Brigueil vue A et Pontivy vue 1 gardent l'EXIF sur l'avant ET sur l'après.** Ce sont les deux
cas où les ombres de HOCH deviennent vérifiables : on calcule la direction du soleil, on mesure
celle des ombres dans leur montage, on compare. C'est le prochain pas, et il conditionne
l'ajout d'ombres portées au rendu.

## Vérification des ombres de Brigueil A — 18/09

**Résultat : il n'y a pas d'ombre à vérifier.** L'almanach place bien le soleil à 10,6° de
hauteur et 107° d'azimut le 03/10/2023 à 9h03, mais la photo a été prise sous lumière diffuse.

Deux constats concordants.

*Visuel, à pleine résolution.* Les touffes d'herbe du bord de piste ne portent aucune ombre.
À 10,6° de hauteur, une ombre mesure 1/tan(10,6°) = **5,3 fois la hauteur de l'objet** : une
touffe de 50 cm projetterait 2,7 m en travers du chemin. Il n'y a rien.

*Mesuré sur la paire avant/après.* HOCH a ajouté 442 232 px de panneaux et seulement
16 112 px de sol assombri, soit **0,04 fois la surface des panneaux**, et cet assombrissement
occupe exactement la même bande d'image que les rangées (v 1441-1920 contre 1441-1917). C'est
un contact au pied des tables, pas une ombre portée. Une vraie ombre à 10,6° couvrirait 13 m
de sol par rangée de 2,5 m et dominerait largement la surface des panneaux.

**La contre-épreuve est nette.** La-Ville-au-Bois vue C, 24/07/2024 à 11h31, soleil à 49,4° —
et cette fois la photo montre de vraies ombres de conifères sur la piste. Là, HOCH ajoute
20 098 px d'ombre pour 26 803 px de panneaux, soit **0,75 fois la surface**. Presque vingt fois
plus qu'à Brigueil.

| | Brigueil A | La-Ville-au-Bois C |
|---|---|---|
| Soleil (almanach) | 10,6° | 49,4° |
| Soleil visible dans la photo | non | oui |
| Surface d'ombre / surface de panneaux | 0,04 | 0,75 |

**La règle de HOCH est donc la règle physique** : ombre portée quand il y a du soleil direct,
simple contact sinon. C'est celle que j'applique déjà sur Sarnois, où les deux photos sont
également sous lumière diffuse.

**Ce que je n'ai PAS pu vérifier : la direction.** Il faudrait le cap de la caméra pour
convertir une direction d'image en azimut. Les métadonnées de vol du drone de La-Ville-au-Bois
donnent l'altitude et le cap de l'appareil, mais les champs de nacelle sont à zéro, donc
inutilisables. J'ai tenté de comparer l'orientation des ombres ajoutées à celle des ombres
réelles de la photo : l'écart obtenu, 25°, n'est pas concluant, car les deux zones sont
éloignées dans une vue aérienne oblique où la perspective fait tourner les directions
apparentes, et le masque des ombres ajoutées suit surtout l'axe des rangées. **Ce chiffre ne
prouve rien, ni dans un sens ni dans l'autre.**

**Correction de ce que j'annonçais.** J'avais présenté Brigueil A et Pontivy 1 comme les deux
cas où les ombres deviendraient vérifiables, parce qu'ils gardent leur EXIF. C'était prématuré :
les deux sont sous lumière diffuse. **Une date et un GPS donnent la position du soleil, pas les
conditions d'éclairage.** Il faut les deux, et c'est la photo qui tranche la seconde.

## Référence ensoleillée avec cap caméra — Saint-Etienne-sous-Barbuise vue B

Le cap se trouve dans l'EXIF de certains téléphones, balise `GPSImgDirection`. Je ne l'avais
pas cherché : **5 images sur 156 le portent**, toutes des iPhone. Une seule est en plein soleil.

**Saint-Etienne-ss-Barbuise, vue B** : iPhone 14, 13/10/2025 15h54, GPS 48.50289 / 4.14676,
cap 245,8° magnétique. Et surtout, **le soleil est dans le cadre**, avec son halo de surexposition.

### Vérification de la chaîne complète

Le soleil visible permet mieux qu'une vérification d'ombres : on résout l'orientation de la
caméra sur sa position dans l'image, et on la compare à la boussole du téléphone.

| | Valeur |
|---|---|
| Soleil calculé (pvlib, d'après EXIF) | azimut 220,17°, hauteur 25,23° |
| Tache surexposée mesurée | 29 642 px, centre (401, 422) sur 4032 × 3024 |
| Focale déduite de l'EXIF | 2 912 px, champ 69,4° |
| **Caméra résolue sur le soleil** | **azimut 250,80° vrai, tangage +8,19°** |
| **Cap EXIF du téléphone** | 245,8° magnétique, soit **247,4° vrai** |
| **Écart** | **3,4°** |

Deux sources indépendantes — l'almanach projeté par mon modèle de caméra, et la boussole du
téléphone — s'accordent à 3,4°, ce qui est la précision courante d'une boussole de smartphone.
Le résidu de la résolution est nul, les deux inconnues étant déterminées par les deux
coordonnées du soleil. **Cela valide bout en bout : EXIF → pvlib → modèle de caméra → image.**

### La direction des ombres reste, elle, non tranchée

Sur cette vue, HOCH n'a presque pas posé d'ombre au sol : rapport 0,03, et aucune tache
allongée mesurable. Ce n'est pas une erreur de leur part, c'est la géométrie. La vue est à
contre-jour — la caméra regarde à 250,8°, le soleil est à 220,2°, donc les ombres partent vers
l'azimut 40,2°, c'est-à-dire **derrière les rangées et vers l'observateur**. Avec une nappe
dense (aération 0,54), elles sont cachées par les tables elles-mêmes.

J'ai aussi tenté de mesurer les ombres réelles dans l'herbe, en comparant chaque tache sombre
allongée à la direction attendue calculée en son propre point au sol : 118 taches, écart médian
17°, 42 % sous 15 degrés contre 33 % au hasard. **Corrélation réelle mais faible**, parce que
les taches sombres d'une prairie sont surtout de la végétation, pas des ombres portées.

### Ce que les trois cas disent ensemble

| Vue | Soleil | Géométrie | Ombre / panneaux |
|---|---|---|---|
| Brigueil A | absent, ciel diffus | — | 0,04 |
| Saint-Etienne B | présent, contre-jour | nappe dense, ombres derrière les rangées | 0,03 |
| La-Ville-au-Bois C | présent, vue aérienne | nappe vue de dessus, ombres dégagées | 0,75 |

La règle n'est donc pas seulement « soleil ou pas » : **c'est la géométrie qui décide si les
ombres sont visibles.** Une nappe dense vue à contre-jour n'en montre aucune, même en plein
soleil. Cela conforte le choix fait sur Sarnois, mais pour deux raisons au lieu d'une.

## Recalage de la vue drone de La-Ville-au-Bois — tentative et verdict

Objectif : obtenir le cap de la caméra indépendamment des ombres, pour vérifier ensuite leur
direction. La prise de vue a tout ce qu'il faut sur le papier — GPS, altitude de vol 29,1 m,
focale 24 mm éq., soleil réel et ombres visibles.

**Ce qui a marché.** L'horizon, ajusté sur 3 440 colonnes avec 6,2 px de résidu, donne le
tangage et le roulis sans aucun point d'appui : **−12,58°** et **−2,09°**. C'est propre et
c'est deux des trois angles.

**Ce qui n'a pas marché : le cap.** Trois voies essayées, aucune concluante.

1. *Point de fuite de la piste.* Les deux bords s'ajustent mal — 100 px de résidu à gauche,
   où la piste se confond avec l'herbe et disparaît derrière les conifères. Le point de fuite
   obtenu tombe 507 px sous l'horizon, alors qu'une direction horizontale doit s'y trouver
   exactement. Incohérent, donc rejeté.
2. *Deux points d'appui lus sur l'ortho.* Résidu de 648 px : les deux points se contredisent,
   donc au moins un est mal identifié. Le cap sorti, 355,6°, est cohérent en gros avec le cap
   de vol DJI de 12,6°, mais à 17° près — sans valeur pour ce qu'on cherche.
3. *Azimut de la haie de conifères.* La détection par seuil attrape un bosquet de 101 × 47 m
   au lieu d'une ligne : ce n'est pas une haie, donc l'azimut mesuré ne veut rien dire.

**La cause est identifiable.** L'orthophoto IGN et la photo de juillet 2024 ne sont pas du même
millésime : les cultures ont changé, la friche a évolué, et les repères vraiment stables — une
lisière, un croisement — sont peu nombreux et difficiles à pointer au pixel près dans une vue
aérienne oblique. C'est précisément le cas où un humain qui voit les deux images fait en trois
minutes ce qu'un seuillage ne fait pas.

**Verdict sur la question des ombres.** Elle se referme ainsi :

| Question | Statut |
|---|---|
| La chaîne EXIF → pvlib → modèle de caméra → image est-elle juste ? | **Vérifiée à 3,4°** (Saint-Etienne, soleil dans le cadre) |
| HOCH pose-t-il une ombre quand il faut, et pas quand il ne faut pas ? | **Vérifié** sur trois cas (0,04 / 0,03 / 0,75) |
| L'azimut des ombres de HOCH est-il exact ? | **Non tranché** |

**Et cette dernière question n'est pas bloquante.** Mon rendu calcule la direction des ombres
avec pvlib, c'est-à-dire par la partie validée de la chaîne. Que HOCH ait raison ou non sur
l'azimut ne change rien à ce que je produis. Ce qui bloque les ombres sur Sarnois reste
l'absence de date dans les photos du bureau d'études.

Pour la fermer complètement il faudrait pointer à la main cinq ou six correspondances entre la
photo drone et l'orthophoto, dans l'outil de calage déjà construit. Une dizaine de minutes,
mais pour un résultat qui ne changerait aucune décision.

## Les locaux techniques, eux, n'étaient pas calés — corrigé le 18/09

La charte ne mesurait que ce qui est **plus sombre** que le fond : tout part du masque
`assombri`. Un préfabriqué béton est plus **clair** que l'herbe, donc il échappait entièrement
à la mesure, et mes bâtiments gardaient des couleurs posées à l'œil.

Ajout d'une passe sur les **volumes clairs ajoutés** : régions éclaircies par le montage,
compactes — un bâtiment est trapu, une piste ou une clôture est allongée, le rapport
d'élongation les sépare — et suffisamment pleines pour être des volumes.

Sur 37 paires, 14 en contiennent. J'en écarte 5 : celles où la détection compte plus de vingt
volumes, donc attrape des clôtures ou des structures, et deux où l'appariement avant/après
s'est inversé. Restent **9 vues exploitables**, de Ruffec 3 à Saint-Hilaire-le-Vouhis.

| Mesure | Médiane | p10 | p90 | Ce que j'utilisais |
|---|---|---|---|---|
| Luminance / ciel | **0,659** | 0,524 | 0,823 | **1,02** |
| Teinte R / V / B | 1,044 / 1,021 / 0,931 | | | 1,028 / 1,007 / 0,965 |
| Écart-type interne | 15,6 | | | 0 (aplat) |

**Mon béton était à 1,02 fois la luminance du ciel, donc aussi clair que le ciel.** Les
références le placent à 0,66, soit un tiers plus sombre — et au-dessus même du p90 de 0,823.
C'était l'erreur la plus grossière du rendu des équipements, et elle sautait aux yeux une fois
le chiffre posé.

Le poste tire maintenant toutes ses teintes de cette base : corps à 0,66 du ciel, toit à 0,78
du corps, acrotère à 0,91, portes à 0,54, grille à 0,45, plateforme en grave à 0,76. La teinte
est légèrement chaude, comme pour les panneaux.

**Ce qui reste non calé** : la citerne souple et les poteaux d'acacia. Aucune référence HOCH
ne montre de bâche souple, et les clôtures sont écartées par le filtre d'élongation. Ces
deux-là restent choisis à l'œil, et je le signale plutôt que de laisser croire le contraire.

## Blender installé et parité vérifiée — 18/09

**Installation.** `bpy` n'existe pas pour Python 3.12 (les roues officielles visent 3.11), donc
Blender portable : `blender-4.5.9-windows-x64.zip`, 399 Mo depuis download.blender.org, extrait
dans `AppData\Local\Programs`. Série LTS, pas la 5.x, parce qu'un outil de production a besoin
de support long. **Aucun droit administrateur, rien dans OneDrive**, et Python 3.11.11 embarqué.
Tourne sans interface : `blender -b -P script.py`.

**Le verrou franchi.** Le repère caméra du projet est gaucher, `det R = −1` ; Blender est
droitier et sa caméra regarde vers son −Z. Une erreur de signe là-dedans retourne le projet
sans rien signaler — exactement le tangage inversé de la veille. La conversion tient en une
ligne : les colonnes de la matrice monde de la caméra Blender sont (droite, haut, −avant), où
ces trois axes sont les lignes de `R`.

| Cas | Écart maximal |
|---|---|
| Vue au sol, plein nord | 0,00012 px |
| Azimut quelconque | 0,00022 px |
| Tangage négatif | 0,00013 px |
| Roulis non nul | 0,00017 px |
| Vue de drone plongeante | 0,00042 px |
| Azimut proche de 360° | 0,00010 px |

**0,0004 px au pire, sur 24 points par cas.** Blender retrouve exactement les pixels de
`camera.py`. C'est le même rôle que la confrontation à OpenCV dans la suite de tests : une
implémentation totalement indépendante doit tomber sur les mêmes nombres.

**Verrouillé.** `parite_blender.json` enregistre le résultat et les empreintes de `camera.py`,
`blender_camera.py` et `parite_blender.py`. Un test de la suite échoue si l'un des trois bouge
sans que la parité ait été refaite. Même mécanique que le verrou du JavaScript. 50 tests.

**Une contrainte du bac à sable à connaître** : lancer `blender.exe` depuis un sous-processus
Python est refusé (WinError 5). Le script est donc découpé en trois temps — Python prépare les
paramètres, le shell lance Blender, Python compare. C'est aussi plus rapide, un seul lancement
traitant tous les cas.

**Prochaine étape** : exporter la géométrie (tables, pieux, clôture, bâtiments) et la pose vers
Blender, puis rendre avec de vrais matériaux et un ciel HDRI. C'est là que se lève le plafond
mesuré — écart-type de 13 dans ma nappe contre 18,5 dans les références.

## Corrections du premier rendu Blender

**La clôture était 192 m sous terre.** Les constructeurs de géométrie mélangeaient altitudes
absolues et relatives : les tables venaient du DXF en NGF absolu, les poteaux passaient par une
fonction qui retranchait déjà l'origine, et `local()` la retranchait une seconde fois. Rien ne
le signalait — la clôture était simplement absente de l'image. Tout est maintenant en absolu
dans les constructeurs, et `local()` retranche une seule fois.

**Le jeu entre modules faisait 20 cm au lieu de 2.** Le paramètre était un demi-jeu appliqué de
chaque côté de chaque cellule, donc doublé. Sur le rendu vectoriel cela se voyait peu, les
modules étant posés sur un cadre plein ; dans Blender ce sont de vrais trous.

**Le grillage était un mur de béton.** Exporté comme un quad plein, à 3,8 m de l'objectif il
barrait tout le cadre. Il porte maintenant des UV **en mètres** et un alpha procédural : modulo
la maille de 20 cm, on est sur un fil si on est à moins de 6 mm du bord. La maille se voit, et
on voit à travers.

**La teinte bleue est corrigée par calage de la base du module.**

| Mesure | Avant | Après | Référence |
|---|---|---|---|
| Luminance / ciel | 0,488 | **0,244** | 0,266 |
| Teinte R / V / B | 0,90 / 1,05 / 1,05 | **1,06 / 1,16 / 0,78** | 1,01 / 1,09 / 0,87 |
| Écart-type | 6,9 | **14,2** | 18,5 |
| Douceur de bord | 6,5 | 4,9 | 6,4 |

Au passage, les matériaux avaient le même défaut que le monde : couleurs sRGB données comme
linéaires à Cycles. C'est ce qui faisait virer les rondins d'acacia au béton.

**Une limite à connaître avant de réutiliser ce matériau.** Une base grise chaude à 84/74/44
avec une rugosité de 0,80 ne décrit pas un module photovoltaïque, qui est bleu sombre et lisse.
Elle compense la réflexion du ciel dans la géométrie de **cette** vue, prise à 78° d'incidence,
où un verre nu donnerait 0,64 fois la luminance du ciel, soit deux fois et demie la référence.
Le calage vaut pour cette géométrie ; une vue plus de face demanderait de le refaire. Le bon
modèle serait une réflectance fonction de l'angle d'incidence, calée sur des références dont on
connaîtrait la géométrie de prise de vue — ce que le `references.csv` ne donne pas.

## Cadres, acacia, et la photo 9 — dernier tour

**La tache uniforme sur les rangees basses.** Vue en rasant le long des rangees, chaque rangee
masque la suivante et la nappe devient un aplat. Ce qui manquait n'etait pas un reglage de
couleur mais de la **geometrie** : les cadres aluminium. Une aile de 4 cm le long des bords haut
et bas de chaque table, plus les montants entre modules, 2 467 faces au total. Ce sont eux qui
dessinent les lignes entre rangees. L'ecart-type est passe de 14,2 a **16,4** contre 18,5 en
reference, sans toucher a la couleur.

**Les poteaux d'acacia.** Deux causes cumulees : la conversion sRGB vers lineaire, qui les avait
assombris, et surtout la desaturation par un ciel bleute diffus. Un bois chaud eclaire par du
bleu perd sa chaleur au rendu ; il faut partir d'une base **plus saturee** que la couleur voulue,
226/176/104, pour retrouver un miel grisant a l'image.

**Photo 9.** Rendue aussi. Le projet y est a 110-311 m et 2 m en contrebas, donc il n'occupe
qu'une bande fine : 14 766 pixels de rendu contre 226 737 sur la photo 10. L'ecart-type y tombe
a 8,9, ce qui est normal — a cette distance la trame des modules passe sous le pixel et il ne
reste qu'une masse sombre. Ce n'est pas un defaut de rendu, c'est ce que voit l'oeil depuis ce
point de vue.

| Mesure | Photo 10 | Photo 9 | Reference |
|---|---|---|---|
| Luminance / ciel | 0,258 | — | 0,266 |
| Teinte R / V / B | 1,07 / 1,16 / 0,77 | 1,04 / 1,13 / 0,83 | 1,01 / 1,09 / 0,87 |
| Ecart-type | 16,4 | 8,9 | 18,5 |

## Equipements techniques rendus en Blender

`exporter_equipements.py` + `blender_rendu.py` + `composer_equipements.py` produisent les
trois vues de synthese dans `equipements_sarnois-B/` : `poste3d.jpg`, `citerne3d.jpg`,
`entree_sud3d.jpg`, et la planche `planche_equipements3d.jpg`.

Le partage des roles reste le meme que pour les photomontages. Le fond — ciel degrade et
prairie procedurale — est calcule en numpy ; Blender apporte les volumes, leurs materiaux et
leurs ombres de contact ; la silhouette de 1,75 m et les legendes se posent a la composition.

Ce que le passage en 3D change sur ces vues :

- le **poste** a des ombres de contact calculees sous l'acrotere debordant et dans les
  embrasures des portes, la ou le rendu vectoriel posait des aplats ;
- la **citerne souple** prend un ombrage continu sur son bombe, ce qui la fait lire comme une
  bache tendue et non comme un polygone vert ;
- le **merlon** du bac de retention se detache par son propre ombrage au lieu d'un degrade
  calcule a la main ;
- la **cloture** est la meme geometrie que sur les photomontages : poteaux d'acacia
  cylindriques et grillage ajoure par alpha procedural.

Dimensions inchangees, toujours tirees des blocs du plan : batiment 10,00 x 3,00 m sur emprise
13,5 x 7,0 m, bache souple 12,0 x 10,0 m et 1,35 m au centre, bac de 16,0 x 11,3 m ceinture
d'un merlon de 0,70 m.

**Ce qui reste a faire sur ces vues** : la plateforme en grave est une dalle lisse, sans
granulometrie ; et la teinte du beton vient de la charte mesuree sur 9 vues seulement, avec un
intervalle p10-p90 de 0,52 a 0,82 autour de 0,66 — c'est la mesure la moins assuree du lot.
