#!/usr/bin/env python3
"""Lecture du contrat de `generateur-dp` : `geometries.gpkg` + `projet.json`.

POURQUOI CE MODULE REMPLACE LA LECTURE DE PLAN
----------------------------------------------
Jusqu'ici chaque projet apportait son propre code d'ingestion : lecture du DXF,
calage du plan PDF, relevé des ouvrages. Pour Gannay cela a fait 1 580 lignes
écrites pour un seul site, dont environ 640 pour la seule ingestion.

`generateur-dp` produit déjà, pour chaque dossier, un **contrat versionné** que
trois producteurs écrivent à l'identique — l'import DXF HelioScope (lot 2),
l'import du plan du BE (lot 2bis) et l'import du plan PDF (lot 2ter). Un test
de ce dépôt-là leur interdit de diverger. Il n'y a donc aucune raison de relire
un plan ici : on lit le contrat, et l'ingestion disparaît du photomontage.

INTERCHANGEABLE AVEC `lecture_dxf.lire`
---------------------------------------
`lire()` rend une `lecture_dxf.Scene`, avec les mêmes tables et les mêmes
catégories de lignes. Tout l'aval — `montage`, `exporter_blender`,
`composer_blender` — fonctionne sans modification. C'est la condition pour que
le changement de source ne devienne pas un chantier.

CE QUE LE CONTRAT DONNE, ET QU'UN DXF NE DONNAIT PAS
-----------------------------------------------------
Le Z par sommet, donc l'inclinaison réelle de chaque table sans reconstruction.
Les cotes normalisées des ouvrages, avec `ordre_cotes` qui dit le sens de
chaque nombre. Les standards UNITe du projet. Et le géoréférencement, déjà fait
et vérifié en amont — pour HelioScope, par la résolution de l'entité IMAGE qui
encode le zoom Web Mercator, avec son test d'intégrité sur la partie
fractionnaire.

Usage :
    python lecture_contrat.py <dossier_sortie>
"""
import json
import math
import re
from pathlib import Path

import fiona
import numpy as np

import lecture_dxf

#: Version du contrat que ce module sait lire. Au-delà, il refuse : une version
#: plus récente peut avoir changé une colonne sans prévenir, et lire quand même
#: produirait un montage faux sans erreur visible.
VERSION_LUE = 2

#: Systeme attendu. Tout le traitement geometrique se fait en Lambert 93, ici
#: comme dans `generateur-dp`.
CRS_ATTENDU = "EPSG:2154"

#: Catégorie du contrat -> catégorie de `lecture_dxf.MOTIFS_LIGNES`.
#:
#: Plusieurs catégories du contrat tombent dans la même ici, et c'est voulu :
#: le dossier DP distingue la piste lourde de la légère, l'existante de celle à
#: créer, parce que son tableau bilan les compte séparément. Le photomontage,
#: lui, les dessine toutes en grave — la nuance de revêtement se rattrape par
#: le nom de calque, que `montage.SOL_TEINTES` va chercher (« lourde »,
#: « legere », « voirie »…). C'est pourquoi `couche` porte le calque d'origine
#: et non la catégorie.
CORRESPONDANCE = {
    "cloture": "cloture",
    "portail": "portail",
    "portail_exploitant": "portail",
    "haie": "haie",
    "haie_existante": "haie",
    # ARBRE ISOLE, ET NON HAIE. Le plan de Sarnois porte 290 polygones sur le
    # calque « PVcase Trees » : les verser dans `haie` ferait dessiner 290
    # haies linéaires là où il y a des houppiers. Ils gardent donc leur propre
    # catégorie — rien ne la dessine aujourd'hui, mais elle sort du contrat
    # complète, et elle comptera : de la végétation existante est un masque de
    # premier plan en puissance.
    "arbre_existant": "arbre",
    "piste_lourde": "piste",
    "piste_legere": "piste",
    "piste_lourde_existante": "piste",
    "piste_lourde_a_creer": "piste",
    "voirie": "voirie",
    "plateforme": "plateforme",
    "aire_grutage": "plateforme",
    "local_technique": "local",
    "pdl": "pdl",
    "ptr": "pdl",
    "pdl_ptr": "pdl",
    "bache_incendie": "sdis",
    "aire_aspiration": "sdis",
}

