#!/usr/bin/env python3
"""Reconstruit des tables en 3D depuis un contrat écrit à plat.

POURQUOI CE MODULE EXISTE
-------------------------
Un export HelioScope est **plat** : ses tables n'ont pas de Z, et c'est le Z
qui donne l'inclinaison. `lecture_contrat` les refusait donc, et un DXF n'y
changerait rien — `lecture_dxf` exige aussi des polylignes 3D. Le but étant de
produire les photomontages **sans DXF du bureau d'études**, il faut refaire ici
ce que le plan ne porte pas.

Rien n'est inventé : tout vient du contrat ou du modèle de terrain.

  - la POSITION et l'ÉTENDUE viennent des empreintes de modules, qui sont au
    contrat ;
  - l'INCLINAISON vient de `parametres.modules.inclinaison_deg` ;
  - la HAUTEUR DU BORD BAS vient de `parametres.structures.point_bas_m` quand
    le tableau du plan le porte ;
  - l'ALTITUDE DU SOL vient du RGE ALTI, sous chaque coin ;
  - et le SENS DE LA PENTE vient d'une règle physique, ci-dessous.

LE SENS DE LA PENTE NE SE DEVINE PAS, IL SE CONTRAINT
------------------------------------------------------
Le contrat ne dit nulle part vers où les modules descendent. Mais une centrale
de l'hémisphère nord tourne ses modules **vers le sud** : le bord bas est
toujours plus au sud que le bord haut, donc dans un azimut entre sud-est et
sud-ouest. C'est une règle physique, pas une statistique, et elle se vérifie
table par table au lieu de se supposer une fois pour toutes.

Une table dont aucun des deux bords n'a de composante sud est **refusée
bruyamment** : c'est le signe que le repère est faux, ou que l'export ne
représente pas ce qu'on croit. Mieux vaut un refus qu'une centrale montée à
l'envers, défaut qui ne saute pas aux yeux sur un rendu.

CE QU'EST UNE TABLE ICI
-----------------------
Le découpage du fabricant ne se retrouve pas toujours dans la géométrie : aux
Islettes, `pas_tables_m` vaut exactement la largeur d'un module, donc les
tables s'aboutent sans jeu et rien ne les sépare au sol. On regroupe donc les
modules par CONTIGUÏTÉ — le jeu entre deux tables, 0,49 m à Gannay, les sépare
quand il existe — et chaque bloc devient une `Table`, dont l'exporteur redérive
lui-même le nombre de colonnes. La géométrie rendue est la même dans les deux
cas ; seule la découpe logique change, et elle ne se voit pas.
"""
import math

import numpy as np

import lecture_dxf

#: Jeu, en metres, au-dela duquel deux modules ne sont plus du meme bloc.
#: Les joints font 1,2 cm, l'ecart entre tables 0,49 m a Gannay.
JEU_MAX = 0.10

#: Hauteur du bord bas, en metres, quand le contrat ne la porte pas. C'est le
#: standard UNITe, celui que le generateur applique en l'absence de tableau.
POINT_BAS_DEFAUT = 1.10

#: Azimut vers lequel la table descend. Le chef de projet l'a pose ainsi le
#: 24/09/2026 : « le bord bas est toujours plus au sud que le bord haut, les
#: tables sont tournees vers le sud, donc forcement SE, S ou SO ». On garde de
#: la marge autour de SE (135) et SO (225), mais l'est et l'ouest FRANCS sont
#: refuses : ils n'ont aucune composante sud, et les accepter revenait a ne
#: rien verifier.
CAP_BAS_MIN, CAP_BAS_MAX = 100.0, 260.0


class ErreurPente(Exception):
    """La pente d'une table ne descend pas vers le sud."""


