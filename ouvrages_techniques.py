#!/usr/bin/env python3
"""Volumes des ouvrages techniques, depuis le plan, aux gabarits UNITe.

CE QUE CE MODULE REPARE
-----------------------
`exporter_blender` ne montait que les tables, la clôture et la haie. Portail,
poste, local, citerne : aucun. Ces volumes existaient pourtant, écrits dans
`exemples/casxcas/exporter_gannay.py` — du code de projet, jamais remonté.

Cela ne se voyait pas tant que les points de vue restaient à cent mètres. Sur
Saint-Cyr, le premier cas où l'on photographie à quinze mètres de la clôture,
le montage montrait des poteaux là où le plan porte un portail à douze mètres
et une aire d'aspiration à **1,2 degré de l'axe de visée**.

LE PLAN DONNE LES COTES, LE GABARIT NE SERT QUE DE SECOURS
-----------------------------------------------------------
J'ai d'abord tenu l'inverse — « un rectangle de poste sur un plan est un repère
graphique » — et cela produisait deux défauts visibles à la fois :

  - la bâche incendie de Saint-Cyr est dessinée **8,08 x 7,40 m** et longe la
    clôture. Montée au gabarit de 11,70 x 8,90, elle débordait de 1,8 m de
    chaque côté : la clôture la traversait.
  - le poste, lui, est dessiné **12,00 x 3,00 m**, soit le gabarit au
    centimètre. Là où les deux sources existent, elles concordent.

Le plan est le choix du projet, le gabarit une moyenne maison. L'ordre est donc
le polygone fermé du plan, puis `cotes_normalisees` du bilan, puis le gabarit.
La HAUTEUR, elle, n'est jamais sur un plan en vue de dessus : elle vient
toujours du bilan ou du gabarit.

⚠️ `ordre_cotes` du bilan donne le sens de chaque nombre — « largeur x longueur
x hauteur » pour le PTR, « longueur x largeur x hauteur » pour le PDL. C'est lui
qui fait foi, jamais la position dans la chaîne. Un poste de 12 x 3 m dessiné
3 x 12 se dessine parfaitement et ne se voit pas.

LES SURFACES VIENNENT DU PLAN, LES VOLUMES N'EN INVENTENT AUCUNE
------------------------------------------------------------------
C'est la correction qui a demande quatre iterations, parce que le defaut ne se
lisait pas sur le rendu : on y voyait « des elements qui se melangent », sans
pouvoir dire lequel avait tort. Il a fallu poser la geometrie exportee a plat
et la comparer au plan.

`geometrie_poste` et `geometrie_citerne` ajoutent chacune un TABLIER DE GRAVE
autour de l'ouvrage. C'est juste quand l'appelant leur donne une geometrie
choisie a la main, comme le faisait `exporter_gannay`. Pilote par un plan, cela
fabrique des surfaces qui n'y sont pas. Mesure sur Saint-Cyr :

    dessine au plan            fabrique par le code
    PDL   36 + 18 + 12 m2      3 tabliers de 94,5 m2  =  283,5 m2
    bache        59,8 m2       1 plateforme de 72,8 m2 =  72,8 m2
                               ------------------------------------
                               356 m2 de grave hors plan

Ces tabliers se recouvraient entre eux — les trois postes sont a un metre l'un
de l'autre — et recouvraient la bache, la cloture et la haie. D'ou « des
conflits entre des elements qui ne sont pas en conflit sur le plan de masse ».

Or LE PLAN DESSINE DEJA SES SURFACES : `UNI_VRD_Plateforme` (133,8 et 94,4 m2)
et trois pistes lourdes a creer. Les trois postes reposent a 100 % dessus. La
bache, elle, n'y repose qu'a 6 % : le plan ne lui donne pas de plateforme, et
il ne faut donc pas lui en mettre une.

La regle est donc : une SURFACE se lit sur le plan et nulle part ailleurs ; un
VOLUME se pose dessus sans rien ajouter au sol. Et les surfaces du plan se
recouvrent entre elles — 356 m2 sur Saint-Cyr — il faut donc les UNIR avant de
les mailler, faute de quoi deux nappes coplanaires clignotent l'une sur l'autre.

UN PORTAIL EST UN SEGMENT DE CLOTURE, PAS UN OUVRAGE POSE A COTE
-----------------------------------------------------------------
La couche `UNI_portail` de Saint-Cyr ne porte aucune polyligne : six hachures,
neuf lignes et six arcs. Prendre chaque tracé pour un portail en donnait quinze,
emmêlés les uns dans les autres, et orientés « comme la clôture la plus proche »
faute de mieux.

Les six hachures sont en fait six **vantaux** de 3,50 m, deux par portail, et
leurs pointes de pivot sont exactement les deux bouts d'un segment de clôture de
7,00 m. Le portail EST ce segment : position, largeur et cap se lisent dessus,
sans gabarit ni approximation. Et il faut alors **ouvrir la clôture** à cet
endroit, faute de quoi le grillage traverse le vantail.
"""
import math
import re

