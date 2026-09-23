#!/usr/bin/env python3
"""Exporte les equipements techniques vers Blender : poste, citerne souple, cloture.

Meme decoupage que `exporter_blender.py` : ce script connait le plan et produit
de la geometrie en metres ; Blender ne sait que monter des maillages et rendre.

Les dimensions sortent des blocs du plan PVcase, pas d'une estimation :
  - UNI_PTR         : batiment de 10,00 x 3,00 m, sur une emprise de 13,5 x 7,0 m
  - citerne souple  : bache PVC rectangulaire, environ 12,0 x 10,0 m, 1,35 m au
    centre, profil de coussin s'affaissant jusqu'au sol sur le pourtour
  - plateforme citerne : dalle de grave debordant de 2 m tout autour. PAS de
    merlon : une citerne souple se pose sur une plateforme dressee, sans talus.

Usage :
    python exporter_equipements.py poste sortie.json
    python exporter_equipements.py citerne sortie.json
    python exporter_equipements.py ensemble sortie.json
"""
import json
import math
import sys
from pathlib import Path

import numpy as np

import lecture_dxf
import montage as M
from camera import Camera
from exporter_blender import _quad, geometrie_cloture, geometrie_haie
from fiche_equipements import CHAMP, TANGAGE, SolPlat, geometrie_equipements

HERE = Path(__file__).resolve().parent
SORTIE = HERE / "equipements_sarnois-B"
W, H = 1180, 740

VUES = {
    "poste":    dict(cible="poste",   distance=26.0, azimut=200.0),
    "citerne":  dict(cible="citerne", distance=30.0, azimut=215.0),
    "bess":     dict(cible="bess",    distance=24.0, azimut=210.0),
    "haie":     dict(cible="haie",    distance=17.0, azimut=150.0,
                     hauteur_haie=4.5),
    "ensemble": dict(cible=None,      distance=85.0, azimut=12.0),
}


# Soleil reel de Sarnois au moment du reportage Antea (24/10/2025, 11 h 06
# locale, 49,682 N 1,918 E) : pvlib donne 140,5 deg d'azimut et 20,2 deg de
# hauteur. Sans soleil, le volume n'a plus d'aretes, la couvertine ne porte pas
# d'ombre, et surtout AUCUNE matiere ne peut ressortir : un mur eclaire par le
# seul ciel diffus rend un aplat, quel que soit le soin mis au materiau.
SOLEIL = {"azimut": 140.5, "elevation": 20.2, "force": 2.4, "angle": 1.5}


def azimut_ensoleille(angle_ouvrage, az_soleil, biais=34.0):
    """Azimut de prise de vue montrant le long pan que le soleil eclaire.

    Sans ce calcul, la vue tombait une fois sur deux sur la facade a l'ombre :
    on y voyait alors un rectangle uni, et tout le travail de matiere passait
    inapercu. Le biais decale la camera vers le pignon lui aussi eclaire, pour
    donner deux faces de valeurs differentes, donc du volume.
    """
    ca, sa = math.cos(math.radians(angle_ouvrage)), math.sin(math.radians(angle_ouvrage))
    ey = np.array([-sa, ca])                   # normale au long pan
    s = np.array([math.sin(math.radians(az_soleil)), math.cos(math.radians(az_soleil))])
    n = ey if float(np.dot(ey, s)) > 0 else -ey
    # la camera se met du cote eclaire ; elle regarde donc dans la direction -n,
    # tournee du biais vers le pignon que le soleil prend aussi
    d = -n
    signe = 1.0 if n[0] * s[1] - n[1] * s[0] > 0 else -1.0
    t = math.radians(biais * signe)
    d = np.array([d[0] * math.cos(t) - d[1] * math.sin(t),
                  d[0] * math.sin(t) + d[1] * math.cos(t)])
    return math.degrees(math.atan2(d[0], d[1])) % 360.0


def _base(centre, angle, L, l):
    ca, sa = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    ex = np.array([ca, sa]); ey = np.array([-sa, ca])
    c = np.array(centre, float)
    return c, ex, ey, [c + ex * (L / 2) * i + ey * (l / 2) * j
                       for i, j in ((-1, -1), (1, -1), (1, 1), (-1, 1))]


def boite(bloc, centre, angle, L, l, z0, z1):
    """Volume droit : quatre faces laterales et un toit."""
    _, _, _, k = _base(centre, angle, L, l)
    for i in range(4):
        a, b = k[i], k[(i + 1) % 4]
        bloc["f"].append(_quad(bloc["v"], [a[0], a[1], z0], [b[0], b[1], z0],
                               [b[0], b[1], z1], [a[0], a[1], z1]))
    bloc["f"].append(_quad(bloc["v"], *[[q[0], q[1], z1] for q in k]))


def _faces(k):
    """Les quatre pans, avec leur sens de parcours et leur normale sortante.

    `k` sort de `_base` dans le sens trigonometrique, donc la normale sortante
    est a droite du sens de parcours : rotation de -90 degres.
    """
    out = []
    for i in range(4):
        a, b = np.asarray(k[i], float), np.asarray(k[(i + 1) % 4], float)
        d = b - a
        L = float(np.linalg.norm(d))
        d = d / L
        out.append((a, d, L, np.array([d[1], -d[0]])))
    return out


def _mur_perce(bloc, a, d, L, z0, z1, trous):
    """Pan de mur moins ses ouvertures, par decoupe en bandes verticales.

    Sans cela, creuser un tableau ne sert a rien : le quad plein de la facade
    reste devant et masque la porte, le fond et les lamelles. C'etait le cas
    ici — la geometrie etait juste, simplement invisible.
    """
    bornes = sorted({0.0, L} | {s for t in trous for s in (t[0], t[1])})
    for i in range(len(bornes) - 1):
        s0, s1 = bornes[i], bornes[i + 1]
        if s1 - s0 < 1e-4:
            continue
        sm = (s0 + s1) / 2
        dedans = sorted([t for t in trous if t[0] - 1e-6 <= sm <= t[1] + 1e-6],
                        key=lambda t: t[2])
        p0, p1 = a + d * s0, a + d * s1
        zc = z0
        for t in dedans:
            if t[2] > zc + 1e-4:
                bloc["f"].append(_quad(bloc["v"], [p0[0], p0[1], zc], [p1[0], p1[1], zc],
                                       [p1[0], p1[1], t[2]], [p0[0], p0[1], t[2]]))
            zc = max(zc, t[3])
        if z1 > zc + 1e-4:
            bloc["f"].append(_quad(bloc["v"], [p0[0], p0[1], zc], [p1[0], p1[1], zc],
                                   [p1[0], p1[1], z1], [p0[0], p0[1], z1]))


