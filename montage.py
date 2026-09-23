#!/usr/bin/env python3
"""Rend le projet sur une photo calee : sol, pistes, tables, pieux, cloture, haie.

Le rendu se fait en trois couches, dans cet ordre :

  1. LE SOL, par lancer de rayon. Pour chaque pixel sous l'horizon on cherche le
     point du terrain vise, puis on regarde s'il tombe dans l'emprise cloturee
     (herbe rase) ou sur une piste (grave). C'est la seule facon propre de poser
     un sol : projeter le contour de l'emprise ne marche pas quand la camera est
     juste a cote, le polygone s'enroule autour du point de vue.
  2. CE QUI SE DRESSE, trie par profondeur : tables avec pieux et panne, cloture,
     haie prevue au plan.
  3. rien d'autre. Pas d'ombre portee : sans date ni heure, la position du soleil
     est inconnue, et sur les deux photos de Sarnois la lumiere est diffuse.

Pieges deja corriges, a ne pas reintroduire :
  - les PIEUX SONT VERTICAUX. Les faire partir du bord bas de la table les incline
    de plus de 60 degres, parce que le vecteur de pente porte aussi l'horizontale.
    Un pieu se bat a l'aplomb de la panne qu'il porte.
  - un ELEMENT TRANSLUCIDE REPETE blanchit tout. Les ombres de contact vont sur un
    calque sans fusion ; le grillage se dessine en fils tant qu'ils sont resolus,
    et seulement au-dela en aplat leger.
  - la formule de FRESNEL doit etre plafonnee, sinon les rangees vues par la
    tranche virent au blanc.

Usage :
    python montage.py 10
    python montage.py 9
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy.ndimage import gaussian_filter

import lecture_dxf
import terrain
from camera import Camera

HERE = Path(__file__).resolve().parent
DXF = HERE / "exemples" / "sarnois-B" / "2026_08_27-IMP-DEV-Fixe-IND10b_V2.dxf"
DOSSIER = HERE / "exemples" / "sarnois-B" / "reportage-BE"

SUR = 3                      # surechantillonnage du calque des volumes
ESPACEMENT_PIEUX = 6.0       # m entre pieux le long d'une table
LARGEUR_PIEU = 0.12          # m, profile en H vu de face
FRACTION_PIEU = 0.50         # position de la panne sur la pente, depuis le bord bas
HAUTEUR_CLOTURE = 2.0
PAS_PIQUET = 3.0             # m entre poteaux, mesures sur toute la polyligne
MAILLE = 0.20                # m, pas du grillage rigide
DIAM_POTEAU = 0.13           # m, rondin d'acacia ecorce
DIST_FILS = 60.0             # m : au-dela, le grillage passe en aplat
HAUTEUR_HAIE = 2.0           # haie a la plantation
PORTEE_SOL = 420.0           # m : au-dela on laisse la photo telle quelle

#: Hauteur du fondu de la couverture peinte sous l'horizon, en fraction de la
#: hauteur d'image. Les derniers pixels sous l'horizon portent des centaines de
#: metres chacun : y peindre une couverture n'a pas de sens, et la couper net y
#: dessine une horizontale que l'oeil trouve aussitot.
MARGE_HORIZON = 0.012

SOL_CATEGORIES = ("piste", "plateforme", "voirie", "sdis")

# Les plans distinguent les revetements, le rendu les confondait en une seule
# grave. Le calque source est conserve dans chaque polyligne par
# `lecture_dxf`, il suffit de le lire. Les motifs sont cherches dans le NOM DE
# CALQUE, du plus specifique au plus general.
SOL_TEINTES = (
    ("aspiration",   (148, 141, 126), (0.7, 2.1)),   # aire SDIS, grave franche
    ("lourde",       (142, 134, 119), (0.6, 1.8)),   # grave compactee, nue
    ("legere",       (126, 126, 102), (0.5, 1.3)),   # structure legere, deja reprise d'herbe
    ("voirie",       (122, 119, 114), (0.4, 1.0)),   # voie d'acces, plus fermee
    ("plateforme",   (140, 133, 118), (0.6, 1.8)),
    ("bache",        (140, 133, 118), (0.6, 1.8)),   # assise de la citerne
)
SOL_DEFAUT = ((136, 128, 114), (0.6, 1.8))

# CONTRAT avec le lecteur de plan. `fiche_equipements.geometrie_equipements`
# rend davantage que le poste et la citerne — le BESS, la zone de remise, la
# zone de contention, et une LISTE de portails. Le rendu vectoriel ne sait
# dessiner que ceux-ci ; tout le reste est ecarte explicitement. Cette
# constante est au niveau du module pour etre verrouillee par un test : une
# cle nouvelle avait fait lever un TypeError sans que rien ne le signale.
DESSINABLES = ("poste", "citerne")

# Charte de rendu MESUREE sur les photomontages de reference (voir charte_rendu.py).
# Ces valeurs ne sont pas choisies a l'oeil : elles sortent des paires avant/apres
# du prestataire. Un rapport a la luminance du ciel se transpose d'une photo a
# l'autre, contrairement a une couleur absolue.
def _charte():
    # priorite a la charte des 18 dossiers (37 paires) sur celle des 3 vues
    f = HERE / "charte_dossiers.json"
    if not f.exists():
        f = HERE / "charte_rendu.json"
    defaut = {"panneau_luminance_sur_ciel": 0.31, "panneau_teinte": [1.04, 1.09, 0.87],
              "ombre_rapport": 0.78,
              # Volumes clairs ajoutes par le prestataire. ATTENTION : ce ne
              # sont PAS des batiments. Les 18 dossiers HOCH ne montrent aucun
              # poste ni citerne ; le detecteur a retenu des poteaux, du
              # grillage et des dessous de modules. Valeur de travail.
              "volume_clair_luminance_sur_ciel": 0.66, "volume_clair_teinte": [1.04, 1.02, 0.93]}
    if not f.exists():
        return defaut
    try:
        c = json.loads(f.read_text(encoding="utf-8"))["charte"]
        return {**defaut, **{k: v for k, v in c.items() if k in defaut}}
    except Exception:
        return defaut


CHARTE = _charte()

# Le plafond de Fresnel n'est pas une constante physique. Cale sur 37 paires de
# reference, dont la luminance des panneaux vaut 0,266 fois celle du ciel en
# mediane, pour un intervalle p10-p90 de 0,195 a 0,391.
# A 0,16 la vue 10 de Sarnois mesure 0,298 : au-dessus de la mediane, mais bien
# dans l'intervalle. On ne descend PAS a 0,05 pour coller a la mediane, car cette
# vue est prise en incidence tres rasante et de l'arriere, geometrie ou le verre
# renvoie reellement davantage. Forcer une statistique globale sur une geometrie
# particuliere serait un sur-ajustement.
# Recalage : `python ingerer_references.py <dossiers> --par-projet` puis ici.
REFLEX_MAX = 0.16            # plafond de Fresnel, cale sur la charte (voir ci-dessus)


# ---------------------------------------------------------------- geometrie

def _ordonner(q):
    """(bas0, bas1, haut1, haut0) : le bord bas porte les deux z les plus faibles."""
    q = np.asarray(q, float)
    o = np.argsort(q[:, 2])
    b0, b1 = q[o[0]], q[o[1]]
    ha, hb = q[o[2]], q[o[3]]
    if np.linalg.norm(ha - b0) < np.linalg.norm(hb - b0):
        h0, h1 = ha, hb
    else:
        h0, h1 = hb, ha
    return np.array([b0, b1, h1, h0])


def _fresnel(n, vers):
    """Reflectance du verre : 4% de face, plafonnee en incidence rasante."""
    c = abs(float(np.dot(n, vers)))
    return min(REFLEX_MAX, 0.04 + 0.96 * (1 - c) ** 5), c


def _dans_polygone(x, y, poly):
    """Point-dans-polygone vectorise, regle pair-impair."""
    p = np.asarray(poly, float)
    dedans = np.zeros(np.shape(x), dtype=bool)
    j = len(p) - 1
    for i in range(len(p)):
        xi, yi = p[i, 0], p[i, 1]
        xj, yj = p[j, 0], p[j, 1]
        traverse = (yi > y) != (yj > y)
        with np.errstate(divide="ignore", invalid="ignore"):
            xc = (xj - xi) * (y - yi) / (yj - yi) + xi
        dedans ^= traverse & (x < xc)
        j = i
    return dedans


class Scene:
    def __init__(self, cam, est, nord, z_sol, mnt, ciel):
        self.cam, self.E, self.N, self.z, self.mnt = cam, est, nord, z_sol, mnt
        self.ciel = np.asarray(ciel, float)
        self.oeil = np.array([est, nord, z_sol + cam.h])

    def p(self, X, Y, Z):
        uv = self.cam.projeter([[X - self.E, Y - self.N, Z - self.z]])[0]
        return None if not np.isfinite(uv).all() else (float(uv[0]), float(uv[1]))

    def poly(self, d, pts, remplissage, contour=None, ep=1):
        s = [self.p(*q) for q in pts]
        if any(v is None for v in s):
            return False
        if remplissage:
            d.polygon(s, fill=remplissage)
        if contour:
            d.line(s + [s[0]], fill=contour, width=ep)
        return True

    def sol(self, X, Y):
        return float(self.mnt.altitude(X, Y))


# ------------------------------------------------------------------- le sol

def carte_sol(cam, E0, N0, z0, mnt, W, H, v0):
    """Lancer de rayon : point du terrain vise par chaque pixel sous l'horizon.

    Renvoie (E, N, distance horizontale, validite), chacun de forme (H, W).
    """
    vs, us = np.mgrid[0:H, 0:W]
    uv = np.stack([us.ravel() + 0.5, vs.ravel() + 0.5], axis=1)
    d = cam.rayon(uv)
    dz = d[:, 2]
    ok = (dz < -1e-6) & (uv[:, 1] > v0)
    t = np.zeros(len(d))
    t[ok] = -cam.h / dz[ok]
    for _ in range(3):                       # affiner contre le vrai terrain
        E = E0 + t * d[:, 0]
        N = N0 + t * d[:, 1]
        zl = np.asarray(mnt.altitude(E, N), float) - z0
        t = np.where(ok, (zl - cam.h) / np.where(ok, dz, 1.0), 0.0)
    E = E0 + t * d[:, 0]
    N = N0 + t * d[:, 1]
    dist = t * np.hypot(d[:, 0], d[:, 1])
    ok &= (dist > 0.5) & (dist < PORTEE_SOL)
    f = lambda a: a.reshape(H, W)
    return f(E), f(N), f(dist), f(ok)


def _teinte_sol(photo, masque, dist, couleur, amplitude, rng, grain=(0.7, 2.6)):
    """Repeint une zone de sol en gardant l'eclairage de la photo, plus un grain.

    Le grain s'attenue avec la distance : a 200 m, une touffe d'herbe de 10 cm
    fait moins d'un tiers de pixel, la texture doit disparaitre.
    """
    L = photo.mean(axis=2)
    ref = L[masque]
    Ln = np.clip((L - ref.mean()) / (ref.std() + 1e-6), -2.2, 2.2)
    n1 = gaussian_filter(rng.standard_normal(L.shape), grain[0])
    n2 = gaussian_filter(rng.standard_normal(L.shape), grain[1])
    n1 /= n1.std() + 1e-9
    n2 /= n2.std() + 1e-9
    amp = amplitude * np.exp(-dist / 110.0)
    tex = (n1 * 0.65 + n2 * 0.35) * amp
    out = (np.asarray(couleur, float)[None, None, :] * (1.0 + 0.09 * np.clip(Ln, -1.5, 1.5))[..., None]
           + tex[..., None] * np.array([0.85, 1.0, 0.7]))
    # GARDER UNE PART DE LA PHOTO, MAIS DECROISSANTE AVEC LA DISTANCE.
    #
    # La part fixe d'un quart etait juste de pres : a vingt metres, ce qui
    # transparait sous la grave est le relief reel du terrain et sa lumiere,
    # et l'aplat peint y gagne. Elle ne l'est plus de loin : a deux cents
    # metres, ce qui transparait est la CULTURE EN PLACE, dont la texture n'a
    # aucune raison de subsister sous une piste. Mesure sur IMG_6941 : 83 % des
    # pixels de piste sont dans les cinquante premiers metres ; le reste est
    # une lame de quelques centaines de pixels, que le quart de photo suffisait
    # a effacer. La piste semblait s'arreter en chemin.
    #
    # Meme decroissance que le grain, pour la meme raison : ce qui fait le
    # realisme de pres fait le bruit de loin.
    part = 0.24 * np.exp(-dist / 150.0)
    out = (1.0 - part)[..., None] * out + part[..., None] * photo.astype(float)
    return np.clip(out, 0, 255)


def couleur_prairie(photo, v0):
    """Couleur d'herbe echantillonnee sur la photo elle-meme, pres de l'horizon."""
    bande = photo[int(v0):int(v0) + 22]
    r, g, b = bande[..., 0], bande[..., 1], bande[..., 2]
    vert = (g > r + 4) & (g > b + 6) & (g > 60)
    if vert.sum() < 60:
        return np.array([104, 116, 76], float)
    return np.array([r[vert].mean(), g[vert].mean(), b[vert].mean()], float)


def peindre_sol(photo, scn, cam, E0, N0, z0, mnt, v0, rng):
    """Herbe rase dans l'emprise cloturee, grave sur les pistes."""
    H, W, _ = photo.shape
    E, N, dist, ok = carte_sol(cam, E0, N0, z0, mnt, W, H, v0)
    out = photo.astype(float).copy()
    cl = np.array([(a, b) for a, b in scn.lignes["cloture"][0]["pts"]], float)
    site = ok & _dans_polygone(E, N, cl)
    from lecture_dxf import _sans_accents
    groupes = {}
    pistes = np.zeros_like(site)
    for cat in SOL_CATEGORIES:
        for p in scn.lignes.get(cat, []):
            pts = np.array([(a, b) for a, b in p["pts"]], float)
            if len(pts) < 3:
                continue
            lay = _sans_accents(p.get("couche", "")).lower()
            cle = next((m for m, _, _ in SOL_TEINTES if m in lay), None)
            m = ok & _dans_polygone(E, N, pts)
            groupes[cle] = groupes.get(cle, np.zeros_like(site)) | m
            pistes |= m
    herbe = site & ~pistes
    if herbe.sum() > 40:
        g = _teinte_sol(photo, herbe, dist, couleur_prairie(photo, v0), 15.0, rng)
        out[herbe] = g[herbe]
    for cle, masque in groupes.items():
        if masque.sum() <= 20:
            continue
        coul, grain = next(((c, g) for m, c, g in SOL_TEINTES if m == cle), SOL_DEFAUT)
        gr = _teinte_sol(photo, masque, dist, np.array(coul, float), 8.0, rng, grain=grain)
        out[masque] = gr[masque]
    # fondu d'un pixel sur les bords pour eviter l'escalier
    m = gaussian_filter((herbe | pistes).astype(float), 0.6)
    # FONDU VERS L'HORIZON, qui manquait et qui se voyait.
    #
    # Le lancer de rayon s'arrête à la ligne d'horizon : la couverture peinte
    # y finit donc sur une HORIZONTALE nette, alors que le sol, lui, continue.
    # Mesuré sur IMG_6941 : le bord lointain de l'enceinte peinte tient entre
    # v=1549 et v=1560 pour des distances allant de 35 à 187 m — une même ligne
    # pour des profondeurs dans un rapport de cinq.
    #
    # C'est que les derniers pixels sous l'horizon portent des centaines de
    # mètres chacun : aucune couverture peinte n'y a de sens, et la vraie image
    # y est de la brume. On éteint donc la peinture sur cette bande au lieu de
    # la couper net. `MARGE_HORIZON` est en fraction de hauteur d'image, pour
    # valoir autant sur un cliché de 960 px que sur un de 4032.
    marge = max(4.0, MARGE_HORIZON * H)
    v = np.arange(H, dtype=float)[:, None]
    m = m * np.clip((v - float(v0)) / marge, 0.0, 1.0)
    m = m[..., None]
    out = photo.astype(float) * (1 - m) + out * m
    return np.clip(out, 0, 255).astype(np.uint8), (herbe | pistes), dist