import numpy as np

#: Gabarits UNITe, employés quand le plan ne dessine rien d'exploitable.
#: Longueur, largeur, hauteur en mètres.
GABARITS = {
    "pdl": dict(L=12.0, l=3.0, h=3.0),        # poste de livraison + transfo
    "ptr": dict(L=10.0, l=3.0, h=3.0),        # transformation seule
    "local": dict(L=6.06, l=2.44, h=2.59),    # conteneur 20 pieds
    # Catalogue UNITe, ligne « Citerne incendie — 120 » : 11,7 x 9,3 x 1 m,
    # 104 m2. La valeur portee ici jusqu'au 30/09/2026 — 11,7 x 8,9 x 1,50 —
    # melangeait l'empreinte de la 120 et la hauteur de la 60. Le contrat fait
    # desormais voyager le catalogue, qui tranche empreinte par empreinte.
    "citerne": dict(L=11.7, l=9.3, h=1.00),   # reserve souple 120 m3
    "portail": dict(L=7.0, h=2.0),
    # Tableau bilan AUZ V3, feuille « Batteries de stockage » : « Conteneur
    # 20 pieds (6x3x3m) ». Le plan le confirme au centimetre — le bloc
    # `BESS Skyray` mesure 6,06 x 3,00 m, soit 18,2 m2 pour les 18 m2 comptes
    # a la feuille « Projet ». La HAUTEUR, elle, ne vient que d'ici : c'est
    # 3,00 m, et non les 2,59 m d'un vrai conteneur 20 pieds maritime.
    "bess": dict(L=6.0, l=3.0, h=3.0),
}

#: Categorie du plan -> ouvrage a monter. Le portail n'y est pas : il se lit
#: sur la clôture, pas sur un polygone pose a cote.
#:
#: `refroidissement` monte une CITERNE et non un groupe froid : le MTEXT de la
#: couche dit « Citerne Souple / 120m3 / Refroidissement des Conteneurs ». Le
#: contour aplati mesure 11,70 x 9,32 m sur les deux plans qui en portent une,
#: soit le gabarit `citerne` — 104 m2 au bilan — au centimetre sur la longueur.
#: C'est donc la meme bache que celle du SDIS, a un autre usage.
#: ⚠️ LA « ZONE DE REMISE » EST UN VOLUME, ET JE L'AI CRUE PLATE.
#: Le 24/09/2026, faute de source, j'avais tranche pour une aire durcie : le
#: tableau bilan la compte en SURFACE (36 m2) la ou il compte les conteneurs en
#: NOMBRE. Le catalogue UNITe, arrive le 30/09/2026 avec le contrat de
#: Saint-Cyr IND07, dit « Zone de remise, 12 x 3 x 3m, longueur x largeur x
#: HAUTEUR ». Il porte dix-sept ouvrages et une seule ligne y est sans
#: hauteur — « Aire d'aspiration », `8 x 4 m` — donc la distinction est
#: deliberee et machine-lisible. C'est 12 x 3 m, soit l'empreinte d'un
#: conteneur 40 pieds, haut de 3 m.
MONTAGE = {
    "pdl": "poste",
    "local": "conteneur",
    "sdis": "citerne",
    "bess": "bess",
    "refroidissement": "citerne",
    "remise": "conteneur",
}

#: Part de l'aire du plus grand contour d'une couche de citernes au-dessous de
#: laquelle un contour n'est plus une citerne mais le sol qui la borde.
#:
#: La couche `UNI_BESS_Refroidissement` de Sarnois porte DEUX choses : la bache
#: de 108,9 m2 et, a cote d'elle sans la recouvrir, un rectangle de 8,00 x 4,00
#: — 32 m2, soit 29 % — que la version IND10b trace avec ses deux diagonales,
#: le symbole de surface que ce module note deja pour l'aire d'aspiration du
#: SDIS. Monte en bache, il donnait une seconde reserve de 120 m3 la ou le
#: bilan n'en compte qu'une.
#:
#: Le seuil laisse passer DEUX baches identiques — un site a deux BESS en aurait
#: deux — et ne coupe qu'entre 29 % et 100 %, ou il y a un facteur trois.
PART_CITERNE = 0.60

#: Tolerance, en metres, pour reconnaitre qu'une pointe de vantail est le bout
#: d'un segment de clôture.
TOL_PIVOT = 0.35

#: Largeurs plausibles d'un portail, en metres.
PORTAIL_MIN, PORTAIL_MAX = 2.0, 12.0

#: Marge, en metres, sous la plus etroite largeur cotee. Un plan dessine a
#: quelques centimetres pres ; a Saint-Cyr le poste ressort a 3,00 m pile pour
#: 3 m cotes, et les bandes ecartees font 1,50 et 1,00 m — le seuil coupe au
#: milieu d'un fosse d'un facteur deux.
TOL_LARGEUR = 0.30

#: Categories du plan qui sont des SURFACES DURES : elles se rendent telles
#: quelles, unies entre elles, et rien d'autre ne pose de grave.
SURFACES = ("piste", "plateforme", "voirie")

