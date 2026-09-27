#!/usr/bin/env python3
"""Où vivent les entrées et les sorties d'un projet. Un seul endroit le dit.

LA CONVENTION, ARRETEE LE 27/09/2026
-------------------------------------
    projets/{NOM}/                 les ENTREES, telles que reçues
        contrat/PV-xxx/            geometries.gpkg + projet.json
        *.jpg                      les photos SORTIES DU TELEPHONE
        Photos géolocalisées.html  la carte photos-geoloc
    projets/{NOM}/montages/        tout ce que la chaîne produit

Le travail va donc **à côté de ses entrées**, et non dans un dossier temporaire :
il survit à la session, il s'archive d'un bloc, et on n'a qu'un dossier à ouvrir
pour voir ensemble le contrat, les photos, la page de calage, les rendus et les
montages qui en sont sortis.

`projets/` est exclu du dépôt — ce sont des données de client — donc rien de
tout cela ne part sur GitHub.

CE QUI N'EST PAS ICI
--------------------
La LIVRAISON. Les montages finis ne restent pas dans `montages/` : `livrer_dp6`
les dépose sous `../generateur-dp/projets/{NOM}/DP_6/`, aux trois noms que la
planche DP 6 sait lire. `montages/` est l'atelier, pas l'étagère.

POURQUOI UN MODULE POUR SI PEU
-------------------------------
Parce que la version precedente de cette convention n'existait que dans la tête
de celui qui lançait les commandes, et que les sorties partaient dans un dossier
temporaire efface a la fin de la session. Avec quinze projets a monter, une
convention non ecrite est une convention perdue.
"""
from pathlib import Path

RACINE = Path(__file__).resolve().parent

#: Ou vivent les dossiers de projet. Exclu du depot (voir `.gitignore`).
PROJETS = RACINE / "projets"

#: Le sous-dossier de travail, arrete avec le chef de projet le 27/09/2026.
ATELIER = "montages"


class ProjetIntrouvable(Exception):
    """Aucun dossier de projet ne correspond, ou plusieurs."""


def projet(nom):
    """Dossier d'un projet, designe par un bout de son nom.

    Les dossiers portent leur numero de departement — « 03. Gannay-sur-Loire »,
    « 88. Auzainvilliers » — qu'on n'a pas envie de retaper. On accepte donc
    n'importe quel fragment, pourvu qu'il ne designe qu'un seul projet.

    ⚠️ UN FRAGMENT AMBIGU EST UNE ERREUR, PAS UN CHOIX. Ecrire dans le mauvais
    projet ne se voit pas : les fichiers ont les memes noms d'un projet a
    l'autre, et un montage depose au mauvais endroit y ressemble a un montage.
    """
    if not PROJETS.is_dir():
        raise ProjetIntrouvable(f"{PROJETS} n'existe pas")
    p = Path(nom)
    if p.is_dir() and p.resolve().parent == PROJETS:
        return p.resolve()
    cible = str(nom).strip().lower()
    trouves = [d for d in sorted(PROJETS.iterdir())
               if d.is_dir() and cible in d.name.lower()]
    if len(trouves) == 1:
        return trouves[0]
    if not trouves:
        connus = ", ".join(d.name for d in sorted(PROJETS.iterdir())
                           if d.is_dir()) or "aucun"
        raise ProjetIntrouvable(
            f"aucun projet ne contient {nom!r}. Connus : {connus}")
    raise ProjetIntrouvable(
        f"{nom!r} designe {len(trouves)} projets : "
        + ", ".join(d.name for d in trouves))


def montages(nom, creer=True):
    """Dossier de travail d'un projet : `projets/{NOM}/montages/`."""
    d = projet(nom) / ATELIER
    if creer:
        d.mkdir(parents=True, exist_ok=True)
    return d


def contrat(nom):
    """Le contrat d'un projet : le dossier qui porte `geometries.gpkg`.

    On le cherche au lieu de l'exiger a un chemin fixe, parce qu'un zip du
    generateur se decompresse en `contrat/PV-xxx/` ou en `PV-xxx/` selon la
    facon dont on l'a ouvert, et que les deux sont raisonnables.
    """
    base = projet(nom)
    trouves = sorted(g.parent for g in base.rglob("geometries.gpkg"))
    if len(trouves) == 1:
        return trouves[0]
    if not trouves:
        raise ProjetIntrouvable(
            f"aucun geometries.gpkg sous {base.name} : le contrat de "
            f"generateur-dp n'y est pas, ou n'est pas decompresse.")
    raise ProjetIntrouvable(
        f"{len(trouves)} contrats sous {base.name} : "
        + ", ".join(str(d.relative_to(base)) for d in trouves))


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        n = sys.argv[1]
        print(f"projet   : {projet(n)}")
        print(f"montages : {montages(n, creer=False)}")
        try:
            print(f"contrat  : {contrat(n)}")
        except ProjetIntrouvable as e:
            print(f"contrat  : {e}")
    else:
        for d in sorted(PROJETS.iterdir()):
            if d.is_dir():
                print(f"  {d.name}")
