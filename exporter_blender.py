#!/usr/bin/env python3
"""Exporte la scene du projet vers un JSON que Blender saura monter.

Le partage des roles est celui-ci et il ne doit pas bouger :

  - CE script connait le plan, le terrain et la pose. Il produit de la geometrie
    en metres, dans le repere local (E, N, Up) centre sous la camera, plus les
    parametres de prise de vue et d'eclairage.
  - `blender_rendu.py`, execute DANS Blender, ne connait rien du photovoltaique.
    Il monte des maillages, applique des materiaux et rend une image a fond
    transparent.
  - la composition sur la photo se fait ensuite, en numpy.

Le SOL est exporte comme capteur d'ombre : invisible au rendu, mais il recoit
les ombres portees, qui sont alors les seuls pixels opaques. C'est ce qui permet
de poser des ombres sur la vraie photo sans repeindre le terrain.

Usage :
    python exporter_blender.py 10 sortie.json
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

import lecture_dxf
import montage as M
import terrain
from camera import Camera

HERE = Path(__file__).resolve().parent
DOSSIER = HERE / "exemples" / "sarnois-B" / "reportage-BE"

PAS_SOL = 6.0                 # m, maille du capteur d'ombre
RAYON_SOL = 260.0             # m, portee du capteur d'ombre autour de la camera


def _quad(v, a, b, c, d):
    n = len(v)
    v.extend([a, b, c, d])
    return [n, n + 1, n + 2, n + 3]


LARGEUR_CADRE = 0.04          # m, aile du cadre aluminium d'un module


def geometrie_tables(scn, mnt, sol_abs):
    """Modules, cadres aluminium, panne et pieux verticaux.

    Les CADRES ne sont pas un detail decoratif : vus en rasant le long des
    rangees, chaque rangee masque la suivante et la nappe devient une tache
    uniforme. Ce sont les ailes d'aluminium, plus claires que le verre, qui
    dessinent les lignes entre rangees et rendent la nappe lisible.
    """
    mod, met = {"v": [], "f": []}, {"v": [], "f": []}
    cadre = {"v": [], "f": []}
    for t in scn.tables:
        q = M._ordonner(t.q)
        b0, b1, h1, h0 = q
        long_vec = b1 - b0
        L = float(np.linalg.norm(long_vec[:2]))
        pente = h0 - b0
        # plan de modules : 2 rangees x cols, avec le jeu reel
        cols = max(6, int(round(L / 1.15)))
        g = 0.01 / max(L, 1e-6)          # 2 cm entre modules, pas 20
        for i in range(cols):
            s0, s1 = i / cols + g, (i + 1) / cols - g
            for j in range(2):
                t0, t1 = j / 2 + 0.002, (j + 1) / 2 - 0.002
                p = [(b0 + long_vec * s) * (1 - tt) + (h0 + (h1 - h0) * s) * tt
                     for s, tt in ((s0, t0), (s1, t0), (s1, t1), (s0, t1))]
                mod["f"].append(_quad(mod["v"], *[list(x) for x in p]))
        # cadres : une aile le long du bord haut et du bord bas, plus les
        # montants lateraux de chaque module
        eh = pente / np.linalg.norm(pente) * LARGEUR_CADRE
        for bord, sens in ((h0, -1.0), (b0, 1.0)):
            d0 = bord
            d1 = bord + long_vec
            cadre["f"].append(_quad(cadre["v"], list(d0), list(d1),
                                    list(d1 + eh * sens), list(d0 + eh * sens)))
        el = long_vec / L * LARGEUR_CADRE
        for i in range(cols + 1):
            sM = min(max(i / cols, 0.0), 1.0)
            a0 = b0 + long_vec * sM
            a1 = h0 + (h1 - h0) * sM
            cadre["f"].append(_quad(cadre["v"], list(a0), list(a0 + el),
                                    list(a1 + el), list(a1)))
        # panne
        pa0 = b0 + pente * M.FRACTION_PIEU
        pa1 = b1 + (h1 - b1) * M.FRACTION_PIEU
        ep = np.array([0.0, 0.0, 0.18])
        met["f"].append(_quad(met["v"], list(pa0 - ep), list(pa1 - ep), list(pa1), list(pa0)))
        # pieux verticaux, a l'aplomb de la panne
        ex = long_vec / L
        lat = np.array([-ex[1], ex[0], 0.0]) * (M.LARGEUR_PIEU / 2)
        nb = max(2, int(round(L / M.ESPACEMENT_PIEUX)) + 1)
        for k in range(nb):
            haut = b0 + long_vec * ((k + 0.5) / nb) + pente * M.FRACTION_PIEU
            zs = sol_abs(haut[0], haut[1])
            for signe in (1, -1):               # deux faces, suffisant a cette echelle
                a = haut + lat * signe
                b = haut - lat * signe
                met["f"].append(_quad(met["v"],
                                      [a[0], a[1], zs], [b[0], b[1], zs],
                                      [b[0], b[1], haut[2]], [a[0], a[1], haut[2]]))
    return mod, met, cadre


def geometrie_cloture(scn, sol_abs, E0, N0, dmax=300.0, ouvertures=()):
    """Poteaux d'acacia (cylindres a 8 faces) et nappe de grillage.

    `ouvertures` : suite de (est, nord, rayon), une par portail. Le segment
    dont le milieu y tombe n'est pas monte, ni ses piquets. SANS CELA LE
    GRILLAGE TRAVERSE LE VANTAIL : sur la vue 4 de Saint-Cyr, le portail se
    lisait derriere sa propre cloture, a un metre du photographe.

    Un rayon PAR portail, et non un rayon commun cale sur le plus large :
    `exporter_gannay` avait deja releve qu'un rayon commun ouvre trop la
    cloture aux petits portails.
    """
    def _ouvert(x, y):
        return any(math.hypot(x - e, y - n) < r for e, n, r in ouvertures)

    bois = {"v": [], "f": []}
    # le grillage porte des UV EN METRES : la maille se dessine ensuite par une
    # texture procedurale, faute de quoi le quad est un mur plein.
    grillage = {"v": [], "f": [], "uv": []}
    for c in scn.lignes.get("cloture", []):
        pts = [(a, b) for a, b in c["pts"]]
        s0 = 0.0
        for i in range(len(pts) - 1):
            a = np.array(pts[i], float); b = np.array(pts[i + 1], float)
            L = math.hypot(*(b - a))
            if L < 0.2:
                continue
            if _ouvert((a[0] + b[0]) / 2, (a[1] + b[1]) / 2):
                s0 += L
                continue
            if math.hypot((a[0] + b[0]) / 2 - E0, (a[1] + b[1]) / 2 - N0) < dmax:
                za, zb = sol_abs(*a), sol_abs(*b)
                grillage["f"].append(_quad(grillage["v"],
                                           [a[0], a[1], za], [b[0], b[1], zb],
                                           [b[0], b[1], zb + M.HAUTEUR_CLOTURE],
                                           [a[0], a[1], za + M.HAUTEUR_CLOTURE]))
                grillage["uv"] += [[s0, 0.0], [s0 + L, 0.0],
                                   [s0 + L, M.HAUTEUR_CLOTURE], [s0, M.HAUTEUR_CLOTURE]]
                depart = math.ceil(s0 / M.PAS_PIQUET) * M.PAS_PIQUET - s0
                for s in np.arange(max(depart, 0.0), L, M.PAS_PIQUET):
                    q = a + (b - a) * (s / L)
                    if math.hypot(q[0] - E0, q[1] - N0) > dmax or _ouvert(*q):
                        continue
                    zs = sol_abs(q[0], q[1])
                    r = M.DIAM_POTEAU / 2
                    n = 8
                    for k in range(n):
                        t0 = 2 * math.pi * k / n
                        t1 = 2 * math.pi * (k + 1) / n
                        p0 = (q[0] + r * math.cos(t0), q[1] + r * math.sin(t0))
                        p1 = (q[0] + r * math.cos(t1), q[1] + r * math.sin(t1))
                        bois["f"].append(_quad(bois["v"],
                                               [p0[0], p0[1], zs - 0.05], [p1[0], p1[1], zs - 0.05],
                                               [p1[0], p1[1], zs + M.HAUTEUR_CLOTURE + 0.12],
                                               [p0[0], p0[1], zs + M.HAUTEUR_CLOTURE + 0.12]))
            s0 += L
    return bois, grillage


def couleur_du_sol(chemin_photo, horizon, bande=0.18):
    """Teinte du sol du site, relevee sur la photo SOUS l'horizon.

    `montage.couleur_prairie` ne retient que les pixels VERTS. C'est juste sur
    un cliche d'ete ; sur un cliche d'hiver il n'en trouve pas assez et retombe
    sur son defaut, un vert de prairie d'ete — mesure a Saint-Cyr : le sol
    rendu sortait a RGB 58/74/61 quand le sol reel de la photo est a 78/79/75
    pour l'herbe du talus et 137/112/95 pour la friche. Une nappe verte au
    milieu d'un paysage gris-brun se lit comme une pelouse peinte, et c'est ce
    qu'a vu le chef de projet.

    On prend donc la MEDIANE du sol tel qu'il est, quelle que soit sa couleur :
    l'herbe rase d'un site suit la saison du reste de l'image.
    """
    a = np.asarray(Image.open(chemin_photo).convert("RGB"), dtype=float)
    H = a.shape[0]
    v0 = int(min(H - 2, max(0, horizon)))
    v1 = int(min(H, v0 + bande * H))
    if v1 - v0 < 8:
        return [104.0, 116.0, 76.0]
    return [float(x) for x in np.median(a[v0:v1].reshape(-1, 3), axis=0)]


def sol_du_site(scn, sol_abs, marge=6.0, verbose=True):
    """Sol OPAQUE sous la NAPPE, et pas sur toute l'emprise.

    A QUOI IL SERT, ET DONC JUSQU'OU IL DOIT ALLER. Sa seule raison d'etre est
    de boucher ce qui, sinon, laisserait passer la photo : les jeux entre
    tables, qui se superposent d'une rangee a l'autre — elles ont toutes la
    meme phase — et font paraitre les panneaux translucides. Mesure a Gannay :
    39 % des pixels rendus avaient un alpha entre 0,05 et 0,95.

    Il n'a donc besoin de couvrir que l'emprise des TABLES, elargie de quelques
    metres. Etendu a toute l'enceinte, il pose au premier plan une grande
    surface lisse d'une seule teinte, que l'oeil lit comme une piste ou une
    plateforme — c'est ce qu'a vu le chef de projet sur PM4 de Saint-Cyr, ou le
    point de vue est a quatre metres de la cloture et ou l'enceinte occupe la
    moitie basse du cadre.

    Ni la teinte ni le grain n'y changent rien : le defaut n'est pas dans le
    materiau mais dans l'ETENDUE. Un sol qui s'arrete sous les tables laisse le
    premier plan a la photo, qui montre deja le couvert reel.

    L'emprise est l'enveloppe convexe des tables, dilatee de `marge`, puis
    RECOUPEE PAR LA CLOTURE : le sol du site ne deborde jamais de son site.
    """
    from shapely.geometry import MultiPoint, Polygon
    from shapely.ops import triangulate as _trianguler

    if not scn.tables:
        return None
    coins = [(float(p[0]), float(p[1])) for t in scn.tables for p in t.q]
    emprise = MultiPoint(coins).convex_hull.buffer(marge)
    lignes = scn.lignes.get("cloture") or []
    if lignes:
        cl = Polygon([(float(a), float(b)) for a, b in lignes[0]["pts"]])
        if cl.is_valid and cl.area > 0:
            emprise = emprise.intersection(cl)
    if emprise.is_empty:
        return None

    bloc = {"v": [], "f": []}
    for tri in _trianguler(emprise):
        # `triangulate` travaille sur l'enveloppe convexe : les triangles qui
        # sortent de l'emprise sont ecartes, sinon le sol deborde.
        if not emprise.contains(tri.centroid):
            continue
        n0 = len(bloc["v"])
        for x, y in list(tri.exterior.coords)[:3]:
            bloc["v"].append([float(x), float(y), sol_abs(x, y)])
        bloc["f"].append([n0, n0 + 1, n0 + 2])
    if verbose:
        print(f"  sol du site    {len(bloc['v']):6d} sommets, "
              f"{len(bloc['f']):6d} faces  ({emprise.area / 10000:.2f} ha, "
              f"emprise des tables + {marge:.0f} m)")
    return bloc if bloc["f"] else None


def capteur_ombre(sol_rel, rayon=RAYON_SOL, pas=PAS_SOL):
    """Nappe de terrain qui ne sert qu'a recevoir les ombres."""
    sol = {"v": [], "f": []}
    n = int(rayon / pas)
    for i in range(-n, n):
        for j in range(-n, n):
            x0, y0 = i * pas, j * pas
            x1, y1 = x0 + pas, y0 + pas
            if math.hypot(x0, y0) > rayon:
                continue
            sol["f"].append(_quad(sol["v"],
                                  [x0, y0, sol_rel(x0, y0)], [x1, y0, sol_rel(x1, y0)],
                                  [x1, y1, sol_rel(x1, y1)], [x0, y1, sol_rel(x0, y1)]))
    return sol