#: Surelevation des surfaces dures, en metres. Posees au ras du terrain, elles
#: disparaitraient dans le bruit du capteur d'ombre et leur bord ne se lirait
#: pas ; plus haut, elles feraient un ressaut que le plan ne porte pas.
EPAISSEUR_SURFACE = 0.04

#: Part du plus petit polygone qu'un plus grand doit recouvrir pour etre sa
#: plateforme plutot qu'un second ouvrage.
RECOUVREMENT_PLATEFORME = 0.80


def _sans_accents(t):
    for a, b in (("é", "e"), ("è", "e"), ("ê", "e"), ("à", "a"), ("ô", "o"),
                 ("û", "u"), ("î", "i"), ("ç", "c")):
        t = t.replace(a, b).replace(a.upper(), b.upper())
    return t


def anneau(pts, tol=1e-3):
    """Sommets d'un contour, sans le point de fermeture repete.

    ⚠️ `np.allclose` EST UN PIEGE EN LAMBERT 93. Sa tolerance est RELATIVE :
    rtol=1e-5 sur un nord de 6 750 000 vaut soixante-sept metres, et deux
    sommets distants de trois metres passent pour confondus. Ecrit ainsi, ce
    test retirait un sommet a chaque secteur de portail, qui n'en a que trois :
    plus aucun vantail n'etait reconnu, et le plan semblait n'avoir aucun
    portail. La comparaison se fait donc en metres, explicitement.
    """
    a = np.asarray([(float(x), float(y)) for x, y in pts], float)
    if len(a) > 1 and math.hypot(*(a[0] - a[-1])) < tol:
        a = a[:-1]
    return a


def rectangle_mini(pts):
    """Rectangle d'aire minimale contenant le contour : (centre, cap, L, l).

    Les ouvrages sont dessines en rectangles, mais rien ne garantit l'ordre des
    sommets ni qu'ils soient exactement a angle droit. On teste donc chaque
    direction d'arete — pour un convexe, l'optimum en est toujours une — et on
    garde celle qui donne la plus petite boite.

    Le cap est celui du GRAND cote, en degres depuis le nord, sens horaire :
    la meme convention que partout ailleurs dans le projet.
    """
    a = anneau(pts)
    if len(a) < 3:
        return None
    best = None
    for i in range(len(a)):
        d = a[(i + 1) % len(a)] - a[i]
        n = math.hypot(*d)
        if n < 1e-6:
            continue
        u = d / n
        v = np.array([-u[1], u[0]])
        pu, pv = a @ u, a @ v
        cote_u, cote_v = float(np.ptp(pu)), float(np.ptp(pv))
        aire = cote_u * cote_v
        if best is None or aire < best[0]:
            centre = (u * (pu.min() + pu.max()) / 2
                      + v * (pv.min() + pv.max()) / 2)
            best = (aire, centre, u, cote_u, cote_v)
    if best is None:
        return None
    _, centre, u, cu, cv = best
    if cu >= cv:
        L, l, axe = cu, cv, u
    else:
        L, l, axe = cv, cu, np.array([-u[1], u[0]])
    cap = math.degrees(math.atan2(axe[0], axe[1])) % 180.0
    return (float(centre[0]), float(centre[1])), cap, float(L), float(l)


def catalogue(parametres):
    """Les ouvrages cotes du contrat, lus en (nom, longueur, largeur, hauteur).

    C'est le catalogue UNITe, que `generateur-dp` fait voyager avec le contrat
    sous `cotes_normalisees` — dix-sept lignes sur celui de Saint-Cyr IND07.
    Il fait autorite sur les HAUTEURS, qu'un plan en vue de dessus ne porte
    jamais.

    ⚠️ `ordre_cotes` DONNE LE SENS DE CHAQUE NOMBRE, et il change d'une ligne a
    l'autre : « largeur x longueur x hauteur » pour le PTR, « longueur x
    largeur x hauteur » pour le PDL. C'est lui qui fait foi, jamais la position
    dans la chaine. Un poste de 12 x 3 dessine 3 x 12 se dessine parfaitement
    et ne se voit pas.

    ⚠️ UNE LIGNE SANS HAUTEUR EST UNE SURFACE, et c'est la seule facon
    machine-lisible de les distinguer. Sur les dix-sept lignes du catalogue,
    une seule n'en porte pas : « Aire d'aspiration », `8 x 4 m`,
    `ordre_cotes = "longueur x largeur"`. Toutes les autres en ont une — y
    compris la « Zone de remise » (12 x 3 x 3) et le « Bac de retention »
    (17,5 x 3 x 2,3), que j'avais pris pour des ouvrages de sol faute de cette
    source. La hauteur vaut alors None.
    """
    out = []
    for ligne in (parametres or {}).get("cotes_normalisees") or []:
        ordre = [m.strip() for m in
                 str(ligne.get("ordre_cotes", "")).lower().split("x")]
        nombres = [float(x.replace(",", "."))
                   for x in re.findall(r"\d+(?:[.,]\d+)?",
                                       str(ligne.get("dimensions", "")))]
        # « 1 conteneur 20 pieds 6 x 3 x 3m » : les cotes sont les DERNIERS
        # nombres, le compte et le calibre du conteneur les precedent.
        if len(nombres) > len(ordre):
            nombres = nombres[-len(ordre):]
        if len(ordre) != len(nombres) or not nombres:
            continue
        d = dict(zip(ordre, nombres))
        if "longueur" not in d or "largeur" not in d:
            continue
        out.append((str(ligne.get("ouvrage", "")), d["longueur"], d["largeur"],
                    d.get("hauteur")))
    return out


