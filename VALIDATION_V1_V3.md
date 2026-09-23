# Validation du cœur géométrique — V1, V2, V3

Réalisé le 16/09/2026, sans matière nouvelle : tout vient du DXF et de la photo déjà présents.
Lancer : `python -m pytest test_geometrie.py -v` puis `python audit_sarnois.py`.

| Fichier | Rôle |
|---|---|
| `camera.py` | Modèle sténopé de référence en Python, miroir exact du JavaScript du HTML |
| `test_geometrie.py` | 43 tests : V1 extraction DXF, V2 modèle, V3 audit photo |
| `parite_js.py` | Comparaison JavaScript / Python et verrouillage par empreinte |
| `audit_sarnois.py` | Mesures sur IMG_6941 (mâts d'éoliennes, ligne d'arbres) |

## Résultat en une phrase

Le modèle de projection est maintenant vérifié et protégé contre les erreurs de convention.
Le calage de la photo de Sarnois, lui, reste non validé : deux éoliennes distantes de 5° ne
suffisent pas à séparer l'azimut de la focale.

## V2 — Modèle sténopé : vérifié

- **Confrontation à OpenCV.** Notre projection et `cv2.projectPoints` coïncident à 4 × 10⁻¹² px
  sur cinq orientations très différentes. C'est une implémentation totalement indépendante, donc
  une vraie contre-épreuve.
- **Parité JavaScript / Python.** Le modèle du HTML et `camera.py` donnent les mêmes pixels à
  4 × 10⁻¹² px sur quatre configurations, et rejettent les mêmes points. La source de `makeCam`
  est verrouillée par empreinte : si elle change, un test exige de rejouer la comparaison.
- **Tests de mutation.** Six conventions cassées volontairement (sens de l'azimut, signe du
  tangage, signe du roulis, sens de l'axe vertical de l'image, permutation Est / Nord, focale
  calculée sur le mauvais côté du capteur). Les six sont détectées. La focale n'est protégée que
  par un seul test, c'est le point le plus mince.
- **Découverte de convention.** Le repère caméra du brief (X à droite, Y en haut, Z vers l'avant)
  est **gaucher** : droite ∧ haut = −avant, donc le déterminant de la rotation vaut −1. Ce n'est
  pas une erreur, la projection le compense, et le passage en convention OpenCV rétablit +1. Mais
  il faudra le savoir avant de brancher Blender ou toute bibliothèque 3D, qui attendent un repère
  droitier. C'est écrit dans `camera.py` et vérifié par un test.

## V1 — Extraction DXF : une erreur trouvée, une valeur corrigée

- **Le « +1,50 m » du brief était en double.** Les coins bas exportés par PVcase sont déjà à
  1,500 m (± 0,006) au-dessus du terrain. Les rendus du 07/09 plaçaient les tables 1,5 m trop
  haut, soit 16 à 24 px. Le script mesure désormais l'écart au sol et n'ajoute que le complément.
- **Le pas entre rangées est 10,33 m**, pas 8,4 m comme je l'avais écrit le 14/09. Mon calcul
  rapide projetait chaque table sur sa propre normale, ce qui n'a pas de sens. Il faut projeter
  tous les centroïdes sur une direction commune. 15 rangées, pas régulier à ± 0,02 m, avec trois
  écarts plus grands là où passe une piste.
- Verrouillés par tests : 85 tables, largeur 4,784 m, inclinaison 25,0°, dénivelé 2,022 m, ordre
  des sommets, orientation des modules vers le secteur sud, clôture à 21 sommets, 4 044 points
  topo, et le fait que les coordonnées brutes des blocs sont en OCS et inutilisables.

## V3 — Audit de la photo : le calage n'est pas validé

Mesures faites dans l'image, sans réglage manuel.

| Grandeur mesurée | Résultat | Qualité |
|---|---|---|
| Fût de l'éolienne gauche | +0,01° ± 0,10 de la verticale | 69 lignes, résidu 0,30 px |
| Base de la ligne d'arbres | +0,61° | 107 colonnes, résidu 5,5 px |

**Le roulis est bien nul**, ce qui confirme la valeur retenue le 07/09. Au passage, un piège :
mesurer le fût par le maximum de contraste attrape une pale et donne +2,6°, ce qui conduisait à
conclure à tort à un roulis de 5°. Il faut cibler la bande sombre du fût, les pales étant claires.
Le test de non-régression impose désormais un résidu inférieur à 1 px.

**La focale reste ouverte.** Écart entre la position prédite et la position mesurée des deux fûts :

| Hypothèse de focale | Azimut associé | Écart sur les fûts |
|---|---|---|
| 2 457 px, règle EXIF appliquée à la largeur | 332,8° | 27 px |
| 2 912 px, rognage 9:16 corrigé sur la hauteur | 335,3° | 7,5 px |
| 3 166 px, calage visuel du 07/09 | 336,4° | 3,7 px |

La règle EXIF naïve est clairement exclue : la correction du rognage est donc nécessaire, ce qui
confirme le constat du 07/09. Mais la valeur exacte ne l'est pas. L'azimut et la focale sont
corrélés à 0,98 : toute augmentation de focale se rattrape par une rotation. Deux repères situés
à 5° l'un de l'autre, du même côté du cadre, ne les séparent pas.

**Ce qu'il faudrait pour trancher**, par ordre d'efficacité :
1. Une mire imprimée photographiée avec le même téléphone dans le même mode. Cela donne la focale
   seule, à 0,5 % près, et se fait au bureau en une heure pour tous les modèles de l'équipe.
2. Des repères répartis sur toute la largeur de l'image plutôt que groupés.
3. Une photo non rognée, en désactivant le cadrage 9:16 de l'application.

## Ce qui est validé et ce qui ne l'est pas

Validé : l'extraction DXF, la conversion des coordonnées, le modèle de projection, sa transcription
en JavaScript, le roulis nul sur cette photo, et le fait que la focale EXIF brute est fausse.

Non validé : la focale exacte, l'azimut exact, le tangage (mesuré sur la ligne d'arbres prise pour
l'horizon, ce que la topographie du site rend acceptable mais qui ne se généralise pas), la
position de la caméra (le GPS à 5 m près vaut 53 px à 300 m et rien ici ne le contrôle), et la
hauteur apparente des tables, qu'aucun repère de cette photo ne permet de vérifier.

Le premier test capable de tout valider ensemble reste une centrale déjà construite, photographiée
depuis plusieurs points, avec son plan de récolement.
