#!/usr/bin/env python3
"""Dépose les montages sous la convention attendue par la pièce DP 6.

CE QUE DP 6 ATTEND
------------------
`generateur-dp`, dans `dp_socle/planches/dp6_insertions.py`, compose une planche
par point de vue à partir de **deux ou trois images**, dans cet ordre relevé sur
le dossier de référence :

  1. l'image brute, l'état actuel, le projet absent ;
  2. la même image avec le photomontage ;
  3. le même photomontage avec l'aménagement paysager.

Le troisième n'existe que si le projet porte des mesures paysagères. Les deux
premiers sont indissociables : c'est la comparaison avant/après qui fait la
pièce, et DP 6 refuse une vue à une seule image plutôt que de la compléter en
silence.

POURQUOI UNE CONVENTION DE NOMS, ET PAS UN APPEL DE FONCTION
-------------------------------------------------------------
Les deux outils n'ont rien en commun côté dépendances : `generateur-dp` vit sur
cairo, geopandas et Streamlit ; le photomontage sur Blender, scipy et un
pipeline de rendu. Les coupler imposerait à chacun les contraintes d'
installation de l'autre, pour un lien qui se résume à des fichiers posés dans
un dossier.

L'application écrit les photographies déposées **sous leur propre nom** dans
`projets/{nom}/DP_6/`. Le nom est donc le seul canal, et il doit porter deux
choses : à quel point de vue l'image appartient, et quel volet elle est.

    vue{N}_1_etat_actuel.jpg
    vue{N}_2_projet.jpg
    vue{N}_3_mesures_paysageres.jpg

Un tri alphabétique groupe alors par vue et ordonne les volets. Sans le
préfixe, trois vues écriraient trois fois les mêmes trois noms — c'est l'erreur
que j'avais d'abord proposée.

LE PIÈGE : LES TROIS VOLETS DOIVENT AVOIR LE MÊME CADRAGE
----------------------------------------------------------
Les montages sont rognés de leur bandeau GPS après composition. L'état actuel
doit l'être **identiquement**, sinon DP 6 empile trois images qui ne se
superposent pas, et la comparaison avant/après ne compare plus rien. C'est pour
cela que ce module rogne la photo lui-même au lieu de la copier, et qu'il
refuse si les tailles ne concordent pas.

Usage :
    python livrer_dp6.py <pose.json> <montage.jpg> [montage_haie.jpg] \\
        --projet PV-Gannay --vue 4
"""
import argparse
import json
import shutil
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent

#: Dépôt voisin, dans l'arborescence habituelle. Se surcharge par `--dossier`.
DEPOT_DP = HERE.parent / "generateur-dp"

#: Les trois volets, dans l'ordre de la pièce.
VOLETS = ("1_etat_actuel", "2_projet", "3_mesures_paysageres")


class ErreurLivraison(Exception):
    """La livraison ne peut pas se faire telle quelle."""


def _rogner(image, rogner):
    """Coupe le bandeau, comme `monter.py` le fait sur les montages."""
    if not rogner:
        return image
    return image.crop((0, 0, image.width, int(rogner)))


def livrer(pose, montage, montage_haie=None, projet=None, vue=None,
           dossier=None, verbose=True):
    """Écrit les deux ou trois volets d'un point de vue, et rend leurs chemins.

    `pose` est le JSON de pose de la vue : il porte le nom de la photo et le
    `rogner` qui a servi aux montages.
    """
    pose = Path(pose)
    p = json.loads(pose.read_text(encoding="utf-8"))
    photo = pose.parent / p["photo"]
    if not photo.exists():
        raise ErreurLivraison(f"photo introuvable : {photo}")
    if not projet:
        raise ErreurLivraison(
            "nom de projet manquant : il designe le dossier "
            "projets/{nom}/DP_6/ de generateur-dp, et ne se devine pas.")
    vue = str(vue if vue is not None else pose.stem.replace("pose_", ""))

    cible = Path(dossier) if dossier else DEPOT_DP / "projets" / projet / "DP_6"
    cible.mkdir(parents=True, exist_ok=True)

    brut = _rogner(Image.open(photo).convert("RGB"), p.get("rogner"))
    sources = [None, Path(montage)]
    if montage_haie:
        sources.append(Path(montage_haie))

    ecrits = []
    for i, (volet, src) in enumerate(zip(VOLETS, sources)):
        sortie = cible / f"vue{vue}_{volet}.jpg"
        if src is None:
            brut.save(sortie, quality=95)
            taille = brut.size
        else:
            if not src.exists():
                raise ErreurLivraison(f"montage introuvable : {src}")
            im = Image.open(src).convert("RGB")
            # MÊME CADRAGE OU RIEN. Un volet qui ne se superpose pas aux autres
            # casse la comparaison avant/après, qui est tout l'objet de la
            # pièce — et cela ne se verrait qu'à l'impression du dossier.
            if im.size != brut.size:
                raise ErreurLivraison(
                    f"{src.name} fait {im.size}, l'etat actuel {brut.size}. "
                    "Les volets d'une meme vue doivent partager le cadrage ; "
                    "verifier `rogner` dans la pose.")
            shutil.copyfile(src, sortie)
            taille = im.size
        ecrits.append(sortie)
        if verbose:
            print(f"  {sortie.name}  {taille[0]} x {taille[1]}")

    if verbose:
        n = len(ecrits)
        print(f"vue {vue} : {n} volet(s) dans {cible}")
        if n == 2:
            print("  pas de volet « mesures paysageres » : DP 6 laissera son "
                  "emplacement vide et le signalera. C'est normal si le projet "
                  "n'en porte pas.")
    return ecrits


def _args():
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("pose")
    a.add_argument("montage")
    a.add_argument("montage_haie", nargs="?")
    a.add_argument("--projet", required=True,
                   help="nom du dossier dans projets/ de generateur-dp")
    a.add_argument("--vue", help="repere de la vue (defaut : d'apres la pose)")
    a.add_argument("--dossier", help="cible explicite, au lieu du depot voisin")
    return a.parse_args()


if __name__ == "__main__":
    o = _args()
    livrer(o.pose, o.montage, o.montage_haie, projet=o.projet, vue=o.vue,
           dossier=o.dossier)