def largeur_mini(parametres):
    """Largeur du plus etroit ouvrage cote. En dessous, ce n'est pas un ouvrage.

    ⚠️ CE QUI REPARE LES TROIS POSTES EMPILES DE SAINT-CYR. La couche `UNI_PDL`
    y porte trois bandes ACCOLEES, de meme cap, larges de 3,00 / 1,50 / 1,00 m
    — un bloc de 12,00 x 5,50 m pose sur une plateforme de 131,4 m2, soit le
    `surface_plateforme_m2 = 132` que le catalogue donne au PDL/PTR. La
    nidification n'y peut rien : les trois bandes ne se recouvrent pas du tout.

    Une seule des trois, 12,00 x 3,00 = 36 m2, est un ouvrage du catalogue.
    Les deux autres ne peuvent en etre aucun : LA PLUS ETROITE LARGEUR DECLAREE
    EST 3 m. Le seuil ne se choisit donc pas, il se lit — et il vient avec le
    contrat, donc il suit le catalogue s'il change.
    """
    l = [lg for _n, _L, lg, h in catalogue(parametres) if h is not None]
    return min(l) if l else min(g["l"] for g in GABARITS.values() if "l" in g)


def _cotes(parametres, cle, gabarit, mesure=None):
    """Cotes d'un ouvrage : le plan d'abord, le catalogue ensuite, le gabarit enfin.

    `mesure` est le (L, l) releve sur le polygone du plan, quand il y en a un.
    La HAUTEUR ne s'y lit jamais — un plan est une vue de dessus — et vient
    donc toujours du catalogue ou du gabarit.

    ⚠️ LA HAUTEUR SE CHOISIT SUR L'EMPREINTE, PAS SUR LE NOM DE LA CATEGORIE.
    Le catalogue porte quatre citernes incendie — 30, 60, 120 et 240 m3, de
    7,95 x 4,44 x 1,3 a 10,4 x 18,5 x 1,6 m — et une citerne de
    refroidissement. Chercher « citerne » par sous-chaine prenait la premiere
    venue : a Saint-Cyr, ou le plan dessine 8,08 x 7,40 (la 60, haute de
    1,50 m), cela pouvait donner la 120, haute de 1,00 m. Le plan, lui, dit
    exactement laquelle c'est — par son empreinte.
    """
    h = gabarit.get("h", 3.0)
    cat = catalogue(parametres)

    if mesure is not None and cat:
        Lm, lm = sorted(mesure, reverse=True)
        best = None
        for nom, L, lg, hh in cat:
            if hh is None:                       # une surface n'a pas de volume
                continue
            a, b = sorted((L, lg), reverse=True)
            ecart = math.hypot(a - Lm, b - lm)
            if best is None or ecart < best[0]:
                best = (ecart, hh, nom)
        # Tolerance : un huitieme de la plus grande cote. Mesure a Saint-Cyr,
        # la bache colle a 0,03 m de la « Citerne incendie — 60 » quand la
        # deuxieme candidate est a 3,9 m.
        if best and best[0] <= max(Lm, 1.0) / 8.0:
            return dict(L=mesure[0], l=mesure[1], h=best[1])

    for nom, L, lg, hh in cat:
        n = nom.lower().replace("-", " ").replace("_", " ")
        if cle not in n or hh is None:
            continue
        h = hh
        if mesure is None:
            return dict(L=L, l=lg, h=h)
        break
    if mesure is not None:
        return dict(L=mesure[0], l=mesure[1], h=h)
    return dict(L=gabarit["L"], l=gabarit["l"], h=h)


def _pivots(scn):
    """Pointes de pivot des vantaux dessines sur les couches « portail ».

    Un vantail est un SECTEUR : deux rayons egaux et une corde. La pointe est
    donc le sommet dont les deux aretes voisines ont la meme longueur, ce qui
    reste vrai quel que soit l'angle de battement — contrairement a « le sommet
    oppose au plus grand cote », faux des qu'un vantail bat moins de 60 deg.
    """
    out = []
    for o in scn.lignes.get("portail", []):
        a = anneau(o["pts"])
        if len(a) < 3:
            continue
        cotes = np.hypot(*(np.roll(a, -1, axis=0) - a).T)
        ecart = [abs(cotes[i - 1] - cotes[i]) for i in range(len(a))]
        out.append(a[int(np.argmin(ecart))])
    return out