def _rectangle(pts):
    """Rectangle d'aire minimale d'un nuage : (centre, u, v, long_u, long_v)."""
    a = np.asarray(pts, float)
    best = None
    for i in range(len(a)):
        d = a[(i + 1) % len(a)] - a[i]
        n = math.hypot(*d)
        if n < 1e-9:
            continue
        u = d / n
        v = np.array([-u[1], u[0]])
        pu, pv = a @ u, a @ v
        aire = float(np.ptp(pu)) * float(np.ptp(pv))
        if best is None or aire < best[0]:
            centre = u * (pu.min() + pu.max()) / 2 + v * (pv.min() + pv.max()) / 2
            best = (aire, centre, u, v, float(np.ptp(pu)), float(np.ptp(pv)))
    return best[1:] if best else None


def blocs_contigus(modules, jeu=JEU_MAX):
    """Regroupe les empreintes de modules qui se touchent. Rend des listes d'indices.

    Le voisinage se cherche par un arbre sur les centres, puis se confirme sur
    la distance reelle entre rectangles : deux modules de rangees voisines ont
    des centres a neuf metres, mais deux modules d'un meme bandeau sont a une
    largeur de module l'un de l'autre.
    """
    from scipy.spatial import cKDTree
    from shapely.geometry import Polygon

    polys = [Polygon(m) for m in modules]
    centres = np.array([[p.centroid.x, p.centroid.y] for p in polys])
    # rayon de recherche : la plus grande diagonale de module, plus le jeu
    diag = max(math.hypot(*(np.ptp(np.asarray(m, float), axis=0))) for m in modules)
    arbre = cKDTree(centres)
    paires = arbre.query_pairs(diag + jeu, output_type="ndarray")

    parent = list(range(len(polys)))

    def racine(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, j in paires:
        if polys[i].distance(polys[j]) <= jeu:
            ri, rj = racine(int(i)), racine(int(j))
            if ri != rj:
                parent[ri] = rj

    groupes = {}
    for i in range(len(polys)):
        groupes.setdefault(racine(i), []).append(i)
    return list(groupes.values())


def _quad_3d(centre, u, v, long_u, long_v, sol, point_bas, inclinaison):
    """Les quatre sommets d'une table, dans l'ordre haut, haut, bas, bas.

    `v` pointe vers un des deux bords ; on choisit celui qui DESCEND, c'est-a-
    dire celui qui va vers le sud.
    """
    cap_v = math.degrees(math.atan2(v[0], v[1])) % 360.0
    if CAP_BAS_MIN <= cap_v <= CAP_BAS_MAX:
        vers_bas = v
    elif CAP_BAS_MIN <= (cap_v + 180.0) % 360.0 <= CAP_BAS_MAX:
        vers_bas = -v
    else:
        raise ErreurPente(
            f"aucun des deux bords ne descend vers le sud : l'axe de pente "
            f"pointe a {cap_v:.1f} et {(cap_v + 180) % 360:.1f} degres. Le "
            f"repere du contrat est suspect — une centrale de l'hemisphere "
            f"nord tourne ses modules au sud.")

    demi_u, demi_v = u * long_u / 2, vers_bas * long_v / 2
    bas = [centre + demi_v - demi_u, centre + demi_v + demi_u]
    haut = [centre - demi_v - demi_u, centre - demi_v + demi_u]
    monte = long_v * math.tan(math.radians(inclinaison))

    # ⚠️ L'ALTITUDE DU BORD HAUT SE DEDUIT DU BORD BAS, jamais du sol sous
    # lui. Une table est un plan RIGIDE, incline de `inclinaison` sur
    # l'horizontale ; ce sont les pieux qu'on recoupe pour suivre le terrain,
    # pas le panneau qui ondule. Prendre le sol sous le bord haut ajoutait la
    # pente du terrain a celle du panneau : mesure aux Islettes, l'inclinaison
    # ressortait entre 24,4 et 26,6 degres pour 25 declares.
    q = []
    for ph, pb in ((haut[0], bas[0]), (haut[1], bas[1])):
        z = float(sol(pb[0], pb[1])) + point_bas + monte
        q.append((float(ph[0]), float(ph[1]), z))
    for pb in (bas[1], bas[0]):
        q.append((float(pb[0]), float(pb[1]),
                  float(sol(pb[0], pb[1])) + point_bas))
    return q


def reconstruire(modules, parametres, sol, jeu=JEU_MAX, verbose=True):
    """Rend des `lecture_dxf.Table` depuis des empreintes de modules plates.

    `modules` : suite d'anneaux 2D en Lambert 93.
    `sol`     : fonction (x, y) -> altitude NGF.
    """
    mods = (parametres or {}).get("modules") or {}
    struct = (parametres or {}).get("structures") or {}
    inclinaison = float(mods.get("inclinaison_deg") or 0.0)
    if inclinaison <= 0:
        raise ErreurPente("le contrat ne donne pas d'inclinaison des modules")
    point_bas = float(struct.get("point_bas_m") or POINT_BAS_DEFAUT)
    gen = (parametres or {}).get("generalites") or {}
    cap_rangees = gen.get("azimut_rangees_l93_deg")
    cap_rangees = float(cap_rangees) if cap_rangees is not None else None

    groupes = blocs_contigus(modules, jeu)
    tables, refusees = [], 0
    for idx in groupes:
        pts = np.vstack([np.asarray(modules[i], float)[:, :2] for i in idx])
        r = _rectangle(pts)
        if r is None:
            continue
        centre, u, v, long_u, long_v = r
        # ⚠️ NE PAS PRENDRE LE GRAND COTE POUR LA RANGEE. Une table de Gannay
        # fait 6,87 x 6,93 m — dix-huit modules, six en travers sur trois en
        # profondeur — donc presque carree : la regle du plus grand cote y
        # prenait la profondeur pour la rangee, et les modules ressortaient
        # tournes vers l'ouest au lieu du sud.
        #
        # ⚠️ ET `azimut_rangees_l93_deg` EST LA DIRECTION D'ESPACEMENT DES
        # RANGEES, donc celle de la PENTE — pas celle dans laquelle elles
        # courent. Lu a l'envers, il donnait les deux sites face a l'ouest.
        # Verification : aux Islettes il vaut 1,9 deg et les rangees courent
        # est-ouest ; a Gannay 0,4 deg, et la note du lot 2ter dit « six
        # modules d'est en ouest ».
        if cap_rangees is not None:
            ecart = [abs((math.degrees(math.atan2(a[0], a[1])) - cap_rangees
                          + 90) % 180 - 90) for a in (u, v)]
            if ecart[0] < ecart[1]:
                u, v, long_u, long_v = v, u, long_v, long_u
        elif long_v > long_u:
            u, v, long_u, long_v = v, u, long_v, long_u
        try:
            q = _quad_3d(centre, u, v, long_u, long_v, sol, point_bas,
                         inclinaison)
        except ErreurPente:
            refusees += 1
            continue
        cols = max(1, int(round(long_u / float(mods.get("largeur_m") or 1.0))))
        rangs = max(1, int(round(long_v / float(
            mods.get("longueur_projetee_m") or long_v))))
        tables.append(lecture_dxf.Table(q=q, rows=rangs, cols=cols))

    if refusees:
        raise ErreurPente(
            f"{refusees} bloc(s) sur {len(groupes)} n'ont aucun bord qui "
            f"descende vers le sud. Voir la regle dans ce module : une table "
            f"montee a l'envers ne se voit pas sur un rendu.")
    if verbose:
        haut = max(t.q[0][2] - t.q[3][2] for t in tables) if tables else 0.0
        print(f"  tables reconstruites : {len(tables)} blocs depuis "
              f"{len(modules)} modules, inclinaison {inclinaison:.0f} deg, "
              f"bord bas a {point_bas:.2f} m, denivele max {haut:.2f} m")
    return tables