#: Catégories sciemment écartées, avec leur raison. Elles sont listées pour que
#: `lire()` puisse dire ce qu'il a ignoré — une couche qui disparaît en silence
#: est la façon la plus sûre de produire un montage incomplet sans le savoir.
ECARTEES = {
    "modules_pv": "trop fin : le module se redessine depuis la table",
    "zone_implantation_pv": "trace a main levee, ne suit pas le parcellaire",
    "recul_implantation": "limite administrative, rien a dessiner",
    "zone_evitee": "limite administrative, rien a dessiner",
    "ligne_coupe": "sert a la coupe du dossier DP, pas au montage",
    "espace_vert": "sans volume : le sol du site le couvre deja",
    "limite_paddock": "cloture legere non modelisee a ce jour",
    "zone_contention": "sans volume modelise a ce jour",
    "bac_equarrissage": "sans volume modelise a ce jour",
    "citerne_refroidissement": "sans volume modelise a ce jour",
    "zone_remise": "sans volume modelise a ce jour",
    "bess": "sans volume modelise a ce jour",
    # INSTALLATIONS DE CHANTIER : portees au dossier DP, qui doit les declarer,
    # mais absentes d'un montage d'insertion paysagere, lequel montre l'etat
    # ACHEVE. Sur Sarnois elles pesaient 46 objets.
    "base_vie": "installation de chantier, temporaire",
    "stockage_chantier": "installation de chantier, temporaire",
    "bac_retention": "sans volume modelise a ce jour",
}


class ErreurContrat(Exception):
    """Le contrat ne peut pas être lu tel quel."""


class ErreurVersionContrat(ErreurContrat):
    pass


class ErreurTablesAbsentes(ErreurContrat):
    pass


class ErreurRepereContrat(ErreurContrat):
    pass


class ErreurAltitudeAbsente(ErreurContrat):
    pass


def parametres(dossier):
    """Le `projet.json` du dossier, après contrôle de version."""
    dossier = Path(dossier)
    chemin = dossier / "projet.json"
    if not chemin.exists():
        raise ErreurContrat(
            f"pas de projet.json dans {dossier} : ce n'est pas un dossier de "
            "sortie de generateur-dp")
    p = json.loads(chemin.read_text(encoding="utf-8"))
    v = p.get("version_contrat")
    if not isinstance(v, int) or v > VERSION_LUE:
        raise ErreurVersionContrat(
            f"contrat en version {v}, ce module lit jusqu'a {VERSION_LUE}. "
            "Mettre a jour le photomontage avant de lire ce dossier — une "
            "colonne a pu changer de sens sans que rien ne le signale.")
    return p


def _formats(p):
    """Les formats de table déclarés, sous la forme [(rangs, colonnes), …].

    `format_table` vaut « 2V26 », ou « 2V26/2V13 » quand le projet mêle deux
    longueurs. V pour portrait, H pour paysage — l'orientation ne change pas le
    découpage en rangs et colonnes.
    """
    brut = str(((p.get("parametres") or {}).get("structures") or {})
               .get("format_table") or "")
    out = []
    for morceau in brut.replace(" ", "").split("/"):
        m = re.match(r"(\d+)[VH](\d+)", morceau, re.IGNORECASE)
        if m:
            out.append((int(m.group(1)), int(m.group(2))))
    return out


def _longueur_rang(q):
    """Longueur de la table le long de ses rangs, en mètres."""
    a, b = np.array(q[0], float), np.array(q[1], float)
    return float(np.linalg.norm(a[:2] - b[:2]))


def _attribuer_formats(tables, formats, verbose=True):
    """Donne à chaque table ses rangs et colonnes, d'après sa longueur.

    Le contrat déclare les formats du projet mais ne dit pas lequel s'applique
    à quelle table — cette information n'a pas de raison d'y être, le dossier
    DP n'en a pas l'usage. La géométrie, elle, le dit : une table de 26
    colonnes est deux fois plus longue qu'une de 13.

    On déduit donc la largeur d'un module de la table la plus longue rapportée
    au plus grand format déclaré, puis on attribue à chaque table le format
    dont la longueur prédite est la plus proche. Aucune constante extérieure
    n'entre ici : tout se mesure sur le lot de tables lui-même.
    """
    if not formats:
        return
    longueurs = np.array([_longueur_rang(t.q) for t in tables])
    rangs, colonnes = max(formats, key=lambda f: f[1])
    pas = longueurs.max() / colonnes
    compte = {}
    for t, L in zip(tables, longueurs):
        r, c = min(formats, key=lambda f: abs(f[1] * pas - L))
        t.rows, t.cols = r, c
        compte[(r, c)] = compte.get((r, c), 0) + 1
    if verbose:
        detail = ", ".join(f"{n} x {r}V{c}" for (r, c), n in sorted(compte.items()))
        print(f"  formats : {detail} (module deduit a {pas:.3f} m)")