def _cordes(scn, tol=TOL_PIVOT):
    """Segments de la couche « portail » dont les DEUX bouts sont sur la clôture.

    ⚠️ QUAND LE PLAN DESSINE LE PORTAIL, IL FAUT LE LIRE PLUTOT QUE LE DEDUIRE.
    Un DXF de bureau d'etudes ne trace souvent que les VANTAUX — d'ou
    l'heuristique des pivots ci-dessous, ecrite pour Saint-Cyr. Mais un contrat
    reconstitue depuis un plan PDF ecrit le portail en CINQ entites, mesurees
    sur Gannay :

        1 segment de 6,99 m, ses deux bouts a 0,11 et 0,13 m de la cloture
        2 vantaux de 3,50 m, un bout sur la cloture, l'autre a 3,4 m
        2 arcs de battement de 5,49 m, en dix-sept points

    Le premier EST le portail : position, largeur et cap se lisent dessus.
    L'heuristique des pivots, elle, cherche un segment de CLOTURE de la bonne
    largeur — or l'enceinte de ce contrat n'a que quatre cotes de 170 a 190 m.
    Faute de le trouver, elle retombait sur l'ecartement des pivots et donnait
    **3,38 m pour un portail que le contrat declare a 7,00 m**, soit la moitie.
    """
    lignes = scn.lignes.get("cloture") or []
    if not lignes:
        return []
    from shapely.geometry import LineString, Point

    bords = [LineString(anneau(c["pts"])) for c in lignes
             if len(anneau(c["pts"])) >= 2]
    out = []
    for o in scn.lignes.get("portail", []):
        a = np.asarray(o["pts"], float)
        if len(a) != 2:
            continue
        L = math.hypot(*(a[1] - a[0]))
        if not (PORTAIL_MIN <= L <= PORTAIL_MAX):
            continue
        if all(any(b.distance(Point(*p)) <= tol for b in bords) for p in a):
            out.append((((a[0][0] + a[1][0]) / 2, (a[0][1] + a[1][1]) / 2),
                        math.degrees(math.atan2(a[1][0] - a[0][0],
                                                a[1][1] - a[0][1])), L))
    return out


def portails(scn, verbose=False):
    """Portails du plan : (centre, cap, largeur), lus sur la clôture.

    Le portail est d'abord le segment DESSINE dont les deux bouts touchent la
    clôture (voir `_cordes`). A defaut, c'est le segment de clôture dont les
    DEUX bouts sont des pointes de vantail ; a defaut encore, la paire de
    pivots elle-meme.
    """
    cordes = _cordes(scn)
    if cordes:
        if verbose:
            print(f"  portails : {len(cordes)} lu(s) au plan, en corde de "
                  f"cloture ({', '.join(f'{L:.2f} m' for _c, _a, L in cordes)})")
        return cordes

    piv = _pivots(scn)
    if not piv:
        return []
    pris, out = set(), []
    for c in scn.lignes.get("cloture", []):
        pts = np.asarray([(float(x), float(y)) for x, y in c["pts"]], float)
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            L = math.hypot(*(b - a))
            if not (PORTAIL_MIN <= L <= PORTAIL_MAX):
                continue
            ia = [k for k, p in enumerate(piv) if math.hypot(*(p - a)) < TOL_PIVOT]
            ib = [k for k, p in enumerate(piv) if math.hypot(*(p - b)) < TOL_PIVOT]
            if ia and ib:
                pris.update(ia + ib)
                out.append((((a[0] + b[0]) / 2, (a[1] + b[1]) / 2),
                            math.degrees(math.atan2(b[0] - a[0], b[1] - a[1])),
                            L))
    # Pivots orphelins : on les apparie deux a deux, du plus proche au plus
    # loin, tant que l'ecartement reste celui d'un portail.
    reste = [p for k, p in enumerate(piv) if k not in pris]
    while len(reste) >= 2:
        d = sorted((math.hypot(*(reste[0] - q)), j)
                   for j, q in enumerate(reste[1:], 1))
        if not (PORTAIL_MIN <= d[0][0] <= PORTAIL_MAX):
            reste.pop(0)
            continue
        a, b = reste[0], reste[d[0][1]]
        out.append((((a[0] + b[0]) / 2, (a[1] + b[1]) / 2),
                    math.degrees(math.atan2(b[0] - a[0], b[1] - a[1])),
                    float(d[0][0])))
        reste = [q for j, q in enumerate(reste) if j not in (0, d[0][1])]
    if verbose:
        print(f"  portails : {len(out)} pour {len(piv)} vantaux dessines")
    return out


def _cap_cloture(scn, E, N, defaut=0.0):
    """Cap du brin de clôture le plus proche d'un point, en degrés.

    Ne sert plus que de secours : un ouvrage dont le plan ne donne qu'un point,
    ou dont le polygone est trop degenere pour porter une orientation.
    """
    meilleur, dmin = defaut, math.inf
    for c in scn.lignes.get("cloture", []):
        pts = np.asarray([(float(a), float(b)) for a, b in c["pts"]], float)
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            m = (a + b) / 2.0
            d = math.hypot(m[0] - E, m[1] - N)
            if d < dmin:
                dmin = d
                meilleur = math.degrees(math.atan2(b[0] - a[0], b[1] - a[1]))
    return meilleur