# ----------------------------------------------------------------------- haies
# Les 19 dossiers HOCH ne dessinent AUCUNE haie plantee dans leurs
# photomontages — verifie sur les 35 paires avant/apres. Il n'y a donc rien a
# copier, comme pour les locaux techniques. Ce qui fait lire une haie a 100 ou
# 400 m, ce n'est ni la feuille ni la branche, c'est :
#   - une CIME DECHIQUETEE : un volume extrude lisse se lit comme un objet en
#     forme de haie, pas comme une haie ;
#   - de fortes variations de valeur par touffes ;
#   - une silhouette qui laisse passer le ciel par endroits ;
#   - et surtout la TEINTE DE LA VEGETATION DE LA PHOTO, pas une couleur
#     choisie : c'est elle qui porte la lumiere et la saison du cliche.
PROFIL_HAIE = ((0.50, 0.00), (0.52, 0.22), (0.50, 0.44), (0.45, 0.64),
               (0.37, 0.80), (0.24, 0.93), (0.0, 1.0))


def geometrie_haie(scn, sol_abs, E0, N0, hauteur=2.0, largeur=1.5,
                   dmax=400.0, pas=0.35, graine=11, cartes=None,
                   densite=52.0, coeur=0.58, bois=None, espacement=1.05,
                   pied_coeur=0.09):
    """Haies du plan, en volume extrude a cime irreguliere.

    UV en metres : u le long de la haie, v l'abscisse du profil depuis le sol.
    Le materiau s'en sert pour eclaircir et trouer la cime.
    """
    rng = np.random.default_rng(graine)
    haie = {"v": [], "f": [], "uv": []}
    for c in scn.lignes.get("haie", []):
        pts = [np.array(p, float) for p in c["pts"]]
        # reechantillonnage a pas constant le long de la polyligne
        chemin, reste = [], 0.0
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            L = float(np.linalg.norm(b - a))
            if L < 1e-6:
                continue
            d = (b - a) / L
            s = reste
            while s < L:
                chemin.append((a + d * s, d))
                s += pas
            reste = s - L
        if len(chemin) < 2:
            continue
        # Cime bruitee. Les ECHELLES sont en METRES, pas en nombre de sections :
        # une periode de 5 sections faisait des bosses de 2,75 m, ce qui donne
        # un rocher. Une haie ondule lentement sur 8 a 20 m, et se herisse
        # finement tous les 0,6 a 1,2 m.
        n = len(chemin)
        s_m = np.arange(n) * pas
        h = np.ones(n)
        # BRUIT INTERPOLE, pas des sinusoides : une somme de sinus se repete et
        # donne un peigne regulier, qu'on reconnait immediatement pour du calcul.
        # Ici, des valeurs tirees au sort tous les `periode_m` metres, reliees
        # par une interpolation douce — donc irregulier a toutes les echelles.
        for periode_m, amp in ((0.8, 0.075), (2.4, 0.070), (9.0, 0.085), (24.0, 0.06)):
            noeuds = int(max(2, s_m[-1] / periode_m + 2))
            val = rng.normal(0, 1.0, noeuds)
            x = np.linspace(0, s_m[-1] if s_m[-1] > 0 else 1.0, noeuds)
            u = np.interp(s_m, x, val)
            # lissage en cosinus : evite les cassures aux noeuds.
            # Le noyau est BORNE par la longueur du brin : `np.convolve` en
            # mode "same" rend max(len(signal), len(noyau)) points, donc un
            # noyau plus long que le brin faisait echouer l'addition. Cela ne
            # se voyait pas a Sarnois, ou la haie fait 388 m d'un tenant ;
            # cela creve des qu'on la coupe en troncons de quelques metres.
            k = max(1, min(int(periode_m / pas / 3), (n - 1) // 2))
            noyau = np.hanning(2 * k + 1); noyau /= noyau.sum()
            h += amp * np.convolve(u, noyau, mode="same")
        h = np.clip(h, 0.55, 1.45)
        # DENSITE variable le long de la haie. Un semis uniforme rend un
        # crepi : un feuillage reel fait des masses denses et des trouees, a
        # l'echelle du metre. Meme procede que la cime.
        dens = np.ones(n)
        for periode_m, amp in ((1.4, 0.35), (4.5, 0.30), (13.0, 0.22)):
            noeuds = int(max(2, s_m[-1] / periode_m + 2))
            val = rng.normal(0, 1.0, noeuds)
            x = np.linspace(0, s_m[-1] if s_m[-1] > 0 else 1.0, noeuds)
            k = max(1, min(int(periode_m / pas / 3), (n - 1) // 2))
            noyau = np.hanning(2 * k + 1); noyau /= noyau.sum()
            dens += amp * np.convolve(np.interp(s_m, x, val), noyau, mode="same")
        dens = np.clip(dens, 0.15, 1.9)

        def section(k):
            q, d = chemin[k]
            lat = np.array([-d[1], d[0]])
            zs = sol_abs(q[0], q[1])
            out = []
            # Le coeur est fortement RETREci quand on seme des cartes : il ne
            # sert plus qu'a boucher la vue au travers. A 0,82 il englobait les
            # tiges plantees a +/- 0,45 de la largeur et les rendait invisibles ;
            # a 0,58 ce n'est plus qu'une echine derriere elles.
            r = coeur if cartes is not None else 1.0
            # Le coeur DEMARRE au-dessus du sol quand il y a des cartes : sinon
            # il forme, vu de cote, un mur continu sur toute la longueur, et les
            # tiges plantees devant lui s'y perdent faute de contraste. En le
            # relevant, elles se detachent sur le fond, comme au pied d'une
            # vraie haie encore jeune.
            v0 = pied_coeur if cartes is not None else 0.0
            for cote in (1, -1):
                for u, v in (PROFIL_HAIE if cote > 0 else PROFIL_HAIE[::-1]):
                    p = q + lat * (cote * u * largeur * r)
                    vv = v0 + v * (1.0 - v0)
                    out.append([p[0], p[1], zs + vv * hauteur * h[k] * r + v0 * 0.0])
            return out

        prec = None
        s_cum = 0.0
        for k in range(n):
            q, _ = chemin[k]
            if math.hypot(q[0] - E0, q[1] - N0) > dmax:
                prec = None
                s_cum += pas
                continue
            cur = section(k)
            if cartes is not None and k % max(1, int(0.40 / pas)) == 0:
                _semer_cartes(cartes, chemin[k], h[k], hauteur, largeur,
                              sol_abs, rng, densite * dens[k])
            if bois is not None and k % max(1, int(espacement / pas)) == 0:
                qq, dd = chemin[k]
                _plant(bois, qq, dd, sol_abs(qq[0], qq[1]), hauteur * h[k],
                       largeur, rng, baliveau=(rng.random() < 0.16),
                       cartes=cartes)
            if prec is not None:
                for j in range(len(cur) - 1):
                    haie["f"].append(_quad(haie["v"], prec[j], cur[j],
                                           cur[j + 1], prec[j + 1]))
                    vj = j / (len(cur) - 1)
                    vj1 = (j + 1) / (len(cur) - 1)
                    tj = 1.0 - abs(2 * vj - 1.0)       # 0 au sol, 1 a la cime
                    tj1 = 1.0 - abs(2 * vj1 - 1.0)
                    haie["uv"] += [[s_cum - pas, tj], [s_cum, tj],
                                   [s_cum, tj1], [s_cum - pas, tj1]]
            prec = cur
            s_cum += pas
    return haie


def _fut(bloc, a, b, r0, r1, n=5):
    """Fut effile entre deux points 3D, en prisme a `n` faces.

    Cinq faces suffisent : un tronc de haie fait 4 a 9 cm a 300 m, soit moins
    d'un demi-pixel de large. Ce qui compte est qu'il soit LA, pas qu'il soit rond.
    """
    a = np.asarray(a, float); b = np.asarray(b, float)
    axe = b - a
    L = float(np.linalg.norm(axe))
    if L < 1e-4:
        return
    axe /= L
    ref = np.array([0.0, 0.0, 1.0]) if abs(axe[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    e1 = np.cross(axe, ref); e1 /= np.linalg.norm(e1) or 1.0
    e2 = np.cross(axe, e1)
    for k in range(n):
        t0 = 2 * math.pi * k / n
        t1 = 2 * math.pi * (k + 1) / n
        p0 = e1 * math.cos(t0) + e2 * math.sin(t0)
        p1 = e1 * math.cos(t1) + e2 * math.sin(t1)
        bloc["f"].append(_quad(bloc["v"], list(a + p0 * r0), list(a + p1 * r0),
                               list(b + p1 * r1), list(b + p0 * r1)))


def _plant(bloc, q, d, zs, htot, largeur, rng, baliveau=False, cartes=None):
    """Un plant : une tige montante, ses charpentieres, et sa cime s'il s'agit
    d'un baliveau.

    Une haie champetre se plante en deux ou trois rangs decales, tous les metre
    environ. Un semis strictement regulier donne une PALISSADE, qu'on reconnait
    au premier coup d'oeil : il faut du jeu sur l'abscisse comme sur le rang.

    Un BALIVEAU est un petit arbre, pas une perche : sans couronne il rend un
    piquet mort au-dessus de la haie, et l'ensemble se lit comme un melange de
    haie basse et d'arbres morts sur tige.
    """
    lat = np.array([-d[1], d[0]])
    # jeu le long de la haie ET en travers : deux a trois rangs decales
    base = (q + d * rng.normal(0, 0.38)
            + lat * (rng.choice([-0.62, 0.0, 0.62]) + rng.normal(0, 0.24))
            * largeur * 0.5 + rng.normal(0, 0.05, 2))
    hf = htot * (rng.uniform(1.02, 1.22) if baliveau else rng.uniform(0.52, 0.78))
    r0 = (0.055 if baliveau else 0.028) * rng.uniform(0.75, 1.3)
    pied = np.array([base[0], base[1], zs - 0.05])

    # FUT EN PLUSIEURS TRONCONS, legerement devies. Un fut rigoureusement
    # rectiligne se lit comme un tuteur : c'etait le defaut des baliveaux, qui
    # montaient au-dessus de la haie comme des perches de chantier. Un tronc
    # reel serpente de quelques centimetres par metre.
    nseg = 5 if baliveau else 2
    derive = np.array([rng.normal(0, 0.10), rng.normal(0, 0.10)]) * hf / 3.0
    noeuds = [pied]
    for i in range(1, nseg + 1):
        t = i / nseg
        noeuds.append(np.array([
            base[0] + derive[0] * t + rng.normal(0, 0.030 * hf * t),
            base[1] + derive[1] * t + rng.normal(0, 0.030 * hf * t),
            zs + hf * t]))
    for i in range(nseg):
        _fut(bloc, noeuds[i], noeuds[i + 1],
             r0 * (1.0 - 0.60 * i / nseg), r0 * (1.0 - 0.60 * (i + 1) / nseg))
    sommet = noeuds[-1]

    def sur_fut(s):
        """Point du fut a l'abscisse relative `s`, en suivant ses troncons."""
        x = min(max(s, 0.0), 1.0) * nseg
        i = min(int(x), nseg - 1)
        return noeuds[i] + (noeuds[i + 1] - noeuds[i]) * (x - i)

    # charpentieres : elles partent du tiers superieur et s'ecartent, puis
    # se REDIVISENT. Une branche unique et droite reste un baton ; c'est la
    # bifurcation qui fait lire un arbre, meme a quelques pixels.
    # PORTEE des branches. Une charpentiere qui depasse l'enveloppe du
    # feuillage ne se lit pas comme une branche mais comme une RAYURE sur le
    # ciel : c'est ce qu'on voyait en haut a droite de la planche, ou une
    # secondaire filait a 3,9 m du tronc pour une couronne de 1,4 m de rayon.
    # On la borne donc au rayon de couronne pour un baliveau, et a la demi-
    # largeur de haie pour les autres.
    portee = hf * 0.26 if baliveau else min(hf * 0.26, largeur * 0.75)
    for _ in range(rng.integers(3, 6)):
        s = rng.uniform(0.42, 0.88)
        dep = sur_fut(s)
        ecart = np.array([rng.normal(0, 1.0), rng.normal(0, 1.0),
                          rng.uniform(0.5, 1.4)])
        ecart /= np.linalg.norm(ecart) or 1.0
        lg = portee * rng.uniform(0.45, 1.0)
        bout = dep + ecart * lg
        ra = r0 * 0.55 * (1 - s * 0.4)
        _fut(bloc, dep, bout, ra, ra * 0.38, n=4)
        for _ in range(rng.integers(1, 4)):
            e2 = ecart + np.array([rng.normal(0, 0.8), rng.normal(0, 0.8),
                                   rng.uniform(-0.1, 0.7)])
            e2 /= np.linalg.norm(e2) or 1.0
            d2 = dep + ecart * lg * rng.uniform(0.55, 0.90)
            _fut(bloc, d2, d2 + e2 * lg * rng.uniform(0.25, 0.45),
                 ra * 0.42, ra * 0.14, n=4)

    if baliveau and cartes is not None:
        # COURONNE. Une centaine de cartes reparties dans une sphere de 90 cm
        # donnait des pois isoles sur le ciel — c'est ce qu'on voyait sur la
        # planche a 17 m. Une couronne reelle est un AMAS DE MASSES, chacune
        # portee par une charpentiere et assez dense pour boucher le ciel.
        ray = hf * rng.uniform(0.20, 0.30)
        centre = sur_fut(rng.uniform(0.68, 0.80))
        for _ in range(int(rng.integers(3, 7))):
            o = rng.normal(0, 1.0, 3) * np.array([ray * 0.55, ray * 0.55, ray * 0.40])
            cm = centre + o
            rm = ray * rng.uniform(0.42, 0.70)
            for _ in range(int(rng.integers(110, 190))):
                u = rng.normal(0, 1.0, 3)
                u /= np.linalg.norm(u) or 1.0
                c = cm + u * rm * rng.uniform(0.25, 1.0) * np.array([1.0, 1.0, 0.78])
                _carte(cartes, c, rng, rng.uniform(0.09, 0.19))


ATLAS_METRES = 0.40
"""Cote reel de la planche de feuilles, en metres.

`textures/feuilles_touffe_*` couvre 40 x 40 cm et porte des feuilles de 12 cm,
soit 30 % de son cote. Une carte lit la planche ENTIERE : sa demi-taille fixe
donc la taille de feuille, a 0,30 x 2 x taille. La fourchette ci-dessous rend
des feuilles de 5 a 12 cm, ce qui est la dispersion d'une haie reelle.

Le materiau n'a pas besoin de ce nombre : les UV valent 0..1 par carte dans les
deux motifs, calcule comme photographie. Il est ici pour documenter d'ou sort
la fourchette de `_semer_cartes`.
"""


def _carte(bloc, c, rng, taille, n_biais=None):
    """Une carte de feuillage isolee, orientee au hasard autour de `c`.

    `taille` est la DEMI-taille : la carte mesure 2 x taille de cote. C'est le
    piege qui a fait rendre des feuilles de 46 cm — une carte a 0,20 fait
    40 cm de large, pas 20.

    Ses UV vont de 0 a 1, au besoin en miroir horizontal. Le materiau y trace
    une touffe a folioles, ou y lit la planche photographique entiere.
    """
    n = n_biais if n_biais is not None else rng.normal(0, 1.0, 3)
    n = np.asarray(n, float) + rng.normal(0, 0.45, 3)
    n /= np.linalg.norm(n) or 1.0
    ref = np.array([0.0, 0.0, 1.0]) if abs(n[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    e1 = np.cross(n, ref); e1 /= np.linalg.norm(e1) or 1.0
    e2 = np.cross(n, e1)
    # tour complet, et non un demi : une feuille pointe en bas ne se lit pas
    # comme la meme retournee, contrairement a une touffe calculee.
    a = rng.uniform(0, 2 * math.pi)
    f1 = e1 * math.cos(a) + e2 * math.sin(a)
    f2 = -e1 * math.sin(a) + e2 * math.cos(a)
    p = [c + f1 * taille * i + f2 * taille * j * rng.uniform(0.90, 1.10)
         for i, j in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    bloc["f"].append(_quad(bloc["v"], *[list(x) for x in p]))
    if rng.random() < 0.5:                       # miroir horizontal
        bloc["uv"] += [[1.0, 0.0], [0.0, 0.0], [0.0, 1.0], [1.0, 1.0]]
    else:
        bloc["uv"] += [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]


def _semer_cartes(bloc, etape, hk, hauteur, largeur, sol_abs, rng, densite):
    """Cartes de feuillage instanciees sur l'enveloppe de la haie.

    C'est LA difference entre un volume texture et un feuillage. Une carte est
    un petit quad oriente au hasard, porteur d'un alpha en touffe : la
    silhouette est alors reellement decoupee, les cartes s'ombrent entre elles
    et la lumiere passe entre elles. Blender ne demandait que cela ; le volume
    lisse d'avant ne lui laissait rien a rendre.
    """
    q, d = etape
    lat = np.array([-d[1], d[0]])
    zs = sol_abs(q[0], q[1])
    hh = hauteur * hk
    nb = max(1, int(densite))
    for _ in range(nb):
        # tirage sur l'enveloppe : hauteur biaisee vers le haut (la ou le
        # feuillage est dense), et un cote au hasard
        # on degage le pied : sans cela le feuillage descend jusqu'au sol
        # et masque les tiges qu'on vient de planter.
        # Une haie champetre a maturite est DENSE des 30 a 50 cm : degager
        # 80 cm de tiges nues en faisait une haie conduite en cepee, pas une
        # haie de protection. On ne degage plus que le tout premier pied,
        # et les tiges se devinent entre les cartes.
        tv = 0.08 + 0.92 * rng.beta(1.7, 1.25)
        cote = 1.0 if rng.random() < 0.5 else -1.0
        u = np.interp(tv, [p[1] for p in PROFIL_HAIE], [p[0] for p in PROFIL_HAIE])
        base = q + lat * (cote * u * largeur * rng.uniform(0.92, 1.22))
        z = zs + tv * hh
        c = np.array([base[0], base[1], z])
        c[:2] += rng.normal(0, 0.10, 2)
        # TAILLE : c'est une DEMI-taille, la carte mesure le double. Le piege a
        # coute un rendu de feuilles de 46 cm.
        #
        # Elle ne depend PAS de la hauteur de la haie : une feuille de charme
        # mesure 12 cm sur un plant de 1 m comme sur un baliveau de 5 m. Le
        # facteur en `hauteur / 2` d'avant gonflait les cartes sur la planche a
        # maturite, et le feuillage y lisait en erable de parc.
        taille = rng.uniform(0.09, 0.20)
        # orientation biaisee vers l'exterieur de la haie, puis `_carte` pose
        # le quad. UNE SEULE fabrique de carte, ici comme pour les couronnes de
        # baliveaux : deux copies finiraient par diverger.
        _carte(bloc, c, rng, taille,
               n_biais=[lat[0] * cote, lat[1] * cote, rng.uniform(-0.35, 0.75)])


def couleur_vegetation(chemin_photo, horizon_v):
    """Teinte de la vegetation DE LA PHOTO, lue juste au-dessus de l'horizon.

    C'est la ligne d'arbres du cliche : meme lumiere, meme saison, meme
    exposition. Une couleur choisie a la main ne peut pas s'y substituer.
    """
    from PIL import Image
    a = np.array(Image.open(chemin_photo).convert("RGB")).astype(float)
    v0 = int(max(0, horizon_v - 60))
    v1 = int(min(a.shape[0], horizon_v + 6))
    bande = a[v0:v1].reshape(-1, 3)
    # On garde la vegetation SOMBRE : les clairs de la bande sont du ciel
    # entre les branches et des cimes en pleine lumiere, qui tirent la
    # mediane vers un beige de paille.
    vert = (bande[:, 1] > bande[:, 2] + 4) & (bande[:, 1] > 25)
    if vert.sum() < 200:
        return [86, 94, 66]
    v = bande[vert]
    lim = np.percentile(v.mean(axis=1), 55)
    v = v[v.mean(axis=1) <= lim]
    return [float(x) for x in np.median(v, axis=0)]


def exporter(num, sortie, pose=None, scn=None, dossier=None):
    """Exporte la scene d'une vue vers un JSON que Blender saura monter.

    `pose` et `scn` sont facultatifs et servent a sortir de Sarnois : le
    module y etait cloue par `DOSSIER` et `M.DXF`. Une `pose` peut etre un
    chemin ou un dictionnaire deja lu ; une `scn` vient de `lecture_dxf.lire`
    comme de `lecture_contrat.lire`, les deux rendant la meme `Scene`.
    """
    if pose is None:
        pose = DOSSIER / f"pose_PV{num}.json"
    # Le dossier de la POSE sert de racine a la photo : un chemin relatif dans
    # la pose se lit a cote d'elle, et non dans le dossier de Sarnois.
    if dossier is None:
        dossier = Path(pose).parent if not isinstance(pose, dict) else DOSSIER
    if not isinstance(pose, dict):
        pose = json.loads(Path(pose).read_text(encoding="utf-8"))
    if scn is None:
        scn = lecture_dxf.lire(M.DXF)

    # LA PHOTO DOIT FAIRE LA TAILLE QUE LA POSE ANNONCE. Sans ce controle,
    # une pose calee sur une image reduite mais pointant l'originale se lit
    # sans erreur : la focale et l'horizon sont alors rapportes a une autre
    # echelle, et tout ce qui echantillonne la photo — la teinte du sol, celle
    # de la haie — va chercher ses pixels au mauvais endroit. Constate a
    # Saint-Cyr : la couleur du sol a ete relevee dans le ciel.
    _photo = Path(dossier) / pose["photo"]
    _taille = Image.open(_photo).size
    if _taille != (pose["largeur"], pose["hauteur"]):
        raise ValueError(
            f"{_photo.name} fait {_taille[0]}x{_taille[1]} alors que la pose "
            f"annonce {pose['largeur']}x{pose['hauteur']}. La focale et "
            "l'horizon se rapportent a la taille declaree : lire l'une pour "
            "l'autre fausse tout sans rien signaler.")
    q = np.array([t.q for t in scn.tables])
    mnt = terrain.charger_mnt((q[:, :, 0].min(), q[:, :, 1].min(),
                               q[:, :, 0].max(), q[:, :, 1].max()), pas=5.0, marge=350.0)
    E0, N0 = pose["est"], pose["nord"]
    z0 = float(mnt.altitude(E0, N0))

    def sol_abs(X, Y):
        """Altitude NGF ABSOLUE.

        Les constructeurs travaillent tous en absolu ; c'est `local()` qui
        retranche l'origine, UNE SEULE FOIS. Melanger les deux avait envoye la
        cloture 192 m sous terre sans que rien ne le signale.
        """
        return float(mnt.altitude(X, Y))

    def sol_rel(x, y):
        """Altitude relative, pour la nappe deja exprimee en coordonnees locales."""
        return float(mnt.altitude(E0 + x, N0 + y)) - z0

    mod, met, cadre = geometrie_tables(scn, mnt, sol_abs)
    cartes = {"v": [], "f": [], "uv": []}
    bois_haie = {"v": [], "f": []}
    haie = geometrie_haie(scn, sol_abs, E0, N0,
                          hauteur=pose.get("hauteur_haie", M.HAUTEUR_HAIE),
                          cartes=cartes, bois=bois_haie)
    import ouvrages_techniques as OT
    tech, ouvertures, registre = OT.ouvrages(scn, sol_abs, E0, N0,
                                             parametres=pose.get("parametres"))
    bois, grillage = geometrie_cloture(scn, sol_abs, E0, N0,
                                       ouvertures=ouvertures)
    sol = capteur_ombre(sol_rel)
    herbe = sol_du_site(scn, sol_abs)
    # LES OUVRAGES TECHNIQUES FONT PARTIE DU RENDU, toujours. Ils manquaient
    # jusqu'au 23/09/2026 : le montage de Saint-Cyr montrait des poteaux la ou
    # le plan porte un portail a douze metres et une aire d'aspiration a un
    # degre de l'axe de visee.

    def local(bloc):
        bloc["v"] = [[v[0] - E0, v[1] - N0, v[2] - z0] for v in bloc["v"]]
        return bloc

    cam = Camera(pose["largeur"], pose["hauteur"], pose["azimut"], pose["tangage"],
                 pose.get("roulis", 0.0), 26.0, pose.get("hauteur_oeil", 1.60))
    cam.f_px = pose["f_px"]
    data = {
        "camera": {"largeur": cam.W, "hauteur": cam.H, "f_px": cam.f_px,
                   "position": [0.0, 0.0, cam.h],
                   "R": [[float(x) for x in ligne] for ligne in cam.R]},
        # Le registre voyage AVEC la scene : `conformite` doit pouvoir la
        # confronter au plan sans rejouer l'export.
        "registre": registre,
        "soleil": pose.get("soleil"),          # None si la photo n'a pas de date
        "ciel": pose.get("ciel_rgb", [135, 156, 173]),
        # teinte du feuillage prise sur la photo elle-meme
        "materiaux": {"herbe_rgb": couleur_du_sol(
                          Path(dossier) / pose["photo"], pose["horizon"]),
                      "haie_rgb": couleur_vegetation(
            Path(dossier) / pose["photo"], pose["horizon"])},
        "objets": [
            # LE SOL D'ABORD, pour qu'il soit derriere tout le reste a la
            # lecture comme au rendu.
            *([{"materiau": "herbe", **local(herbe)}] if herbe else []),
            {"materiau": "module", **local(mod)},
            {"materiau": "acier", **local(met)},
            {"materiau": "cadre", **local(cadre)},
            {"materiau": "bois", **local(bois)},
            {"materiau": "grillage", **local(grillage)},
            {"materiau": "haie", **local(haie)},
            {"materiau": "feuillage", **local(cartes)},
            {"materiau": "branche", **local(bois_haie)},
            *[{"materiau": k, **local(v)} for k, v in sorted(tech.items())],
            {"materiau": "sol_ombre", **sol},
        ],
    }
    Path(sortie).write_text(json.dumps(data), encoding="utf-8")

    # CONFRONTATION AU PLAN, AVANT TOUT RENDU. Un rendu perspectif melange la
    # geometrie, la pose et l'occultation : quand il cloche, on ne sait pas
    # laquelle a lache, et l'on corrige a l'aveugle. Quatre allers-retours ont
    # ete perdus ainsi. Le controle, lui, dit ou regarder, et il ne se laisse
    # pas convaincre par une image qui a l'air correcte.
    import conformite
    for ligne in conformite.verifier(data, scn, E0, N0):
        print(f"  ! conformite au plan : {ligne}")
    for o in data["objets"]:
        print(f"  {o['materiau']:12s} {len(o['v']):7d} sommets, {len(o['f']):6d} faces")
    print(f"ecrit : {sortie}")
    return data


if __name__ == "__main__":
    num = sys.argv[1] if len(sys.argv) > 1 else "10"
    sortie = sys.argv[2] if len(sys.argv) > 2 else f"scene_PV{num}.json"
    exporter(num, sortie)