# --------------------------------------------------------------- les volumes

def contact_sol(sc, d, q):
    """Assombrissement doux du sol sous une table (calque separe, sans fusion)."""
    b0, b1, h1, h0 = _ordonner(q)
    av = (h0 - b0) * FRACTION_PIEU
    z0, z1 = sc.sol(*b0[:2]), sc.sol(*b1[:2])
    sc.poly(d, [(b0[0] - av[0] * .3, b0[1] - av[1] * .3, z0),
                (b1[0] - av[0] * .3, b1[1] - av[1] * .3, z1),
                (b1[0] + av[0] * 1.7, b1[1] + av[1] * 1.7, z1),
                (b0[0] + av[0] * 1.7, b0[1] + av[1] * 1.7, z0)],
            (26, 24, 18, int(round(300 * (1 - CHARTE["ombre_rapport"])))))


def dessiner_table(sc, d, q, dist):
    """Pieux verticaux, panne, plan de modules avec sa trame."""
    q = _ordonner(q)
    b0, b1, h1, h0 = q
    n = np.cross(h0 - b0, b1 - b0)
    n = n / np.linalg.norm(n) * (1 if n[2] > 0 else -1)
    vers = sc.oeil - b0
    vers /= np.linalg.norm(vers)
    R, _ = _fresnel(n, vers)
    brume = 1 - math.exp(-dist / 2600)
    # base issue de la charte : luminance visee en fraction du ciel de CETTE photo,
    # teinte mesuree sur les references (chaude et neutre, pas bleue)
    teinte = np.asarray(CHARTE["panneau_teinte"], float)
    base = teinte / teinte.mean() * (CHARTE["panneau_luminance_sur_ciel"] * sc.ciel.mean())
    base = base * (1 - R) + sc.ciel * 0.92 * R
    coul = base * (1 - brume) + sc.ciel * 0.97 * brume
    acier = np.array([78, 81, 78]) * (1 - brume) + sc.ciel * 0.95 * brume
    acier = tuple(int(v) for v in np.clip(acier, 0, 255))

    long_vec = b1 - b0
    L = float(np.linalg.norm(long_vec[:2]))
    ex = long_vec / L
    lat = np.array([-ex[1], ex[0], 0.0]) * (LARGEUR_PIEU / 2)
    pente = h0 - b0                                  # porte l'horizontale ET la hauteur

    # 1. pieux : verticaux, a l'aplomb de la panne
    nb = max(2, int(round(L / ESPACEMENT_PIEUX)) + 1)
    for k in range(nb):
        t = (k + 0.5) / nb
        haut = b0 + long_vec * t + pente * FRACTION_PIEU
        zs = sc.sol(haut[0], haut[1])                # le pied est SOUS la panne
        sc.poly(d, [(haut[0] - lat[0], haut[1] - lat[1], zs),
                    (haut[0] + lat[0], haut[1] + lat[1], zs),
                    (haut[0] + lat[0], haut[1] + lat[1], haut[2]),
                    (haut[0] - lat[0], haut[1] - lat[1], haut[2])], acier + (255,))

    # 2. panne sous les modules
    pa0 = b0 + pente * FRACTION_PIEU
    pa1 = b1 + (h1 - b1) * FRACTION_PIEU
    ep = np.array([0.0, 0.0, 0.18])
    sc.poly(d, [tuple(pa0 - ep), tuple(pa1 - ep), tuple(pa1), tuple(pa0)], acier + (255,))

    # 3. cadre plein puis trame des modules : les jeux doivent laisser voir la
    #    structure sombre, pas le ciel a travers la table.
    sc.poly(d, [tuple(x) for x in q],
            tuple(int(v) for v in np.clip(coul * 0.55, 0, 255)) + (255,))
    cols = max(6, int(round(L / 1.15)))
    g = 0.10 / max(L, 1e-6)
    for i in range(cols):
        s0, s1 = i / cols + g, (i + 1) / cols - g
        for j in range(2):
            t0, t1 = j / 2 + 0.012, (j + 1) / 2 - 0.012
            c = [(b0 + long_vec * s0) * (1 - t0) + (h0 + (h1 - h0) * s0) * t0,
                 (b0 + long_vec * s1) * (1 - t0) + (h0 + (h1 - h0) * s1) * t0,
                 (b0 + long_vec * s1) * (1 - t1) + (h0 + (h1 - h0) * s1) * t1,
                 (b0 + long_vec * s0) * (1 - t1) + (h0 + (h1 - h0) * s0) * t1]
            # legere variation module a module : les references montrent un ecart-type
            # de 20 niveaux dans la nappe, un aplat parfait se voit tout de suite
            jit = 1.0 + 0.055 * math.sin(12.9898 * (i + 1) + 78.233 * (j + 1) + b0[0] * 0.013)
            teinte = coul * (1.0 if j == 0 else 0.94) * jit
            sc.poly(d, [tuple(x) for x in c],
                    tuple(int(v) for v in np.clip(teinte, 0, 255)) + (252,))
    sc.poly(d, [tuple(x) for x in q], None, (18, 22, 34, 190), max(1, SUR // 2))


def poteau_bois(sc, d, x, y, zs, hauteur, diam, brume, teinte=0.0):
    """Poteau d'acacia : rond, donc rendu en lamelles verticales ombrees.

    Un rond ne se dessine pas comme un rectangle plat : c'est l'ombre qui tourne
    sur le flanc qui le fait lire comme un cylindre. Six lamelles suffisent.
    """
    lam = 7
    vx, vy = x - sc.E, y - sc.N
    n = math.hypot(vx, vy) or 1.0
    lx, ly = -vy / n, vx / n              # lateral, perpendiculaire a la visee
    ax, ay = vx / n, vy / n               # profondeur, vers le fond
    bois = np.array([126, 106, 82]) * (1.0 + teinte)
    for k in range(lam):
        a0 = -0.5 + k / lam
        a1 = -0.5 + (k + 1) / lam
        mid = (a0 + a1) / 2               # -0,5 au bord gauche, +0,5 au bord droit
        # cylindre sous ciel couvert : clair au centre, sombre sur les deux flancs,
        # avec un leger decalage pour ne pas etre parfaitement symetrique
        f = 0.42 + 0.72 * max(0.0, math.cos(math.pi * (mid - 0.08))) ** 1.3
        c = bois * f * (1 - brume) + sc.ciel * 0.9 * brume
        sc.poly(d, [(x + lx * diam * a0, y + ly * diam * a0, zs - 0.05),
                    (x + lx * diam * a1, y + ly * diam * a1, zs - 0.05),
                    (x + lx * diam * a1, y + ly * diam * a1, zs + hauteur),
                    (x + lx * diam * a0, y + ly * diam * a0, zs + hauteur)],
                tuple(int(v) for v in np.clip(c, 0, 255)) + (255,))
    # tete sciee : visible seulement de pres
    if math.hypot(vx, vy) < 40:
        tete = np.clip(bois * 1.25 * (1 - brume) + sc.ciel * 0.9 * brume, 0, 255)
        sc.poly(d, [(x - lx * diam * .5, y - ly * diam * .5, zs + hauteur),
                    (x + lx * diam * .5, y + ly * diam * .5, zs + hauteur),
                    (x + lx * diam * .35 + ax * diam * .45,
                     y + ly * diam * .35 + ay * diam * .45, zs + hauteur),
                    (x - lx * diam * .35 + ax * diam * .45,
                     y - ly * diam * .35 + ay * diam * .45, zs + hauteur)],
                tuple(int(v) for v in tete) + (255,))


def dessiner_cloture(sc, d, pts, s0=0.0, dmax=400.0):
    """Fils de grillage, et poteaux d'acacia poses a pas constant sur TOUTE la ligne.

    `s0` est l'abscisse curviligne du debut du segment. Sans elle, chaque segment
    repart a zero et les poteaux se serrent a chaque sommet de la polyligne : on
    en voit deux cote a cote puis un trou. La cloture de Sarnois a 57 sommets, le
    defaut se voit partout.
    """
    a, b = np.array(pts[0], float), np.array(pts[1], float)
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    if L < 0.2:
        return
    dist = math.hypot((a[0] + b[0]) / 2 - sc.E, (a[1] + b[1]) / 2 - sc.N)
    if dist > dmax:
        return
    za, zb = sc.sol(*a), sc.sol(*b)
    A = sc.p(a[0], a[1], za + HAUTEUR_CLOTURE)
    B = sc.p(b[0], b[1], zb + HAUTEUR_CLOTURE)
    A0, B0 = sc.p(a[0], a[1], za), sc.p(b[0], b[1], zb)
    if not (A and B and A0 and B0):
        return
    if dist > DIST_FILS:
        d.polygon([A, B, B0, A0], fill=(146, 148, 142, 38))
    else:
        pas = max(MAILLE, L / 600)
        for s in np.arange(0, L, pas):
            q = a + (b - a) * (s / L)
            if math.hypot(q[0] - sc.E, q[1] - sc.N) > DIST_FILS:
                continue
            zs = sc.sol(q[0], q[1])
            P, Q = sc.p(q[0], q[1], zs + 0.04), sc.p(q[0], q[1], zs + HAUTEUR_CLOTURE)
            if P and Q and abs(P[1] - Q[1]) > 2:
                d.line([P, Q], fill=(118, 121, 115, 104), width=max(1, SUR // 3))
    for f in np.arange(0.06, 1.001, MAILLE / HAUTEUR_CLOTURE):   # fils horizontaux
        P = sc.p(a[0], a[1], za + HAUTEUR_CLOTURE * f)
        Q = sc.p(b[0], b[1], zb + HAUTEUR_CLOTURE * f)
        if P and Q:
            d.line([P, Q], fill=(118, 121, 115, 104), width=max(1, SUR // 3))
    brume = 1 - math.exp(-dist / 2600)
    depart = (math.ceil(s0 / PAS_PIQUET) * PAS_PIQUET) - s0    # pas constant, global
    for s in np.arange(depart, L, PAS_PIQUET):
        if s < 0:
            continue
        q = a + (b - a) * (s / L)
        zs = sc.sol(q[0], q[1])
        teinte = 0.10 * math.sin(7.3 * (s0 + s))               # chaque poteau un peu different
        poteau_bois(sc, d, q[0], q[1], zs, HAUTEUR_CLOTURE + 0.12, DIAM_POTEAU, brume, teinte)


def _boite(sc, d, centre, angle, L, l, h0, h1, couleur, brume, toit=None):
    """Volume parallelepipedique pose au sol, faces ombrees selon leur orientation."""
    ca, sa = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    ex = np.array([ca, sa]); ey = np.array([-sa, ca])
    c = np.array(centre, float)
    coins = [c + ex * (L / 2) * i + ey * (l / 2) * j for i, j in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    zs = [sc.sol(*q) for q in coins]
    base = np.asarray(couleur, float)
    faces = []
    for k in range(4):
        a, b = coins[k], coins[(k + 1) % 4]
        za, zb = zs[k], zs[(k + 1) % 4]
        m = (a + b) / 2
        nrm = np.array([-(b - a)[1], (b - a)[0]])
        nrm = nrm / (np.linalg.norm(nrm) or 1)
        vers = np.array([sc.E - m[0], sc.N - m[1]])
        vers = vers / (np.linalg.norm(vers) or 1)
        cosv = float(np.dot(nrm, vers))
        if cosv <= 0.02:                       # face tournee a l'oppose
            continue
        f = 0.62 + 0.38 * cosv                 # ciel couvert : contraste doux
        coul = base * f * (1 - brume) + sc.ciel * 0.9 * brume
        faces.append((np.hypot(m[0] - sc.E, m[1] - sc.N),
                      [(a[0], a[1], za + h0), (b[0], b[1], zb + h0),
                       (b[0], b[1], zb + h1), (a[0], a[1], za + h1)],
                      tuple(int(v) for v in np.clip(coul, 0, 255))))
    for _, pts, coul in sorted(faces, key=lambda z: -z[0]):
        sc.poly(d, pts, coul + (255,), tuple(int(v * 0.72) for v in coul) + (200,), max(1, SUR // 3))
    t = np.asarray(toit if toit is not None else base * 1.1, float)
    t = t * (1 - brume) + sc.ciel * 0.9 * brume
    sc.poly(d, [(q[0], q[1], z + h1) for q, z in zip(coins, zs)],
            tuple(int(v) for v in np.clip(t, 0, 255)) + (255,),
            tuple(int(v * 0.7) for v in np.clip(t, 0, 255)) + (200,), max(1, SUR // 3))


def dessiner_poste(sc, d, centre, angle, dist, L=10.0, l=3.0, h=2.60):
    """Poste de transformation : prefab beton 10 x 3 x 2,6 m, geometrie du bloc UNI_PTR.

    Le plan donne un batiment de 10,00 x 3,00 m dans une emprise de 13,5 x 7,0 m.
    C'est un prefabrique beton standard : corps clair, acrotere debordant, portes
    metal en long pan et grilles de ventilation.
    """
    brume = 1 - math.exp(-dist / 2600)
    ca, sa = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    ex = np.array([ca, sa]); ey = np.array([-sa, ca])
    c = np.array(centre, float)
    # Couleur de travail, PAS une mesure de beton : les references ne
    # contiennent aucun local technique. Le 0,66 vient de volumes clairs
    # quelconques (poteaux, dessous de modules). Il a seulement le merite
    # d'etre plus sombre que le ciel, ce que mon 1,02 initial n'etait pas.
    # A remplacer des qu'une photo de poste reel sera disponible.
    tb = np.asarray(CHARTE["volume_clair_teinte"], float)
    corps = tb / tb.mean() * (CHARTE["volume_clair_luminance_sur_ciel"] * sc.ciel.mean())
    # plateforme en grave : 13,5 x 7,0 m au plan
    grave = corps * 0.76 * (1 - brume) + sc.ciel * 0.9 * brume
    pl = [c + ex * 6.75 * i + ey * 3.5 * j for i, j in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    sc.poly(d, [(q[0], q[1], sc.sol(*q) + 0.02) for q in pl],
            tuple(int(v) for v in np.clip(grave, 0, 255)) + (255,))
    _boite(sc, d, c, angle, L, l, 0.0, h, corps, brume, toit=corps * 0.78)
    _boite(sc, d, c, angle, L + 0.30, l + 0.30, h, h + 0.22,   # acrotere
           corps * 0.91, brume, toit=corps * 0.76)
    # portes et grilles sur le long pan tourne vers l'observateur
    vers = np.array([sc.E - c[0], sc.N - c[1]])
    cote = 1.0 if float(np.dot(ey, vers)) > 0 else -1.0
    face = c + ey * (l / 2 + 0.02) * cote
    for i, (u0, u1, hh0, hh1, coul) in enumerate(
            ((-0.42, -0.10, 0.02, 0.86, tuple(corps * 0.54)),   # portes
             (-0.06, 0.26, 0.02, 0.86, tuple(corps * 0.54)),
             (0.30, 0.44, 0.10, 0.62, tuple(corps * 0.45)))):  # grille
        a = face + ex * (L * u0)
        b = face + ex * (L * u1)
        za, zb = sc.sol(*a), sc.sol(*b)
        cc = np.asarray(coul, float) * (1 - brume) + sc.ciel * 0.9 * brume
        sc.poly(d, [(a[0], a[1], za + h * hh0), (b[0], b[1], zb + h * hh0),
                    (b[0], b[1], zb + h * hh1), (a[0], a[1], za + h * hh1)],
                tuple(int(v) for v in np.clip(cc, 0, 255)) + (255,))


def dessiner_citerne(sc, d, centre, angle, dist, cote=(12.0, 10.0), h=1.35,
                     bac=(16.0, 11.3), h_bac=0.70):
    """Citerne souple 120 m3 : bache PVC rectangulaire, gonflee comme un coussin.

    Ce n'est pas une cuve cylindrique : une citerne bache souple est un
    rectangle en plan, dont la souplesse arrondit les aretes et bombe le dessus.
    Elle est haute d'a peine 1,35 m au centre et s'affaisse jusqu'au sol sur son
    pourtour, donc elle se voit beaucoup moins qu'une cuve rigide.

    12,0 x 10,0 m au sol pour 1,35 m au centre donnent environ 120 m3 compte tenu
    du bombe. Le bac de retention du plan fait 16,0 x 11,3 m, ce qui laisse
    2,0 m de garde tout autour.
    """
    brume = 1 - math.exp(-dist / 2600)
    c = np.array(centre, float)
    ca, sa = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    ex = np.array([ca, sa, 0.0]); ey = np.array([-sa, ca, 0.0])
    zc = sc.sol(*c)

    # --- merlon du bac de retention, en deux moities pour encadrer la bache
    talus, npts = 1.15, 88
    bandes = []
    coins = [(-1, -1), (1, -1), (1, 1), (-1, 1), (-1, -1)]
    for k in range(npts):
        pts3 = []
        for t in (4.0 * k / npts, 4.0 * (k + 1) / npts):
            i = int(min(t, 3.999)); u = t - i
            g = np.array(coins[i], float) + (np.array(coins[i + 1], float)
                                             - np.array(coins[i], float)) * u
            ext = c + ex[:2] * g[0] * bac[0] / 2 + ey[:2] * g[1] * bac[1] / 2
            nrm = (c - ext) / (np.linalg.norm(c - ext) or 1)
            pts3.append((ext, nrm))
        (e0, n0), (e1, n1) = pts3
        m = (e0 + e1) / 2
        vers = np.array([sc.E - m[0], sc.N - m[1]])
        vers = vers / (np.linalg.norm(vers) or 1)
        f = 0.72 + 0.30 * max(0.0, float(np.dot(-(n0 + n1) / 2, vers)))
        herbe = np.clip(np.array([96, 108, 68]) * f * (1 - brume) + sc.ciel * 0.9 * brume, 0, 255)
        herbe = tuple(int(v) for v in herbe)
        z0, z1 = sc.sol(*e0), sc.sol(*e1)
        c0, c1 = e0 + n0 * talus, e1 + n1 * talus
        i0, i1 = e0 + n0 * 2 * talus, e1 + n1 * 2 * talus
        bandes.append((math.hypot(m[0] - sc.E, m[1] - sc.N),
                       [(e0[0], e0[1], z0), (e1[0], e1[1], z1),
                        (c1[0], c1[1], z1 + h_bac), (c0[0], c0[1], z0 + h_bac)], herbe,
                       [(c0[0], c0[1], z0 + h_bac), (c1[0], c1[1], z1 + h_bac),
                        (i1[0], i1[1], z1 + h_bac), (i0[0], i0[1], z0 + h_bac)],
                       tuple(int(v * 1.08) for v in herbe)))
    d_c = math.hypot(c[0] - sc.E, c[1] - sc.N)
    for dm, t1, k1, t2, k2 in sorted(bandes, key=lambda z: -z[0]):
        if dm > d_c:
            sc.poly(d, t1, k1 + (255,)); sc.poly(d, t2, k2 + (255,))

    # --- la bache : maille sur un profil de coussin
    nu, nv = 30, 24
    def surface(u, v):
        """u, v dans [-1, 1] ; superellipse en plan, bombe au centre."""
        r = (abs(u) ** 4 + abs(v) ** 4) ** 0.25
        hh = h * math.sqrt(max(0.0, 1.0 - min(r, 1.0) ** 3))
        p = c + ex[:2] * (u * cote[0] / 2) + ey[:2] * (v * cote[1] / 2)
        return np.array([p[0], p[1], zc + 0.02 + hh])
    pvc = np.array([64, 76, 60])                       # PVC vert sombre
    faces = []
    for i in range(nu):
        for j in range(nv):
            u0, u1 = -1 + 2 * i / nu, -1 + 2 * (i + 1) / nu
            v0, v1 = -1 + 2 * j / nv, -1 + 2 * (j + 1) / nv
            q = [surface(u0, v0), surface(u1, v0), surface(u1, v1), surface(u0, v1)]
            n = np.cross(q[1] - q[0], q[3] - q[0])
            nn = np.linalg.norm(n)
            if nn < 1e-9:
                continue
            n = n / nn * (1 if n[2] > 0 else -1)
            m = sum(q) / 4
            vers = sc.oeil - m
            vers = vers / (np.linalg.norm(vers) or 1)
            cosv = abs(float(np.dot(n, vers)))
            # bache tendue : diffus, plus un peu de ciel sur les parties bombees
            refl = 0.05 + 0.30 * max(0.0, n[2]) ** 2
            coul = pvc * (0.62 + 0.46 * cosv) * (1 - refl) + sc.ciel * 0.75 * refl
            coul = coul * (1 - brume) + sc.ciel * 0.9 * brume
            faces.append((np.hypot(m[0] - sc.E, m[1] - sc.N),
                          [tuple(x) for x in q],
                          tuple(int(v) for v in np.clip(coul, 0, 255))))
    for _, pts, coul in sorted(faces, key=lambda z: -z[0]):
        sc.poly(d, pts, coul + (255,))

    for dm, t1, k1, t2, k2 in sorted(bandes, key=lambda z: -z[0]):
        if dm <= d_c:
            sc.poly(d, t1, k1 + (255,)); sc.poly(d, t2, k2 + (255,))


def dessiner_haie(sc, d, pts):
    """Haie prevue au plan, a sa hauteur de plantation."""
    a, b = np.array(pts[0], float), np.array(pts[1], float)
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    for s in np.arange(0, max(L, 0.1), 1.1):
        q = a + (b - a) * (s / max(L, 1e-6))
        zs = sc.sol(q[0], q[1])
        P, Q = sc.p(q[0], q[1], zs), sc.p(q[0], q[1], zs + HAUTEUR_HAIE)
        if P and Q:
            r = abs(P[1] - Q[1]) * 0.44
            d.ellipse([Q[0] - r, Q[1] - r * 0.55, Q[0] + r, P[1]], fill=(72, 84, 56, 228))


# ------------------------------------------------------------------- rendu

def rendre(photo, pose, sortie, haie_projet=True, graine=7):
    base = Image.open(photo).convert("RGB")
    W, H = base.size
    arr = np.array(base).astype(np.uint8)
    v0 = float(pose["horizon"])
    ciel = arr.astype(float)[max(0, int(v0) - 40):int(v0) - 4].reshape(-1, 3).mean(axis=0)

    scn = lecture_dxf.lire(DXF)
    q = np.array([t.q for t in scn.tables])
    mnt = terrain.charger_mnt((q[:, :, 0].min(), q[:, :, 1].min(),
                               q[:, :, 0].max(), q[:, :, 1].max()), pas=5.0, marge=350.0)
    E0, N0 = pose["est"], pose["nord"]
    z0 = float(mnt.altitude(E0, N0))
    oeil = pose.get("hauteur_oeil", 1.60)

    cam1 = Camera(W, H, pose["azimut"], pose["tangage"], pose.get("roulis", 0.0), 26.0, oeil)
    cam1.f_px = pose["f_px"]
    rng = np.random.default_rng(graine)
    fond, masque_sol, _ = peindre_sol(arr, scn, cam1, E0, N0, z0, mnt, v0, rng)

    cam = Camera(W * SUR, H * SUR, pose["azimut"], pose["tangage"],
                 pose.get("roulis", 0.0), 26.0, oeil)
    cam.f_px = pose["f_px"] * SUR
    sc = Scene(cam, E0, N0, z0, mnt, ciel)
    calque = Image.new("RGBA", (W * SUR, H * SUR), (0, 0, 0, 0))
    d = ImageDraw.Draw(calque, "RGBA")

    objets = []
    for t in scn.tables:
        c = np.array(t.q).mean(axis=0)
        objets.append((math.hypot(c[0] - E0, c[1] - N0), "table", t.q))
    for genre, cat in (("cloture", "cloture"), ("haie", "haie")):
        if genre == "haie" and not haie_projet:
            continue
        for e in scn.lignes.get(cat, []):
            pts = [(a, b) for a, b in e["pts"]]
            s0 = 0.0                       # abscisse cumulee : pas de poteau constant
            for i in range(len(pts) - 1):
                m = ((pts[i][0] + pts[i + 1][0]) / 2, (pts[i][1] + pts[i + 1][1]) / 2)
                objets.append((math.hypot(m[0] - E0, m[1] - N0), genre,
                               ([pts[i], pts[i + 1]], s0)))
                s0 += math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
    import fiche_equipements as fe                 # geometrie reelle des blocs
    for cle, g in fe.geometrie_equipements(DXF).items():
        if cle not in DESSINABLES:
            continue
        for gg in (g if isinstance(g, list) else [g]):
            if isinstance(gg, dict) and "centre" in gg:
                objets.append((math.hypot(gg["centre"][0] - E0, gg["centre"][1] - N0),
                               cle, gg))
    objets.sort(key=lambda z: -z[0])

    calque_sol = Image.new("RGBA", (W * SUR, H * SUR), (0, 0, 0, 0))
    d_sol = ImageDraw.Draw(calque_sol)          # sans fusion : pas d'empilement
    for _, genre, obj in objets:
        if genre == "table":
            contact_sol(sc, d_sol, obj)
    calque.alpha_composite(calque_sol)

    for dist, genre, obj in objets:
        if genre == "table":
            dessiner_table(sc, d, obj, dist)
        elif genre == "cloture":
            dessiner_cloture(sc, d, obj[0], obj[1])
        elif genre == "poste":
            dessiner_poste(sc, d, obj["centre"], obj["angle"], dist,
                           L=obj.get("L", 10.0), l=obj.get("l", 3.0))
        elif genre == "citerne":
            dessiner_citerne(sc, d, obj["centre"], obj["angle"], dist)
        elif genre == "haie":
            dessiner_haie(sc, d, obj[0])

    calque = calque.resize((W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(0.4))
    im = Image.fromarray(fond)
    im.paste(calque, (0, 0), calque)
    im.save(sortie, quality=95)
    return im, int(masque_sol.sum())


if __name__ == "__main__":
    num = sys.argv[1] if len(sys.argv) > 1 else "10"
    pose = json.loads((DOSSIER / f"pose_PV{num}.json").read_text())
    im, n = rendre(DOSSIER / pose["photo"], pose, DOSSIER / f"montage_PV{num}.jpg")
    print(f"montage_PV{num}.jpg  {im.size}  az {pose['azimut']}  f {pose['f_px']} px  "
          f"| sol repeint : {n} px")