def englobants(scn):
    """Polygones de VOLUME qui en contiennent un autre : ce sont des plateformes.

    ⚠️ UN PLAN DESSINE SOUVENT DEUX FOIS LE MEME OUVRAGE — son emprise batie et
    la plateforme qui la porte — sur deux couches voisines. Sarnois IND10b en
    donne le cas net : `UNI_PDL` fait 12,0 x 3,0 m, soit le gabarit UNITe au
    centimetre, et `VAL-PDL` fait 15,3 x 6,3 m au MEME cap et a la MEME
    distance, en le contenant ENTIEREMENT. Monter les deux donnait deux postes
    empiles, dont le plus gros debordait a 65 % hors de l'enceinte — ce que le
    controle de conformite a signale.

    La nidification tranche sans avoir a deviner d'apres le nom de la couche :
    un batiment n'en contient pas un autre, une plateforme si.

    Rend la liste des contours a traiter comme surface dure.
    """
    from shapely.geometry import Polygon

    cands = []
    for cat in MONTAGE:
        for o in scn.lignes.get(cat, []):
            a = anneau(o["pts"])
            if len(a) < 3:
                continue
            p = Polygon(a).buffer(0)
            if p.is_valid and p.area > 1.0:
                cands.append((p, o))
    dehors = []
    for p, o in cands:
        for q, _ in cands:
            if q is p or q.area >= p.area:
                continue
            # RECOUVRIR N'EST PAS CONTENIR, et il faut la version faible. Un
            # bloc dessine souvent l'ouvrage en plusieurs contours qui se
            # debordent un peu : celui du PTR de Sarnois en donne quatre, au
            # meme cap, dont un de 10,0 x 3,0 m — le gabarit PTR exact — et un
            # de 13,3 x 3,2 qui le couvre entierement sans le contenir au sens
            # strict. La regle stricte laissait deux transformateurs.
            if p.intersection(q).area >= RECOUVREMENT_PLATEFORME * q.area:
                dehors.append(o)
                break
    return dehors


def aires_de_citerne(scn, cat="refroidissement", part=PART_CITERNE):
    """Contours d'une couche de citernes qui sont du SOL, pas une reserve.

    Voir `PART_CITERNE` : la couche porte la bache ET l'aire qui la borde, sans
    que le nom de la couche ni la nidification ne les separent — les deux
    contours ne se recouvrent pas du tout.
    """
    from shapely.geometry import Polygon

    cands = []
    for o in scn.lignes.get(cat, []):
        a = anneau(o["pts"])
        if len(a) < 3:
            continue
        p = Polygon(a).buffer(0)
        if p.is_valid and p.area > 1.0:
            cands.append((p.area, o))
    if not cands:
        return []
    plafond = max(a for a, _ in cands)
    return [o for a, o in cands if a < part * plafond]


def _polygones_durs(scn, E0, N0, dmax):
    """Polygones des surfaces dures A CREER, dans la portee."""
    from shapely.geometry import Polygon

    out = []
    for o in englobants(scn) + aires_de_citerne(scn):
        a = anneau(o["pts"])
        c = a.mean(axis=0)
        if math.hypot(c[0] - E0, c[1] - N0) <= dmax:
            p = Polygon(a).buffer(0)
            if p.is_valid and p.area > 0.5:
                out.append(p)
    cats = list(SURFACES) + ["sdis"]
    for cat in cats:
        for o in scn.lignes.get(cat, []):
            couche = _sans_accents(str(o.get("couche", ""))).lower()
            # CE QUI EXISTE DEJA EST DANS LA PHOTO. Redessiner une piste
            # existante, c'est poser une dalle grise sur la vraie, qui n'aura
            # ni sa teinte ni son grain. Sur Saint-Cyr, `Piste_lourde_existante`
            # pesait 652 des 684 m2 de l'union : l'essentiel de la grave
            # rendue ne montrait donc rien de nouveau.
            if "existant" in couche:
                continue
            # Sur la couche SDIS, seule l'aire d'aspiration est une surface ;
            # la bache est un volume, et ses deux diagonales sont un symbole.
            if cat == "sdis" and not ("aspiration" in couche or "aire" in couche):
                continue
            a = anneau(o["pts"])
            if len(a) < 3:
                continue
            c = a.mean(axis=0)
            if math.hypot(c[0] - E0, c[1] - N0) > dmax:
                continue
            p = Polygon(a).buffer(0)
            if p.is_valid and p.area > 0.5:
                out.append(p)
    return out