def _creux(bloc, fond, plan, n, ex, u0, u1, z0, z1, prof=0.055):
    """Ouverture EN CREUX : quatre tableaux vers l'interieur, puis un fond.

    Une porte dessinee comme un simple rectangle de couleur sur la facade reste
    un rectangle de couleur. Ce qui la fait lire, c'est le filet d'ombre du
    tableau, donc il faut la geometrie du retrait, pas seulement la teinte.
    """
    ext = plan + n * 0.004                     # a peine en saillie, anti z-fighting
    itr = plan - n * prof
    for u in (u0, u1):                         # tableaux lateraux
        a, b = ext + ex * u, itr + ex * u
        bloc["f"].append(_quad(bloc["v"], [a[0], a[1], z0], [b[0], b[1], z0],
                               [b[0], b[1], z1], [a[0], a[1], z1]))
    for z in (z0, z1):                         # linteau et seuil
        a, b = ext + ex * u0, ext + ex * u1
        d, e = itr + ex * u0, itr + ex * u1
        bloc["f"].append(_quad(bloc["v"], [a[0], a[1], z], [b[0], b[1], z],
                               [e[0], e[1], z], [d[0], d[1], z]))
    a, b = itr + ex * u0, itr + ex * u1
    fond["f"].append(_quad(fond["v"], [a[0], a[1], z0], [b[0], b[1], z0],
                           [b[0], b[1], z1], [a[0], a[1], z1]))


def _lamelles(bloc, plan, n, ex, u0, u1, z0, z1, pas=0.075, prof=0.055):
    """Grille de ventilation a lamelles reelles, pas un rectangle plat.

    Chaque lamelle est un bandeau incline vers le bas et vers l'exterieur ; le
    vide entre deux lamelles laisse voir le fond sombre du creux. C'est ce qui
    donne la rayure horizontale caracteristique d'un poste, visible de loin.
    """
    nb = max(3, int((z1 - z0) / pas))
    for k in range(nb):
        zb = z0 + (k + 0.12) * (z1 - z0) / nb
        zh = z0 + (k + 0.82) * (z1 - z0) / nb
        av = plan - n * 0.004                  # bord bas, en avant
        ar = plan - n * prof * 0.85            # bord haut, au fond
        a, b = av + ex * u0, av + ex * u1
        d, e = ar + ex * u0, ar + ex * u1
        bloc["f"].append(_quad(bloc["v"], [a[0], a[1], zb], [b[0], b[1], zb],
                               [e[0], e[1], zh], [d[0], d[1], zh]))


def geometrie_poste(geo, zsol, oeil=None, cle="poste"):
    """Prefabrique peint, couvertine debordante, portes et grilles en creux.

    Cotes et dispositions relevees sur les PC5 HOCH (planche PC 5-1 / 5-2) :
    couvertine plus claire et debordante, socle enterre de 0,3 a 0,5 m avec
    remblai evase, deux portes sur un long pan, grilles de ventilation
    superposees sur l'autre et en pignon.

    `oeil` est la position (E, N) de l'observateur : les portes vont sur le long
    pan qui LUI fait face. Sans cela on modelise deux portes et on rend le dos.
    """
    g = geo[cle]
    c, ex, ey, _ = _base(g["centre"], g["angle"], g.get("L", 10.0), g.get("l", 3.0))
    L, l, h = g.get("L", 10.0), g.get("l", 3.0), 3.00
    beton = {"v": [], "f": []}
    grave = {"v": [], "f": []}
    couvertine = {"v": [], "f": []}
    acier = {"v": [], "f": []}
    creux = {"v": [], "f": []}                 # fonds d'ouverture, non eclaires

    # couvertine : debord de 0,15 m, 0,18 m d'epaisseur, teinte plus claire
    boite(couvertine, c, g["angle"], L + 0.30, l + 0.30, zsol + h, zsol + h + 0.18)

    # remblai evase au pied, 0,40 m de haut sur 0,55 m de large
    _, _, _, kb = _base(c, g["angle"], L, l)
    _, _, _, kh = _base(c, g["angle"], L + 1.10, l + 1.10)
    for i in range(4):
        a, b = kb[i], kb[(i + 1) % 4]
        d, e = kh[i], kh[(i + 1) % 4]
        grave["f"].append(_quad(grave["v"], [d[0], d[1], zsol], [e[0], e[1], zsol],
                                [b[0], b[1], zsol + 0.40], [a[0], a[1], zsol + 0.40]))
    # plateforme en grave : 13,5 x 7,0 m au plan
    _, _, _, k = _base(c, g["angle"], 13.5, 7.0)
    grave["f"].append(_quad(grave["v"], *[[q[0], q[1], zsol + 0.02] for q in k]))

    # 1. ou sont les ouvertures. Les portes vont sur le long pan qui regarde
    #    l'observateur ; les grilles de ventilation sur l'autre et en pignon.
    if oeil is None:
        cp = 1.0
    else:
        cp = 1.0 if float(np.dot(ey, np.asarray(oeil, float) - c)) > 0 else -1.0
    ouv = []
    for u in (-0.26, 0.10):
        ouv.append(dict(genre="porte", plan=c + ey * (l / 2) * cp, n=ey * cp, e=ex,
                        u0=L * u, u1=L * u + 1.10, z0=zsol + 0.42, z1=zsol + 2.62))
    for zz in (0.62, 1.66):
        ouv.append(dict(genre="grille", plan=c - ey * (l / 2) * cp, n=-ey * cp, e=ex,
                        u0=-L * 0.30, u1=-L * 0.30 + 1.70,
                        z0=zsol + zz, z1=zsol + zz + 0.62))
    for cote in (1.0, -1.0):
        ouv.append(dict(genre="grille", plan=c + ex * (L / 2) * cote, n=ex * cote, e=ey,
                        u0=-0.34, u1=0.34, z0=zsol + 2.00, z1=zsol + 2.40))

    # 2. les murs, PERCES de ces ouvertures, puis la dalle de toiture
    _, _, _, k = _base(c, g["angle"], L, l)
    faces = _faces(k)
    for a, d, Lf, nrm in faces:
        trous = []
        for o in ouv:
            if float(np.dot(nrm, o["n"])) < 0.9:
                continue
            s = sorted(float(np.dot(o["plan"] + o["e"] * u - a, d)) for u in (o["u0"], o["u1"]))
            trous.append((s[0], s[1], o["z0"], o["z1"]))
        _mur_perce(beton, a, d, Lf, zsol, zsol + h, trous)
    beton["f"].append(_quad(beton["v"], *[[q[0], q[1], zsol + h] for q in k]))

    # 3. tableaux, fonds, vantaux et lamelles dans les creux
    for o in ouv:
        _creux(beton, creux, o["plan"], o["n"], o["e"], o["u0"], o["u1"], o["z0"], o["z1"])
        if o["genre"] == "porte":
            # deux vantaux pleins, laissant un jeu de 15 mm au milieu et sur le
            # pourtour : c'est ce jeu qui fait la ligne d'ombre
            larg = o["u1"] - o["u0"]
            for v0, v1 in ((0.015, larg / 2 - 0.008), (larg / 2 + 0.008, larg - 0.015)):
                a = o["plan"] - o["n"] * 0.030 + o["e"] * (o["u0"] + v0)
                b = o["plan"] - o["n"] * 0.030 + o["e"] * (o["u0"] + v1)
                acier["f"].append(_quad(acier["v"],
                                        [a[0], a[1], o["z0"] + 0.015],
                                        [b[0], b[1], o["z0"] + 0.015],
                                        [b[0], b[1], o["z1"] - 0.015],
                                        [a[0], a[1], o["z1"] - 0.015]))
        else:
            _lamelles(acier, o["plan"], o["n"], o["e"], o["u0"] + 0.02, o["u1"] - 0.02,
                      o["z0"] + 0.02, o["z1"] - 0.02)
    return beton, grave, couvertine, acier, creux


