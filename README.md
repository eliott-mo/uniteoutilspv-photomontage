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

**Un heredoc Bash long se tronque.** Au-delà d'une centaine de lignes, écrire le fichier,
pas le coller dans le shell.

---

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
