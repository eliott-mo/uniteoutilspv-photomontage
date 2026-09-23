# Provenance et licence des textures

Ce dossier ne contient que des ressources dont la licence autorise la diffusion
d'images rendues dans un dossier public — une étude d'impact ou une demande de
permis de construire est consultable par des tiers, il faut donc que la licence
le permette explicitement.

## LeafSet024 — ambientCG

| | |
|---|---|
| Source | <https://ambientcg.com/view?id=LeafSet024> |
| Licence | **CC0 1.0** (domaine public) |
| Usage commercial | oui |
| Attribution | non requise |
| Redistribution du fichier | autorisée |
| Téléchargé le | 21/09/2026, archive `LeafSet024_1K-PNG.zip` |
| Dimensions réelles | 40 × 40 cm pour 1024 px, soit 3 × 3 feuilles d'environ 12 cm |

Fichiers conservés : `LeafSet024_Color.png` et `LeafSet024_Opacity.png`. Les
cartes de normale, de rugosité et de déplacement n'ont pas été retenues : à
17 m une feuille couvre cinq pixels, leur relief ne se voit pas et elles
pèsent 6 Mo.

Espèce : feuille ovale dentée, du type charme (*Carpinus betulus*) ou noisetier
(*Corylus avellana*) — les essences d'une haie champêtre picarde. Le choix
s'est fait sur la forme, ambientCG ne documentant pas l'espèce.

## feuilles_touffe_* — dérivé

Produits par [`../atlas_feuilles.py`](../atlas_feuilles.py) à partir des
fichiers ci-dessus, dont ils héritent la licence CC0. La grille 3 × 3 d'origine
se lisait comme une trame de pois sur la haie rendue ; le script redécoupe les
neuf feuilles et les redistribue en désordre, ce qui porte au passage la
couverture de 42 à 64 %.

Ces deux fichiers sont **reproductibles** : les régénérer d'une commande suffit,
il n'est pas nécessaire de les archiver précieusement.

```bash
python atlas_feuilles.py
```

## Ces fichiers ne sont PAS le motif par défaut

Comparaison faite entre les deux rendus de la planche à 17 m, le motif
**calculé** (`materiaux_proc._alpha_touffe`) tient mieux la distance que la
feuille photographiée. La raison est une question de forme, pas de qualité
d'image : les feuilles de LeafSet024 sont **ovales**, et à 17 m un ovale de
cinq pixels rend un aplat, là où une feuille **lobée** accroche la lumière par
ses découpes. C'est le jugement d'Eliott Moreau du 21/09/2026, et il est
conforme à ce qu'on voit.

L'atlas reste disponible : poser `atlas_feuilles` à vrai dans les matériaux de
la scène. Il redeviendrait le meilleur choix avec une planche d'essence à
feuille **découpée** — érable champêtre, aubépine, viorne — ou pour un point de
vue nettement plus rapproché, où l'ovale reprendrait le dessus.

## Sans ces fichiers

`materiaux_proc.feuillage_carte` retombe sur `_alpha_touffe`, une silhouette
calculée. Le dépôt reste donc utilisable si le dossier `textures/` est absent —
le rendu est seulement moins bon de près.