# Meridien de la bache : super-ellipse d'exposants 2,8 / 2,2. Constantes de
# module parce que la geometrie ET les accessoires doivent poser sur LA MEME
# surface ; deux copies de la formule finiraient par diverger et les ferrures
# flotteraient au-dessus de la toile ou s'y enfonceraient.
CIT_NZ, CIT_NR = 2.8, 2.2


def _meridien_citerne(t, haut, tuck):
    """(rayon relatif, hauteur) a la fraction de hauteur t."""
    u = (1.0 - min(max(t, 0.0), 1.0) ** CIT_NZ) ** (1 / CIT_NR)
    return u * (1.0 - tuck * math.exp(-(t / 0.10) ** 2)), haut * t


def _rayon_plan_citerne(theta, cote):
    """Rayon du contour en plan : super-ellipse d'exposant 4, donc un rectangle
    a angles arrondis, comme la vue de dessus du plan."""
    a, b = cote[0] / 2, cote[1] / 2
    ct, st = math.cos(theta), math.sin(theta)
    return 1.0 / ((abs(ct / a) ** 4 + abs(st / b) ** 4) ** 0.25)


def geometrie_citerne(geo, zsol, cote=(11.7, 8.9), haut=1.50, marge=2.0,
                      tuck=0.045, cle="citerne"):
    """Bache souple, cotee et profilee sur la planche PC5 « CITERNE ~ 120 m3 ».

    Cotes du plan : 11,70 x 8,90 m en oeuvre, 1,50 m au centre, RAL 6011.

    PROFIL. La vue de face donne une hauteur qui suit (1 - u^1,6)^0,55, bien
    plus creusee sur les bords que le (1 - r^3)^0,5 que j'employais : c'est ce
    dernier qui donnait une galette etalee au lieu d'une bache. Et l'extremite
    bombe vers un dixieme de la hauteur puis REPIQUE vers l'interieur pour
    rejoindre le sol — la bache ne s'etale pas, elle se retourne sous
    elle-meme. Il faut donc mailler le long du MERIDIEN, de bas en haut, et non
    en fonction du rayon : une surface z(r) ne peut pas surplomber son appui.

    PAS de merlon, et la plateforme reste AU NIVEAU DU TERRAIN NATUREL : une
    dalle surelevee de 6 cm projetait, sous un soleil a 20 degres, un liseré
    d'ombre a la limite de l'herbe qui n'a pas lieu d'etre.
    """
    g = geo[cle]
    c, ex, ey, _ = _base(g["centre"], g["angle"], 1.0, 1.0)
    a, b = cote[0] / 2, cote[1] / 2
    pvc = {"v": [], "f": []}
    ntheta, nz = 72, 18

    # Flancs presque verticaux dans le premier tiers, dessus large et plat.
    # J'avais d'abord ajuste (1-u^1,6)^0,55 sur la vue de face de la planche
    # PC5, qui colle au dessin a 0,04 pres — mais le dessin est un schema, et
    # les photos de citernes en service montrent un PAIN, pas une lentille :
    # une membrane sous pression tend ses flancs au lieu de s'evaser. La
    # planche garde les cotes et la teinte, la photo donne la courbure.
    def rayon_plan(theta):
        return _rayon_plan_citerne(theta, cote)

    def meridien(t):
        return _meridien_citerne(t, haut, tuck)

    def pt(theta, t):
        u, z = meridien(t)
        R = rayon_plan(theta) * u
        p = c + ex * (R * math.cos(theta)) + ey * (R * math.sin(theta))
        return [p[0], p[1], zsol + 0.01 + z]

    # Sommets calcules d'abord, pour en deduire les UV EN METRES dont le
    # materiau a besoin : u = abscisse le long du contour, v = abscisse
    # curviligne du meridien depuis le sol. Les soudures de les sont a v
    # constant tous les 1,50 m, le fronçage de pied vit a petit v.
    pvc["uv"] = []
    P = [[pt(2 * math.pi * i / ntheta, j / (nz - 1)) for j in range(nz)]
         for i in range(ntheta + 1)]
    U = [0.0]
    for i in range(1, ntheta + 1):
        a0, b0 = P[i - 1][0], P[i][0]
        U.append(U[-1] + math.dist(a0, b0))
    V = []
    for i in range(ntheta + 1):
        col = [0.0]
        for j in range(1, nz):
            col.append(col[-1] + math.dist(P[i][j - 1], P[i][j]))
        V.append(col)
    for i in range(ntheta):
        for j in range(nz - 1):
            pvc["f"].append(_quad(pvc["v"], P[i][j], P[i + 1][j],
                                  P[i + 1][j + 1], P[i][j + 1]))
            pvc["uv"] += [[U[i], V[i][j]], [U[i + 1], V[i + 1][j]],
                          [U[i + 1], V[i + 1][j + 1]], [U[i], V[i][j + 1]]]
    # plateforme en grave, au niveau du terrain naturel
    plateforme = {"v": [], "f": []}
    _, _, _, k = _base(g["centre"], g["angle"],
                       cote[0] + 2 * marge, cote[1] + 2 * marge)
    plateforme["f"].append(_quad(plateforme["v"],
                                 *[[q[0], q[1], zsol + 0.005] for q in k]))
    return pvc, plateforme


