# Photomontage de centrales photovoltaïques au sol

Production des photomontages d'insertion paysagère pour les projets PV d'UNITe : on part
d'une photo géolocalisée et d'un plan, on rend le projet en 3D à la pose exacte du
cliché, et on compose.

Le résultat alimente la pièce **DP 6 — Insertions paysagères** du dossier de déclaration
préalable, produite par [`generateur-dp`](https://github.com/eliott-mo/uniteoutilspv-generateur-dp).

---

## Entrées attendues

| | |
|---|---|
| **une photo géolocalisée** | fournie directement, ou extraite d'un rapport photo-géoloc |
| **un plan DXF** | complet, ou limité aux tables — et dans ce second cas, un plan PDF portant clôture, haies, pistes et ouvrages |

Trois choses valent d'être demandées **avant** de commencer, parce qu'elles coûtent cher
à rattraper :

1. **La photo originale**, avant GPS Map Camera. L'application recadre en 9:16 et perd
   l'EXIF. Sans focale, la pose n'est pas déterminée : mesuré à Gannay, l'emprise
   latérale de la nappe varie de ±15 % entre 22 et 30 mm équivalents. À défaut de
   l'originale, le **modèle de téléphone** donne la focale à 2 % près.
2. **La correspondance fichier ↔ numéro de vue du dossier.** Le rapport HTML de Gannay
   publiait le même cliché sous les numéros 1 et 2 (même empreinte MD5), ce qui décale
   toute la numérotation ensuite.
3. **L'horizon de la mesure paysagère** — haie à la plantation, ou à quelques années.

---

## Avant tout : le point de vue est-il exploitable ?

C'est la première question, elle coûte une seconde, et elle ne demande même pas la
photo — seulement la position.

```bash
streamlit run app.py                     # interface, pour un chef de projet
python garde_prise_de_vue.py plan.dxf photo.jpg          # ou en ligne de commande
```

Le pilote de Saint-Cyr a coûté quatre allers-retours et n'a rien livré : le premier
ouvrage visible y était à **2,4 m** et **9,4 m**, contre **20 m** sur les deux vues de
Sarnois qui, elles, ont été livrées.

| vue | premier ouvrage visible | clôture de 2 m | déplacement dû au GPS |
|---|---|---|---|
| Sarnois PV9 — livré | 21,4 m | 8,6 % | 2,3 % |
| Sarnois PV10 — livré | 20,0 m | 9,2 % | 2,6 % |
| Saint-Cyr PV3 — abandonné | 9,4 m | 18,8 % | 13,6 % |
| Saint-Cyr PV4 — abandonné | 2,4 m | 75,3 % | 191,7 % |

Les seuils sont calés sur ces quatre cas, là où l'écart est le plus large. Le critère
décisif n'est pas la taille apparente mais l'**incertitude de position** : la base d'un
ouvrage à la distance *d* se projette en `horizon + f·h/d`, donc une erreur δ la déplace
de `f·h·δ/d²` pixels — en **carré inverse** de la distance. C'est pourquoi les mêmes
outils marchent à 20 m et échouent à 2,4 m alors que rien d'autre n'a changé.

Deux pièges relevés en écrivant ce contrôle :

- **ce qui compte est dans le cadre, pas autour.** Une première version mesurait la
  distance à l'ouvrage le plus proche *du point de vue* et recalait Sarnois : les quatre
  vues sont au bord d'un chemin, donc à trois mètres d'une clôture, souvent dans le dos.
- **une polyligne se juge sur sa longueur, pas sur ses sommets.** Une clôture de trois
  cents mètres peut n'avoir que quatre sommets ; le brin qui passe à deux mètres de
  l'objectif a ses extrémités à cent. Les tracés sont donc densifiés au mètre.

Et **ce qui n'est pas un défaut** : que le projet ne tienne pas entier dans le cadre.
Sarnois PV10 n'en montre que 26 % et a été livré — une centrale de quatre hectares vue
de son bord couvre 359°, et c'est bien pour cela qu'un dossier porte plusieurs vues.

---

## La chaîne

```
plan (DXF, ou DXF + PDF)  ─┐
                           ├─►  scène JSON  ─►  Blender  ─►  rendu RGBA
photo + pose calée  ───────┘                                      │
                                                                  ▼
                              masque de premier plan  ─►  composition  ─►  montage
```

Chaque étape est un module, et le **partage des rôles ne doit pas bouger** :

| | |
|---|---|
| `exporter_blender.py`, `exemples/*/exporter_*.py` | connaissent le plan, le terrain et la pose. Produisent de la géométrie en mètres, repère local (E, N, Up) centré sous la caméra |
| `blender_rendu.py` | s'exécute **dans** Blender et ne connaît **rien** du photovoltaïque. Monte des maillages, applique des matériaux, rend à fond transparent |
| `masque_avant_plan.py`, `composer_blender.py` | composent en numpy |

`blender_rendu.py` ne s'importe donc pas depuis l'environnement pip : il tourne sous le
Python de Blender, qui embarque `bpy` et `mathutils`.

```bash
python exemples/casxcas/exporter_gannay.py 4 scene.json
blender -b --factory-startup -noaudio -P blender_rendu.py -- scene.json rendu.png 128
python exemples/casxcas/monter.py 4 --haie
```

---

## Le masque de premier plan

C'est la seule étape où la machine ne tranche pas seule, et c'est là que se joue le temps
de production. `apercu_masque.py` produit une **planche de validation** avant tout rendu :
elle coûte quelques secondes contre plusieurs minutes pour un rendu, ce qui rend les
corrections gratuites.

La planche montre le masque **complet**, pas un morceau : elle appelle
`masque_avant_plan.masque` avec les réglages de la vue et teinte son résultat. Une version
antérieure n'affichait que le classement par couleur, et faisait signaler comme oubliées
des masses masquées à 100 % par la ligne de garde.

### Deux natures de masque

**La ligne de garde** est de la géométrie, pas une estimation. Un ouvrage est posé sur le
sol : son point le plus bas dans une colonne *est* le sol à sa distance, donc tout ce qui
est plus bas dans l'image est plus près. Elle existe en deux formes, et le choix compte :

- **globale**, tirée de la distance minimale — valable quand l'ouvrage est à distance à
  peu près constante ;
- **par colonne** — indispensable dès que l'ouvrage fuit. Sur une vue de Sarnois où la
  clôture part à 3,8 m et s'éloigne à 245 m, les deux diffèrent de 1 200 px.

Elle se lit **sur le rendu**, qui est rastérisé, et non sur la projection des sommets : à
quatre mètres, une face de poteau couvre 400 px de haut et 30 de large, et dans les
colonnes où elle n'a pas de sommet l'enveloppe par sommets remonte au bas d'un panneau
lointain — 296 px d'ouvrage effacés en médiane sur 566 colonnes.

**Les masses de premier plan** demandent un jugement humain, et trois détourages existent
selon **ce sur quoi la masse se découpe** :

| détourage | quand | fonction |
|---|---|---|
| contre le **ciel** | la masse fait l'horizon | `masque_par_silhouette` |
| par **couleur** | masse franche qu'aucune silhouette ne borne | `masque_par_couleur` |
| **remontée** depuis la garde | masse sombre reliée au sol, sur fond clair | `masque_remontant` |

Une masse de premier plan touche le sol, donc elle traverse la ligne de garde : c'est la
règle de connexité, et elle vaut pour les trois. Un amas qui flotte au-dessus du champ,
si sombre et si vert soit-il, est un arbre lointain — la couleur ne les distingue pas, la
position si.

### Ce qui ne s'automatise pas, et se déclare

- `arriere_plan=((x0, x1), …)` — des colonnes que les automatismes ont prises à tort.
  Cas réel : un arbre de troisième plan dont le houppier touche, dans l'image, la haie
  proche qui passe devant lui. Colonne sombre continue : ni la remontée, ni le classement,
  ni un filtre médian ne le rejettent.
- un **profil**, polyligne (x, v) en quatrième terme d'une plage, pour redéclarer ce qui
  se trouve vraiment là où `arriere_plan` a annulé.

L'ordre est celui du sens : les automatismes proposent, `arriere_plan` annule, l'opérateur
redéclare.

---

## Pièges mesurés, à ne pas réintroduire

**Une constante en pixels absolus est un piège.** Tout seuil vertical se règle sur la
hauteur d'image de la première photo traitée, puis casse au format suivant. La remontée
valait 120 px, calée sur les 960 px de Gannay ; sur un cliché de 4 032 px elle ne couvrait
plus que 3 % de l'image. Exprimer en **fraction de hauteur**.

**Un nuage blanc n'est pas bleu.** Le détecteur de ciel exigeait B nettement au-dessus de
R : vrai d'un ciel franc, faux d'un cirrus. Sur une vue de Gannay il échouait sur 733
colonnes sur 1 280, et le masque y effaçait toute la hauteur d'image — la haie paysagère
gommée sur 591 colonnes, sans que rien ne le signale. Le ciel se définit par ce qu'il
n'est **pas** : jamais chaud, jamais vert.

**Le capteur d'ombre n'est pas un ouvrage.** C'est une nappe invisible au rendu, centrée
sous la caméra. Comptée dans `distance_mini` elle donne une distance nulle ; comptée dans
l'enveloppe elle efface le bas de la centrale.

**Rien n'est devant — sauf quand quelque chose l'est.** `peindre_sol` lance un rayon par
pixel et peint le sol du site partout où le rayon l'atteindrait, sans test d'occlusion.
Inoffensif à 100-400 m d'un site dégagé ; faux dès qu'un ouvrage arrive à quelques mètres.
Attention toutefois à la symétrique : sur une vue où le premier plan et le couvert du site
sont **la même culture**, il n'y a rien à retrancher — le champ est continu.

**AgX délave.** `view_transform = "Standard"` est obligatoire ; le défaut de Blender 4.x
rendrait un module bleu nuit en aplat beige. Et le matériau de module par défaut de
`blender_rendu` est un calage **sous ciel couvert** : sous un soleil franc il faut le
module physique (base 16/20/33, rugosité 0,10, spéculaire 0,5).

**Une ombre portée n'est pas du noir.** Cycles la rend comme un alpha sur du RGB nul :
composée telle quelle, un alpha de 0,89 ne laisse que 11 % de la lumière. Un sol à l'ombre
sous un ciel dégagé en garde 40 à 55 %, éclairé par le ciel et d'une lumière bleue.

**`np.allclose` est un piège en Lambert 93.** Sa tolérance est *relative* :
`rtol=1e-5` sur un nord de 6 750 000 vaut **soixante-sept mètres**. Écrit ainsi, le test
« le contour se referme-t-il ? » retirait un sommet à chaque secteur de portail — qui
n'en a que trois — et plus aucun vantail n'était reconnu : le plan semblait n'avoir aucun
portail. Toute comparaison de positions se fait en mètres, explicitement.

**Un matériau ajouré n'a pas l'alpha d'un mur.** Le grillage plafonne à 80 entre deux
poteaux. Lire le bord du projet à `alpha > 128` y donnait NaN, donc aucun défrichement,
donc un peigne de bandes verticales intactes — une par entre-poteau. À `alpha > 32` la
ligne est continue : 765, 769, 757, 756, 754 là où 128 donnait 765, NaN, NaN, 756, 823.

**Le plan donne les cotes, le gabarit ne sert que de secours.** J'ai d'abord tenu
l'inverse. La bâche incendie de Saint-Cyr est dessinée 8,08 × 7,40 m et longe la clôture ;
montée au gabarit de 11,70 × 8,90, **15 % de son aire tombait hors de l'enceinte** et la
clôture la traversait. Le poste, lui, est dessiné 12,00 × 3,00 m, soit le gabarit au
centimètre : là où les deux sources existent, elles concordent. Seule la **hauteur** n'est
jamais lisible sur une vue de dessus.

**Un portail est un segment de clôture.** La couche `UNI_portail` ne porte parfois aucune
polyligne — à Saint-Cyr, six hachures, neuf lignes et six arcs. Compter un portail par
tracé en donnait quinze, emmêlés. Les hachures sont des **vantaux**, et leurs pointes de
pivot sont les deux bouts d'un segment de clôture : le portail *est* ce segment, et la
clôture doit s'y **ouvrir**, faute de quoi le grillage traverse le vantail.

**Un ciel ne s'ajuste pas par un polynôme.** Un modèle global — degré 1 en x, 2 en y —
laisse un résidu d'écart-type 12 à 15 niveaux : un pixel de ciel sur cinq dépassait le
seuil d'effacement et se faisait repeindre treize niveaux trop clair, dans la forme exacte
de l'arbre effacé. Le fantôme, c'était le ciel repeint, pas la branche survivante. Le fond
se prend **localement**, par convolutions normalisées du plus fin au plus grossier :
erreur médiane 8,3 → 1,5. Et le support se nettoie **par la teinte**, jamais par la
clarté : un peuplier d'hiver au soleil est plus *clair* que le ciel (190 contre 170), mais
un ciel tient dans six niveaux de R−B (−104 à −98) là où le rideau d'arbres va de −82
à −19.

**Un bloc de fabricant dessine l'ouvrage et ses entrailles.** `BESS Skyray` porte 77
contours : le conteneur de 6,06 × 3,00 m, mais aussi sa paroi intérieure, trente-six
racks de 2,32 × 0,12 m et leur boulonnerie de 5 cm. Montés, cela faisait trente-huit
conteneurs empilés dans un seul — et la règle de nidification habituelle ne sait pas
trancher ici : elle tient le contour englobant pour une plateforme, ce qui est vrai d'une
dalle autour d'un poste et faux d'une paroi autour d'un rack, donc elle garderait les
racks et jetterait le conteneur. Ce qui sépare les deux cas se compte : le plus chargé
des **symboles de plan** du corpus en porte 10, le **dessin de produit** en porte 77.

**`virtual_entities` ne descend que d'un niveau.** Sur Sarnois IND10b le conteneur
batterie est imbriqué deux crans plus bas, dans `UNI_Batterie` puis `BESS Skyray` : sans
descendre, on monte l'enveloppe de 8,06 × 6,00 m, soit un conteneur 61 % trop grand, et
rien ne le signale.

**Un segment n'est pas un ouvrage.** Deux polylignes de *deux* points sur la couche de
refroidissement de Sarnois, longues de 8,944 m — c'est-à-dire exactement
`hypot(8,00 ; 4,00)`, les diagonales du rectangle voisin. Sans contour, `rectangle_mini`
rend `None`, le gabarit prend le relais, et chaque diagonale devient une réserve souple de
120 m³ : trois bâches là où le bilan en compte une.

**Une citerne souple se dessine en SPLINE**, parce qu'elle a physiquement des coins
arrondis — et `lecture_dxf` ne lisait pas les splines. La citerne de refroidissement de
120 m³ était donc purement absente des deux plans qui en portent une. Aplatie, elle mesure
11,70 × 9,32 m sur les deux, soit le gabarit UNITe (11,7 × 8,9, 104 m² au bilan) au
centimètre sur la longueur.

**Un heredoc Bash long se tronque.** Au-delà d'une centaine de lignes, écrire le fichier,
pas le coller dans le shell.

---

## Livraison vers le dossier DP

La pièce **DP 6 — Insertions paysagères** de `generateur-dp` compose une planche
par point de vue à partir de deux ou trois images : l'état actuel, le projet, et le
projet avec les mesures paysagères. `livrer_dp6.py` les y dépose.

```bash
python livrer_dp6.py exemples/casxcas/pose_4.json     exemples/casxcas/montage_vue4.jpg exemples/casxcas/montage_vue4_haie.jpg     --projet PV-Gannay-sur-Loire
```

Les deux outils ne partagent **aucun code** : `generateur-dp` vit sur cairo,
geopandas et Streamlit, le photomontage sur Blender et scipy. Le lien se résume à
des fichiers posés dans `projets/{nom}/DP_6/`, et comme l'application les écrit
sous leur propre nom, le nom est le seul canal :

```
vue{N}_1_etat_actuel.jpg
vue{N}_2_projet.jpg
vue{N}_3_mesures_paysageres.jpg
```

Un tri alphabétique groupe alors par vue et ordonne les volets. Le préfixe n'est
pas décoratif : sans lui, trois vues écriraient trois fois les mêmes trois noms.

**Les trois volets doivent partager le cadrage.** Les montages sont rognés de leur
bandeau GPS après composition ; l'état actuel l'est donc identiquement, et le
module refuse si les tailles ne concordent pas. Trois images qui ne se superposent
pas ne comparent plus rien, et cela ne se verrait qu'à l'impression du dossier.

## Installation

```bash
pip install -r requirements.txt
```

Blender 4.5.9 LTS séparément — il n'est pas une dépendance pip, voir `requirements.txt`.

Les **jeux d'essai ne sont pas dans le dépôt** : `exemples/` pèse 2,9 Go et porte des
plans, des photos de visite et des dossiers de permis de tiers. Ils restent sur OneDrive,
à leur place habituelle.

## Tests

```bash
python -m pytest test_geometrie.py -q
```

`test_geometrie.py` verrouille les conventions de repère par des **tests de mutation** :
six conventions cassées volontairement — sens de l'azimut, signe du tangage, signe du
roulis, sens de l'axe vertical, permutation Est/Nord, focale calculée sur le mauvais côté
du capteur. Les six sont détectées.

## Ce qui reste ouvert

- **La focale de Gannay n'est pas déterminée.** Aucun EXIF sur six clichés, la ligne
  d'arbres ne la contraint pas, les projections de clôture sont indiscernables entre 107
  et 293 m. Les montages partent d'un 26 mm supposé. Une seule distance connue dans le
  champ la trancherait.
- **Sur une vue rapprochée, le feuillage est hors domaine.** Les cartes font 18 à 40 cm :
  3 à 7 px à 180 m, mais jusqu'à 745 px à 1,7 m, où elles se lisent comme des plaques. Il
  faudrait une géométrie de feuille pour le premier mètre.
- **La position GPS d'un téléphone vaut 5 à 10 m.** Négligeable à 100-400 m, déterminante
  quand la clôture passe à 3,8 m.
- **La « zone de remise » du BESS est prise pour une aire durcie, pas pour un volume.**
  12,01 × 3,00 m sur les trois plans qui en portent une, soit l'empreinte exacte d'un
  conteneur 40 pieds — et c'est justement pourquoi le doute existe. Le bilan la compte en
  *surface* (« Zone de remise (36 m²) ») là où il compte les conteneurs en *nombre*, et la
  liste séparément du « local de stockage matériel », qui fait aussi 36 m². Le doute est
  assumé dans ce sens-là : monter un volume de 3 m de haut qui n'existe pas se voit sur un
  photomontage, poser une dalle plate là où le sol est nu ne se voit à aucune distance
  utile.
- **Le bac de rétention n'est pas monté du tout.** Son MTEXT dit « Bac de rétention
  120 m³ » : c'est un *creux* dans le sol, 16,90 × 3,00 m à Auzainvilliers. Le rendre en
  dalle surélevée de 4 cm serait un ressaut que le plan ne porte pas, et on n'a pas sa
  profondeur.