def surfaces(scn, sol_abs, E0, N0, dmax=400.0, verbose=True):
    """Les surfaces dures du plan, UNIES puis maillees. Rend un bloc, ou None.

    L'UNION N'EST PAS UNE COQUETTERIE. Sur Saint-Cyr, les sept polygones durs a
    moins de 60 m totalisent 1 040 m2 pour une union de 684 : 356 m2 se
    recouvrent, pistes et plateformes se chevauchant comme il est d'usage sur
    un plan. Maillees separement, elles donnent deux nappes coplanaires a la
    meme altitude, qui clignotent l'une sur l'autre au rendu.
    """
    from shapely.ops import triangulate as _trianguler
    from shapely.ops import unary_union

    parts = _polygones_durs(scn, E0, N0, dmax)
    if not parts:
        return None
    u = unary_union(parts)
    bloc = {"v": [], "f": []}
    for tri in _trianguler(u):
        # `triangulate` travaille sur l'enveloppe convexe : les triangles qui
        # sortent de l'union sont ecartes, sinon la grave deborde.
        if not u.contains(tri.centroid):
            continue
        n0 = len(bloc["v"])
        for x, y in list(tri.exterior.coords)[:3]:
            bloc["v"].append([float(x), float(y),
                              sol_abs(x, y) + EPAISSEUR_SURFACE])
        bloc["f"].append([n0, n0 + 1, n0 + 2])
    if verbose:
        brut = sum(p.area for p in parts)
        print(f"  surfaces dures : {len(parts)} polygones du plan, "
              f"{brut:.0f} m2 bruts -> {u.area:.0f} m2 unis, "
              f"{len(bloc['f'])} triangles")
    return bloc if bloc["f"] else None