def _cylindre(bloc, base, axe, rayon, longueur, n=12, capuchon=True):
    """Cylindre a `n` faces depuis `base`, le long de `axe`, avec son capuchon."""
    axe = np.asarray(axe, float)
    axe = axe / np.linalg.norm(axe)
    ref = np.array([0.0, 0.0, 1.0]) if abs(axe[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    e1 = np.cross(axe, ref); e1 /= np.linalg.norm(e1)
    e2 = np.cross(axe, e1)
    b = np.asarray(base, float)
    s = b + axe * longueur
    cer = [e1 * math.cos(2 * math.pi * k / n) * rayon
           + e2 * math.sin(2 * math.pi * k / n) * rayon for k in range(n + 1)]
    for k in range(n):
        bloc["f"].append(_quad(bloc["v"], list(b + cer[k]), list(b + cer[k + 1]),
                               list(s + cer[k + 1]), list(s + cer[k])))
    if capuchon:                                   # eventail de quads depuis l'axe
        for k in range(0, n, 2):
            bloc["f"].append(_quad(bloc["v"], list(s), list(s + cer[k]),
                                   list(s + cer[k + 1]), list(s + cer[k + 2])))


def accessoires_citerne(geo, zsol, cote=(11.7, 8.9), haut=1.50, tuck=0.045,
                        oeil=None, cle="citerne"):
    """Trop-plein, trappe de visite et raccord pompier.

    Positions relevees sur la vue de dessus de la planche PC5 : le trop-plein a
    4,40 m du centre vers une extremite, la trappe de visite au centre, tous
    deux decales de 0,38 m de l'axe. Le raccord pompier vient du plan de
    fabrication du fournisseur — « Raccord Pompier 4" avec Anti-vortex +
    Manchon thermique » — et des photos, ou il se dresse en pied de flanc,
    rouge, seul element franchement colore de l'ouvrage.

    Les accessoires se posent SUR la membrane : leur altitude se deduit du
    meridien, sinon ils flottent ou s'enfoncent.
    """
    g = geo[cle]
    c, ex, ey, _ = _base(g["centre"], g["angle"], 1.0, 1.0)
    a, b = cote[0] / 2, cote[1] / 2
    acier = {"v": [], "f": []}
    pompier = {"v": [], "f": []}
    plaque = {"v": [], "f": []}

    def sur_la_bache(fu, fv):
        """Point de la membrane a l'aplomb de (fu, fv), fractions des demi-axes."""
        rho = min((abs(fu) ** 4 + abs(fv) ** 4) ** 0.25, 1.0)
        z = haut * (1.0 - rho ** CIT_NR) ** (1 / CIT_NZ)
        p = c + ex * (fu * a) + ey * (fv * b)
        return np.array([p[0], p[1], zsol + 0.01 + z])

    def sur_le_flanc(theta, t):
        """Point du flanc a l'angle plan `theta` et a la fraction de hauteur t."""
        u, z = _meridien_citerne(t, haut, tuck)
        R = _rayon_plan_citerne(theta, cote) * u
        p = c + ex * (R * math.cos(theta)) + ey * (R * math.sin(theta))
        return np.array([p[0], p[1], zsol + 0.01 + z])

    # trop-plein : col de cygne, tube vertical puis coude horizontal
    P = sur_la_bache(-0.752, 0.085)
    _cylindre(acier, P - np.array([0.0, 0.0, 0.05]), (0, 0, 1), 0.070, 0.34)
    coude = P + np.array([0.0, 0.0, 0.29])
    _cylindre(acier, coude, (ex[0], ex[1], 0.0), 0.070, 0.24)

    # trappe de visite : couronne boulonnee, a peine en saillie
    T = sur_la_bache(-0.001, 0.085)
    _cylindre(acier, T - np.array([0.0, 0.0, 0.03]), (0, 0, 1), 0.225, 0.075)

    # raccord pompier : au pied du long pan qui regarde l'observateur
    cote_v = 1.0
    if oeil is not None:
        cote_v = 1.0 if float(np.dot(ey, np.asarray(oeil, float) - c)) > 0 else -1.0
    pied = c + ex * (0.15 * a) + ey * (cote_v * (b * (1.0 - tuck) + 0.34))
    base = np.array([pied[0], pied[1], zsol + 0.01])
    _cylindre(pompier, base, (0, 0, 1), 0.155, 0.46)
    # tete de raccord, un peu plus large, et la sortie DN100 vers l'exterieur
    _cylindre(pompier, base + np.array([0.0, 0.0, 0.46]), (0, 0, 1), 0.185, 0.09)
    sortie = base + np.array([0.0, 0.0, 0.30])
    _cylindre(pompier, sortie, (ey[0] * cote_v, ey[1] * cote_v, 0.0), 0.055, 0.22)

    # plaques signaletiques, juste au-dessus du raccord. Mesurees sur photo :
    # environ 0,40 x 0,35 m rapportees a la longueur de la citerne. A 30 m
    # elles font une tache claire franche sur le vert, donc elles comptent.
    # Elles epousent la membrane : il faut la NORMALE locale, pas un plan vertical.
    # angle plan du point de pose : celui dont la composante le long de ex vaut
    # la meme abscisse que le raccord, sur le flanc regarde par l'observateur
    depart = 0.0 if cote_v > 0 else 180.0
    cible = 0.15 * a
    theta0 = min(np.radians(np.arange(depart + 12, depart + 169, 0.25)),
                 key=lambda th: abs(_rayon_plan_citerne(th, cote) * math.cos(th) - cible))
    # hauteur : au niveau de la tete du raccord, comme sur les photos.
    # Le corps monte a 0,46 m et la tete a 0,55 m ; 0,35 de meridien
    # place le centre des plaques a 0,52 m.
    t0 = 0.35
    P = sur_le_flanc(theta0, t0)
    tu = sur_le_flanc(theta0 + 0.02, t0) - sur_le_flanc(theta0 - 0.02, t0)
    tv = sur_le_flanc(theta0, t0 + 0.02) - sur_le_flanc(theta0, t0 - 0.02)
    tu /= np.linalg.norm(tu)
    tv /= np.linalg.norm(tv)
    n = np.cross(tu, tv)
    n /= np.linalg.norm(n)
    if float(np.dot(n[:2], ey * cote_v)) < 0:
        n = -n

    def carte(bloc, centre, larg, haut_p, recul):
        o = centre + n * recul
        q = [o + tu * (larg / 2) * i + tv * (haut_p / 2) * j
             for i, j in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        bloc["f"].append(_quad(bloc["v"], *[list(x) for x in q]))

    # La paire se decale le long du flanc pour DEGAGER le raccord : a la meme
    # abscisse, le corps de 0,31 m de large en masquait une.
    Pp = P + tu * 0.62
    A = Pp + tu * 0.23
    carte(pompier, A, 0.40, 0.30, 0.008)         # la reglementaire, a bord rouge
    carte(plaque, A, 0.33, 0.23, 0.012)
    carte(plaque, Pp - tu * 0.23, 0.32, 0.24, 0.010)   # celle du fabricant
    return acier, pompier, plaque


def _loin(bloc, E0, N0, dmin):
    """Retire les faces dont tous les sommets sont a moins de `dmin` de l'oeil."""
    V = np.array(bloc["v"], float)
    if not len(V):
        return bloc["v"], bloc["f"], 0
    proche = np.hypot(V[:, 0] - E0, V[:, 1] - N0) < dmin
    garde = [f for f in bloc["f"] if not all(proche[i] for i in f)]
    return bloc["v"], garde, len(bloc["f"]) - len(garde)


def exporter(nom_vue, sortie):
    v = VUES[nom_vue]
    scn = lecture_dxf.lire(M.DXF)
    geo = geometrie_equipements(M.DXF)
    q = np.array([t.q for t in scn.tables])
    z0 = float(np.median(q[:, :, 2])) - 1.5
    if v["cible"] == "haie":
        # Viser PERPENDICULAIREMENT au plus long segment : de biais on regarde
        # l'extremite en enfilade et la haie se reduit a un moignon.
        pts = [np.asarray(p, float) for p in scn.lignes["haie"][0]["pts"]]
        i = max(range(len(pts) - 1), key=lambda k: np.linalg.norm(pts[k + 1] - pts[k]))
        cible = (pts[i] + pts[i + 1]) / 2
        d = pts[i + 1] - pts[i]
        v = dict(v, azimut=(math.degrees(math.atan2(-d[1], d[0]))) % 360.0,
                 au_soleil=False)
    elif v["cible"]:
        cible = np.asarray(geo[v["cible"]]["centre"], float)
    else:
        cible = (geo["poste"]["centre"] + geo["citerne"]["centre"]) / 2
    azimut = v["azimut"]
    if v.get("cible") and v["cible"] in geo and v.get("au_soleil", True):
        azimut = azimut_ensoleille(geo[v["cible"]]["angle"], SOLEIL["azimut"])
        print(f"  vue placee au soleil : azimut {azimut:.1f} deg "
              f"(au lieu de {v['azimut']:.0f})")
    a = math.radians(azimut)
    E0 = cible[0] - v["distance"] * math.sin(a)
    N0 = cible[1] - v["distance"] * math.cos(a)

    beton, grave, couvertine, acier_p, creux = geometrie_poste(geo, z0, (E0, N0))
    # Le plan porte DEUX batiments : le poste de transformation (UNI_PDT, 10 m)
    # et le poste de livraison (UNI_PDL, 12 m). Je ne rendais que le premier.
    if "pdl" in geo:
        for cible, part in zip((beton, grave, couvertine, acier_p, creux),
                               geometrie_poste(geo, z0, (E0, N0), cle="pdl")):
            n0 = len(cible["v"])
            cible["v"] += part["v"]
            cible["f"] += [[i + n0 for i in ff] for ff in part["f"]]
    pvc, plateforme = geometrie_citerne(geo, z0)
    # Citerne de refroidissement du BESS : meme ouvrage, plus petit. La planche
    # PC5 cote un modele 60 m3 a 8,1 x 7,4 m pour 1,1 m ; l'emprise du plan la
    # donne plus etroite, on garde sa largeur reelle.
    if "refroidissement" in geo:
        gr_ = geo["refroidissement"]
        pv2, pl2 = geometrie_citerne(geo, z0, cote=(min(gr_["L"], 8.1), gr_["l"]),
                                     haut=1.10, marge=1.2, cle="refroidissement")
        for cible, part in ((pvc, pv2), (plateforme, pl2)):
            n0 = len(cible["v"])
            cible["v"] += part["v"]
            cible["f"] += [[i + n0 for i in ff] for ff in part["f"]]
            if "uv" in cible and "uv" in part:
                cible["uv"] += part["uv"]
    acc_acier, acc_pompier, acc_plaque = accessoires_citerne(geo, z0, oeil=(E0, N0))

    # Conteneurs : le BESS de Sarnois occupe 8,06 x 6,00 m, ce qui loge DEUX
    # conteneurs de 6,06 x 2,44 m cote a cote avec le passage reglementaire —
    # c'est la disposition des plans de reperage HOCH, qui montrent plusieurs
    # « conteneurs de batteries » groupes.
    tole = {"v": [], "f": []}; porte_c = {"v": [], "f": []}
    coin = {"v": [], "f": []}; creux_c = {"v": [], "f": []}
    if "bess" in geo:
        gb = geo["bess"]
        cb, exb, eyb, _ = _base(gb["centre"], gb["angle"], 1.0, 1.0)
        for signe in (-1.0, 1.0):
            ctr = cb + eyb * (signe * 1.67)
            for bloc, part in zip((tole, porte_c, coin, creux_c),
                                  geometrie_conteneur(ctr, gb["angle"], z0, 6.06, 2.44, 2.90,
                                                      bess=True, oeil=(E0, N0))):
                n0 = len(bloc["v"])
                bloc["v"] += part["v"]
                bloc["f"] += [[i + n0 for i in f] for f in part["f"]]
        _, _, _, kb = _base(gb["centre"], gb["angle"], gb["L"] + 1.6, gb["l"] + 1.6)
        grave["f"].append(_quad(grave["v"], *[[q[0], q[1], z0 + 0.005] for q in kb]))
    # local de stockage materiel : le MEME conteneur, sans ventilation
    if "stockage" in geo:
        gs = geo["stockage"]
        for bloc, part in zip((tole, porte_c, coin, creux_c),
                              geometrie_conteneur(gs["centre"], gs["angle"], z0,
                                                  gs["L"], gs["l"], 2.59,
                                                  bess=False, oeil=(E0, N0))):
            n0 = len(bloc["v"])
            bloc["v"] += part["v"]
            bloc["f"] += [[i + n0 for i in f] for f in part["f"]]
        _, _, _, ks = _base(gs["centre"], gs["angle"], gs["L"] + 1.4, gs["l"] + 1.4)
        grave["f"].append(_quad(grave["v"], *[[q[0], q[1], z0 + 0.005] for q in ks]))
    # La cloture passe parfois a quelques metres de l'oeil : un poteau
    # occupe alors la moitie de la planche et masque l'ouvrage. On la
    # coupe pres de l'oeil, comme un photographe se serait deplace.
    cartes = {"v": [], "f": [], "uv": []}
    bois_haie = {"v": [], "f": []}
    haie = geometrie_haie(scn, lambda X, Y: z0, E0, N0,
                          hauteur=float(v.get("hauteur_haie", M.HAUTEUR_HAIE)),
                          dmax=260.0, cartes=cartes, bois=bois_haie)
    bois, grillage = geometrie_cloture(scn, lambda X, Y: z0, E0, N0, dmax=260.0)

    # Portails : trois sur le plan de Sarnois, deux de 5 m et un de 7 m. Il faut
    # OUVRIR la cloture a leur emplacement, sinon le grillage et ses poteaux
    # traversent les vantaux.
    cadre_p = {"v": [], "f": []}; barreau_p = {"v": [], "f": []}
    ouvertures = []
    for pt in geo.get("portails", []):
        Lp = max(pt["L"], pt["l"])
        c1, b1 = geometrie_portail(pt["centre"], pt["angle"], z0, L=Lp)
        for bloc, part in ((cadre_p, c1), (barreau_p, b1)):
            n0 = len(bloc["v"])
            bloc["v"] += part["v"]
            bloc["f"] += [[i + n0 for i in ff] for ff in part["f"]]
        ouvertures.append((pt["centre"][0], pt["centre"][1], Lp / 2 + 0.4))
    for bloc in (bois, grillage):
        _trouer(bloc, ouvertures)
    for bloc in (bois, grillage):
        # plafonne : sur la vue d'ensemble a 85 m, 0,72 x distance vidait
        # tout le premier plan de la cloture.
        bloc["v"], bloc["f"], _ = _loin(bloc, E0, N0,
                                        min(0.72 * v["distance"], 18.0))

    sol = {"v": [], "f": []}
    pas, rayon = 8.0, 200.0
    n = int(rayon / pas)
    for i in range(-n, n):
        for j in range(-n, n):
            x0, y0 = i * pas, j * pas
            if math.hypot(x0, y0) > rayon:
                continue
            sol["f"].append(_quad(sol["v"], [x0, y0, 0.0], [x0 + pas, y0, 0.0],
                                  [x0 + pas, y0 + pas, 0.0], [x0, y0 + pas, 0.0]))

    def local(bloc):
        bloc["v"] = [[p[0] - E0, p[1] - N0, p[2] - z0] for p in bloc["v"]]
        return bloc

    f1 = (W / 2) / math.tan(math.radians(CHAMP / 2))
    cam = Camera(W, H, azimut, TANGAGE, 0.0, 26.0, 1.60)
    cam.f_px = f1
    data = {
        "camera": {"largeur": W, "hauteur": H, "f_px": f1,
                   "position": [0.0, 0.0, 1.60],
                   "R": [[float(x) for x in ligne] for ligne in cam.R]},
        "soleil": SOLEIL,
        "ciel": [168, 186, 204],
        "sol_rgb": [101, 116, 71],
        # Pas de photo derriere cette planche, donc AUCUNE cible a
        # atteindre : le gain vaut 1 et la base est choisie pour que le
        # rendu tombe sur un feuillage d'automne credible. Le gain
        # mesure de `materiaux_proc` ne vaut que pour un montage sur
        # photo, et pour la distance a laquelle il a ete mesure.
        "materiaux": {"haie_rgb": [104, 118, 68],
                      "gain_haie": [1.0, 1.0, 1.0]},
        "objets": [
            {"materiau": "beton", **local(beton)},
            {"materiau": "couvertine", **local(couvertine)},
            {"materiau": "grave", **local(grave)},
            {"materiau": "menuiserie", **local(acier_p)},
            {"materiau": "creux", **local(creux)},
            {"materiau": "pvc", **local(pvc)},
            {"materiau": "ferrure", **local(acc_acier)},
            {"materiau": "pompier", **local(acc_pompier)},
            {"materiau": "plaque", **local(acc_plaque)},
            {"materiau": "tole", **local(tole)},
            {"materiau": "menuiserie", **local(porte_c)},
            {"materiau": "coin", **local(coin)},
            {"materiau": "creux", **local(creux_c)},
            {"materiau": "menuiserie", **local(cadre_p)},
            {"materiau": "menuiserie", **local(barreau_p)},
            {"materiau": "grave", **local(plateforme)},
            {"materiau": "bois", **local(bois)},
            {"materiau": "grillage", **local(grillage)},
            {"materiau": "haie", **local(haie)},
            {"materiau": "feuillage", **local(cartes)},
            {"materiau": "branche", **local(bois_haie)},
            {"materiau": "sol_ombre", **sol},
        ],
        "vue": {"nom": nom_vue, "est": E0, "nord": N0, "z_sol": z0,
                "azimut": azimut, "distance": v["distance"]},
    }
    Path(sortie).write_text(json.dumps(data), encoding="utf-8")
    for o in data["objets"]:
        if o["f"]:
            print(f"  {o['materiau']:11s} {len(o['f']):6d} faces")
    print(f"ecrit : {sortie}")


# ------------------------------------------------------------------ conteneurs
# Un local de stockage materiel et un conteneur BESS sont le MEME objet : un
# conteneur maritime. Les PC5 les cotent 6,0 a 6,1 x 2,4 a 3,0 m pour 2,6 a
# 3,0 m de haut, et 12,2 m pour un 40 pieds. Ce qui les caracterise, et qu'il
# faut donc modeliser, c'est l'ONDULATION du bardage : des nervures verticales
# trapezoidales entre une lisse basse et une lisse haute lisses. Les portes ne
# sont pas encastrees mais en SAILLIE sur le bardage, comme le montrent les
# photos d'ateliers.
PAS_ONDULE, PROF_ONDULE = 0.28, 0.036          # norme ISO : pas 280 mm, 36 mm


def _bardage(bloc, a, d, n, L, z0, z1, pas=PAS_ONDULE, prof=PROF_ONDULE):
    """Pan de bardage ondule, nervures verticales, entre z0 et z1."""
    profil = [(0.00, 0.0), (0.08, 0.0), (0.13, prof), (0.23, prof), (0.28, 0.0)]
    s = 0.0
    while s < L - 1e-6:
        for (u0, e0), (u1, e1) in zip(profil[:-1], profil[1:]):
            s0, s1 = min(s + u0 * pas / 0.28, L), min(s + u1 * pas / 0.28, L)
            if s1 - s0 < 1e-6:
                continue
            p0 = a + d * s0 + n * e0
            p1 = a + d * s1 + n * e1
            bloc["f"].append(_quad(bloc["v"], [p0[0], p0[1], z0], [p1[0], p1[1], z0],
                                   [p1[0], p1[1], z1], [p0[0], p0[1], z1]))
        s += pas


def _bandeau(bloc, a, d, n, L, z0, z1, saillie=0.012):
    """Lisse lisse (haute ou basse), legerement en avant des nervures."""
    p0 = a + n * saillie
    p1 = a + d * L + n * saillie
    bloc["f"].append(_quad(bloc["v"], [p0[0], p0[1], z0], [p1[0], p1[1], z0],
                           [p1[0], p1[1], z1], [p0[0], p0[1], z1]))


def geometrie_conteneur(centre, angle, zsol, L=6.06, l=2.44, h=2.59,
                        portes=True, bess=False, oeil=None):
    """Conteneur : bardage ondule, lisses, pieces de coin, portes en saillie.

    `bess` ajoute la grille de ventilation en pignon, qui est ce qui distingue
    visuellement un conteneur batterie d'un local de stockage.
    """
    c, ex, ey, k = _base(centre, angle, L, l)
    tole = {"v": [], "f": []}
    porte = {"v": [], "f": []}
    coin = {"v": [], "f": []}
    creux = {"v": [], "f": []}
    zb, zh = zsol + 0.11, zsol + h - 0.16
    cp = 1.0
    if oeil is not None:
        cp = 1.0 if float(np.dot(ey, np.asarray(oeil, float) - c)) > 0 else -1.0

    for a, d, Lf, nrm in _faces(k):
        _bardage(tole, a, d, nrm, Lf, zb, zh)
        _bandeau(tole, a, d, nrm, Lf, zsol, zb)               # lisse basse
        _bandeau(tole, a, d, nrm, Lf, zh, zsol + h)           # lisse haute
    tole["f"].append(_quad(tole["v"], *[[q[0], q[1], zsol + h] for q in k]))

    # pieces de coin, petits blocs sombres qui datent l'objet
    for q in k:
        for z0, z1 in ((zsol, zsol + 0.16), (zsol + h - 0.16, zsol + h)):
            boite(coin, q, angle, 0.30, 0.30, z0, z1)

    # portes : panneaux plans EN SAILLIE sur le bardage, sur le long pan vu
    if portes:
        # Panneau EN RELIEF, pas un simple quad : c'est le retour d'epaisseur
        # qui pose la ligne d'ombre et fait lire la porte. Sans lui, la porte a
        # la meme teinte que le bardage et disparait.
        n = ey * cp
        pied = c + ey * (l / 2 + PROF_ONDULE) * cp
        av = 0.045                                            # saillie sur les crets
        for u in (-0.27, 0.09):
            s0, s1 = L * u, L * u + 2.10
            z0, z1 = zsol + 0.16, zsol + h - 0.20
            f0, f1 = pied + ex * s0, pied + ex * s1
            g0, g1 = f0 + n * av, f1 + n * av
            porte["f"].append(_quad(porte["v"], [g0[0], g0[1], z0], [g1[0], g1[1], z0],
                                    [g1[0], g1[1], z1], [g0[0], g0[1], z1]))
            for p, q in ((f0, g0), (g1, f1)):                 # retours lateraux
                porte["f"].append(_quad(porte["v"], [p[0], p[1], z0], [q[0], q[1], z0],
                                        [q[0], q[1], z1], [p[0], p[1], z1]))
            for z in (z0, z1):                                # retours haut et bas
                porte["f"].append(_quad(porte["v"], [f0[0], f0[1], z], [f1[0], f1[1], z],
                                        [g1[0], g1[1], z], [g0[0], g0[1], z]))
            am0 = pied + ex * (L * u + 1.04) + n * (av + 0.004)
            am1 = pied + ex * (L * u + 1.06) + n * (av + 0.004)
            creux_p = am0, am1
            porte["f"].append(_quad(porte["v"], [am0[0], am0[1], z0], [am1[0], am1[1], z0],
                                    [am1[0], am1[1], z1], [am0[0], am0[1], z1]))
    # ventilation du BESS : large grille a lamelles en pignon
    if bess:
        # CAISSON RAPPORTE, pas un creux : le bardage est ondule, donc les
        # tableaux d'une ouverture creusee ne se raccordent a rien et la grille
        # rend un semis de points. Sur les photos d'atelier, le bloc de
        # ventilation est boulonne EN SAILLIE sur le pignon.
        for cote in (1.0, -1.0):
            plan = c + ex * (L / 2 + PROF_ONDULE) * cote
            n = ex * cote
            u0, u1 = -l * 0.34, l * 0.34
            z0, z1 = zsol + 0.55, zsol + h - 0.35
            av = 0.10
            for p0, p1 in ((u0, u0), (u1, u1)):               # joues du caisson
                a0 = plan + ey * p0
                a1 = plan + ey * p1 + n * av
                coin["f"].append(_quad(coin["v"], [a0[0], a0[1], z0], [a1[0], a1[1], z0],
                                       [a1[0], a1[1], z1], [a0[0], a0[1], z1]))
            for z in (z0, z1):                                # chapeau et seuil
                a0, a1 = plan + ey * u0, plan + ey * u1
                b0, b1 = a0 + n * av, a1 + n * av
                coin["f"].append(_quad(coin["v"], [a0[0], a0[1], z], [a1[0], a1[1], z],
                                       [b1[0], b1[1], z], [b0[0], b0[1], z]))
            a0, a1 = plan + ey * u0, plan + ey * u1           # fond sombre
            creux["f"].append(_quad(creux["v"], [a0[0], a0[1], z0], [a1[0], a1[1], z0],
                                    [a1[0], a1[1], z1], [a0[0], a0[1], z1]))
            _lamelles(porte, plan + n * av, n, ey, u0 + 0.02, u1 - 0.02,
                      z0 + 0.03, z1 - 0.03, pas=0.10, prof=av)
    return tole, porte, coin, creux


# --------------------------------------------------------------------- portail
def geometrie_portail(centre, angle, zsol, L=5.0, h=2.00, pas_barreau=0.125):
    """Portail a deux vantaux, barreaudage vertical, entre deux montants.

    Cote sur la planche PC5 : 2 m de haut, double battant. Le plan de Sarnois
    porte deux blocs `UNI_Portail 5m` et un de 7 m. C'est l'ouvrage le plus
    frequent des dossiers — 109 mentions sur 19 dossiers — et il se trouve a
    l'entree du site, donc exactement la ou se prennent les vues rapprochees.
    """
    c, ex, ey, _ = _base(centre, angle, 1.0, 1.0)
    cadre = {"v": [], "f": []}
    barreau = {"v": [], "f": []}

    def montant(s, cote_l, cote_e, z0, z1):
        """Element rectangulaire vertical de section cote_l x cote_e."""
        q = [c + ex * (s + cote_l / 2 * i) + ey * (cote_e / 2 * j)
             for i, j in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        for k in range(4):
            a, b = q[k], q[(k + 1) % 4]
            cadre["f"].append(_quad(cadre["v"], [a[0], a[1], z0], [b[0], b[1], z0],
                                    [b[0], b[1], z1], [a[0], a[1], z1]))
        cadre["f"].append(_quad(cadre["v"], *[[p[0], p[1], z1] for p in q]))

    # les deux montants de part et d'autre de l'ouverture
    for s in (-L / 2 - 0.09, L / 2 + 0.09):
        montant(s, 0.16, 0.16, zsol, zsol + h + 0.12)

    # chaque vantail : deux traverses, deux dormants, puis le barreaudage
    for signe in (-1.0, 1.0):
        s0 = 0.02 * signe
        s1 = (L / 2 - 0.02) * signe
        ga, dr = min(s0, s1), max(s0, s1)
        for z0, z1 in ((zsol + 0.06, zsol + 0.16), (zsol + h - 0.10, zsol + h)):
            a = c + ex * ga
            b = c + ex * dr
            cadre["f"].append(_quad(cadre["v"], [a[0], a[1], z0], [b[0], b[1], z0],
                                    [b[0], b[1], z1], [a[0], a[1], z1]))
        for s in (ga, dr):                      # dormants du vantail
            a = c + ex * s - ey * 0.03
            b = c + ex * s + ey * 0.03
            cadre["f"].append(_quad(cadre["v"], [a[0], a[1], zsol + 0.06],
                                    [b[0], b[1], zsol + 0.06],
                                    [b[0], b[1], zsol + h], [a[0], a[1], zsol + h]))
        nb = max(2, int((dr - ga - 0.10) / pas_barreau))
        for k in range(1, nb):
            s = ga + 0.05 + k * (dr - ga - 0.10) / nb
            a = c + ex * (s - 0.011)
            b = c + ex * (s + 0.011)
            barreau["f"].append(_quad(barreau["v"], [a[0], a[1], zsol + 0.16],
                                      [b[0], b[1], zsol + 0.16],
                                      [b[0], b[1], zsol + h - 0.10],
                                      [a[0], a[1], zsol + h - 0.10]))
    return cadre, barreau


def _trouer(bloc, ouvertures):
    """Retire les faces dont un sommet tombe dans une des `ouvertures`.

    `ouvertures` : suite de (est, nord, rayon), un rayon PAR portail — un rayon
    commun cale sur le plus large ouvrirait trop la cloture aux petits.

    Sert a ouvrir la cloture a l'emplacement des portails : sans cela, le
    grillage traverse le vantail.
    """
    V = np.array(bloc["v"], float)
    if not len(V):
        return bloc
    proche = np.zeros(len(V), bool)
    for e, n, r in ouvertures:
        proche |= np.hypot(V[:, 0] - e, V[:, 1] - n) < r
    bloc["f"] = [f for f in bloc["f"] if not any(proche[i] for i in f)]
    return bloc


if __name__ == "__main__":
    exporter(sys.argv[1], sys.argv[2])