def _quad(coords):
    """Les 4 sommets d'un anneau, dans l'ordre haut, haut, bas, bas.

    Le contrat les écrit déjà dans cet ordre — vérifié sur les 90 tables de
    Sarnois — mais `lecture_dxf` lève si l'ordre est autre, et la vérification
    coûte moins cher que le diagnostic.
    """
    q = [tuple(float(v) for v in p[:3]) for p in coords[:4]]
    if len(q) != 4:
        raise ErreurContrat(f"anneau de table a {len(q)} sommets, 4 attendus")
    z = [p[2] for p in q]
    if min(z[:2]) > max(z[2:]) - 1e-6:
        return q
    # Réordonner : les deux plus hauts d'abord, en gardant leur adjacence.
    ordre = sorted(range(4), key=lambda i: -z[i])
    hauts = sorted(ordre[:2])
    bas = [i for i in range(4) if i not in hauts]
    # les bas dans l'ordre qui fait face aux hauts (le quad reste convexe)
    return [q[hauts[0]], q[hauts[1]], q[bas[1]], q[bas[0]]]


def lire(dossier, verbose=True):
    """Lit un dossier de sortie de `generateur-dp` et renvoie une `Scene`."""
    dossier = Path(dossier)
    p = parametres(dossier)
    gpkg = dossier / "geometries.gpkg"
    if not gpkg.exists():
        raise ErreurContrat(f"pas de geometries.gpkg dans {dossier}")

    couches = set(fiona.listlayers(gpkg))
    if "tables_pv" not in couches:
        raise ErreurTablesAbsentes(
            f"aucune couche 'tables_pv' dans {gpkg.name} : le photomontage ne "
            "sait pas monter une scene sans tables.")

    tables = []
    with fiona.open(gpkg, layer="tables_pv") as src:
        if str(src.crs) != CRS_ATTENDU:
            raise ErreurRepereContrat(
                f"couche tables_pv en {src.crs}, {CRS_ATTENDU} attendu. Tout "
                "le traitement geometrique se fait en Lambert 93.")
        for f in src:
            anneau = f["geometry"]["coordinates"][0]
            if len(anneau[0]) < 3:
                raise ErreurAltitudeAbsente(
                    "geometrie de table sans Z. Le photomontage a besoin de "
                    "l'altitude par sommet pour poser l'inclinaison ; un "
                    "contrat ecrit a plat n'est pas exploitable ici.")
            tables.append(lecture_dxf.Table(q=_quad(anneau)))
    if not tables:
        raise ErreurTablesAbsentes(f"couche 'tables_pv' vide dans {gpkg.name}")
    _attribuer_formats(tables, _formats(p), verbose)

    lignes, ignorees = {}, {}
    for couche in sorted(couches - {"tables_pv"}):
        cat = CORRESPONDANCE.get(couche)
        if cat is None:
            with fiona.open(gpkg, layer=couche) as src:
                n = len(src)
            if n:
                ignorees[couche] = n
            continue
        with fiona.open(gpkg, layer=couche) as src:
            for f in src:
                g = f["geometry"]
                for pts in _anneaux(g):
                    lignes.setdefault(cat, []).append({
                        "pts": [(float(x), float(y)) for x, y, *_ in pts],
                        "fermee": g["type"] in ("Polygon", "MultiPolygon"),
                        # LE CALQUE D'ORIGINE, et non la categorie : c'est lui
                        # que `montage.SOL_TEINTES` interroge pour distinguer
                        # une voie lourde d'une piste legere.
                        "couche": f["properties"].get("calque") or couche,
                    })

    if verbose:
        print(f"contrat {dossier.name} | origine {p.get('origine')} | "
              f"version {p.get('version_contrat')}")
        print(f"  {len(tables)} tables")
        print("  lignes : " + (", ".join(f"{k}:{len(v)}" for k, v in
                                         sorted(lignes.items())) or "aucune"))
        if ignorees:
            detail = ", ".join(
                f"{c} ({n}, {ECARTEES.get(c, 'categorie inconnue de ce module')})"
                for c, n in sorted(ignorees.items()))
            print(f"  ECARTEES : {detail}")

    return lecture_dxf.Scene(tables=tables, lignes=lignes, topo=None,
                             source=str(dossier))


def _anneaux(g):
    """Les suites de sommets d'une géométrie, quel que soit son type."""
    t, c = g["type"], g["coordinates"]
    if t == "Polygon":
        return list(c)
    if t == "MultiPolygon":
        return [a for poly in c for a in poly]
    if t == "LineString":
        return [c]
    if t == "MultiLineString":
        return list(c)
    if t == "Point":
        return [[c]]
    return []


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(2)
    scn = lire(sys.argv[1])
    print()
    print(scn.resume())