def ouvrages(scn, sol_abs, E0, N0, parametres=None, dmax=400.0, verbose=True):
    """Monte les ouvrages techniques du plan.

    Rend `(blocs, ouvertures, registre)` : les blocs par materiau, la liste
    des (est, nord, rayon) ou la clôture doit s'ouvrir pour laisser place aux
    portails, et le registre de ce qui a ete monte — trace du plan et emprise
    posee — que `conformite` confronte.
    """
    import exporter_equipements as EE

    blocs, ouvertures, compte, ecartes = {}, [], {}, []
    # REGISTRE DE CE QUI EST MONTE, pour que `conformite` puisse confronter le
    # modele au plan sans le deviner. Chaque entree donne le trace du plan et
    # l'emprise reellement posee : une cote inventee ou une orientation prise
    # ailleurs s'y voit tout de suite.
    registre = []

    dur = surfaces(scn, sol_abs, E0, N0, dmax=dmax, verbose=verbose)
    if dur:
        blocs["grave"] = dur

    def fusion(cle, part):
        if part is None or not part.get("f"):
            return
        cible = blocs.setdefault(cle, {"v": [], "f": []})
        n0 = len(cible["v"])
        cible["v"] += part["v"]
        cible["f"] += [[i + n0 for i in f] for f in part["f"]]
        if "uv" in part:
            cible.setdefault("uv", [])
            cible["uv"] += part["uv"]

    # --- portails : lus sur la clôture, qui s'ouvre d'autant ---------------
    for (E, N), ang, L in portails(scn):
        if math.hypot(E - E0, N - N0) > dmax:
            continue
        cadre, barreaux = EE.geometrie_portail((E, N), ang, sol_abs(E, N), L=L,
                                               h=GABARITS["portail"]["h"])
        fusion("menuiserie", cadre)
        fusion("menuiserie", barreaux)
        # Le rayon couvre le segment entier, montants compris : un grillage qui
        # reparaitrait sur les derniers centimetres se verrait autant qu'un
        # grillage entier.
        ouvertures.append((E, N, L / 2 + 0.6))
        compte["portail"] = compte.get("portail", 0) + 1

    # --- poste, conteneur, citerne, aire d'aspiration -----------------------
    sauter = {id(o) for o in englobants(scn) + aires_de_citerne(scn)}
    for cat, quoi in MONTAGE.items():
        for obj in scn.lignes.get(cat, []):
            if id(obj) in sauter:
                continue
            # ⚠️ UN SEGMENT N'EST PAS UN OUVRAGE. La couche
            # `UNI_BESS_Refroidissement` de Sarnois IND10b porte deux
            # polylignes de DEUX points, longues de 8,944 m — soit exactement
            # hypot(8,00 ; 4,00), les diagonales du rectangle voisin. Sans
            # contour, `rectangle_mini` rend None, on retombait sur le gabarit,
            # et chaque diagonale devenait une reserve souple de 120 m3 : trois
            # baches la ou le bilan en compte une.
            a = anneau(obj["pts"])
            if len(a) < 3:
                continue
            E, N = float(a[:, 0].mean()), float(a[:, 1].mean())
            if math.hypot(E - E0, N - N0) > dmax:
                continue
            couche = str(obj.get("couche", "")).lower()
            rect = rectangle_mini(obj["pts"])
            if rect is not None:
                (E, N), ang, Lm, lm = rect
                mesure = (Lm, lm)
                # ⚠️ PLUS ETROIT QUE LE PLUS ETROIT DES OUVRAGES COTES : ce
                # n'est pas un ouvrage. Voir `largeur_mini` — trois bandes
                # accolees sur `UNI_PDL` a Saint-Cyr, 3,00 / 1,50 / 1,00 m,
                # montees en trois postes empiles de 3 m de haut.
                if min(Lm, lm) < largeur_mini(parametres) - TOL_LARGEUR:
                    ecartes.append((couche, Lm, lm))
                    continue
            else:
                ang, mesure = _cap_cloture(scn, E, N), None
            z = sol_abs(E, N)

            def _pose(nom, LL, ll):
                t = math.radians(ang)
                ux, uy = math.sin(t), math.cos(t)
                registre.append({
                    "nom": nom, "couche": obj.get("couche", ""),
                    "plan": [(float(x), float(y)) for x, y in a],
                    "monte": [(E + ux * (LL / 2) * sx - uy * (ll / 2) * sy,
                               N + uy * (LL / 2) * sx + ux * (ll / 2) * sy)
                              for sx, sy in ((1, 1), (1, -1), (-1, -1), (-1, 1))]})

            if quoi == "poste":
                cle = "pdl" if "pdl" in couche else "ptr"
                g = _cotes(parametres, cle, GABARITS[cle], mesure)
                geo = {"p": dict(centre=(E, N), angle=ang, L=g["L"], l=g["l"])}
                # LE TABLIER DE GRAVE EST ECARTE : il vaut 94,5 m2 pour un
                # poste de 36, il n'est sur aucun trace du plan, et les trois
                # postes etant a un metre l'un de l'autre, leurs tabliers se
                # recouvraient. Le sol dur vient de `surfaces()`, et les trois
                # postes y reposent a 100 %.
                for cible, part in zip(
                        ("beton", None, "couvertine", "acier", "creux"),
                        EE.geometrie_poste(geo, z, (E0, N0), cle="p")):
                    if cible:
                        fusion(cible, part)
                compte["pdl"] = compte.get("pdl", 0) + 1
                _pose("poste", g["L"], g["l"])

            elif quoi == "conteneur":
                g = _cotes(parametres, "local", GABARITS["local"], mesure)
                for cible, part in zip(
                        ("tole", "menuiserie", "coin", "creux"),
                        EE.geometrie_conteneur((E, N), ang, z, g["L"], g["l"],
                                               g["h"], bess=False,
                                               oeil=(E0, N0))):
                    fusion(cible, part)
                compte["local"] = compte.get("local", 0) + 1
                _pose("conteneur", g["L"], g["l"])

            elif quoi == "bess":
                # `bess=True` ajoute la grille de ventilation en pignon, qui
                # est ce qui distingue a l'oeil un conteneur batterie d'un
                # local de stockage — meme gabarit, meme bardage.
                g = _cotes(parametres, "bess", GABARITS["bess"], mesure)
                for cible, part in zip(
                        ("tole", "menuiserie", "coin", "creux"),
                        EE.geometrie_conteneur((E, N), ang, z, g["L"], g["l"],
                                               g["h"], bess=True,
                                               oeil=(E0, N0))):
                    fusion(cible, part)
                compte["bess"] = compte.get("bess", 0) + 1
                _pose("conteneur BESS", g["L"], g["l"])

            elif quoi == "citerne":
                # LA COUCHE TRANCHE : une aire d'aspiration est une surface
                # dure, une bache incendie est un volume souple. Les deux
                # arrivent sur la meme categorie « sdis » du plan. L'aire est
                # montee par `surfaces()`, avec les autres surfaces du plan.
                if "aspiration" in couche or "aire" in couche:
                    continue
                g = _cotes(parametres, "citerne", GABARITS["citerne"], mesure)
                geo = {"c": dict(centre=(E, N), angle=ang, L=g["L"], l=g["l"])}
                # LA PLATEFORME DE LA CITERNE EST ECARTEE : le plan n'en
                # dessine pas, et l'emprise de la bache ne repose qu'a 6 % sur
                # les surfaces dures — elle est posee sur l'herbe.
                pvc, _plat = EE.geometrie_citerne(geo, z, cote=(g["L"], g["l"]),
                                                  haut=g["h"], cle="c")
                fusion("pvc", pvc)
                quelle = ("bache de refroidissement"
                          if cat == "refroidissement" else "sdis/bache")
                compte[quelle] = compte.get(quelle, 0) + 1
                _pose("citerne", g["L"], g["l"])

    if verbose:
        detail = ", ".join(f"{n} {c}" for c, n in sorted(compte.items()))
        print(f"  ouvrages techniques : {detail or 'aucun dans la portee'}")
        # ON NE JETTE JAMAIS EN SILENCE : un contour ecarte a tort ne se voit
        # pas sur un rendu, c'est juste un ouvrage qui manque.
        for couche, L, l in ecartes:
            print(f"    ecarte : {couche or '(sans couche)'} {L:.2f} x {l:.2f} m"
                  f" — plus etroit que le plus etroit ouvrage cote "
                  f"({largeur_mini(parametres):.2f} m)")
    return ({k: v for k, v in blocs.items() if v["f"]}, ouvertures,
            registre)
