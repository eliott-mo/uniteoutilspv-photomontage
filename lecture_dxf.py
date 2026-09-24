#!/usr/bin/env python3
"""Lecture generique d'un plan BE PVcase : tables, cloture, pistes, zones.

Gere les deux structures rencontrees :
  - Sarnois   : les tables sont des INSERT de blocs PVCase. Les coordonnees
                brutes `e.dxf.insert` sont en OCS et absurdes ; il faut passer
                par virtual_entities() qui resout en WCS.
  - Saint-Cyr : les tables sont des POLYLINE 3D directement dans le modelspace.

Dans les deux cas une table est une POLYLINE 3D a 4 sommets, dans l'ordre
haut, haut, bas, bas.
"""
import math
import re
from dataclasses import dataclass, field

import ezdxf
import numpy as np

MOTIF_TABLES = "PV Modules"          # sous-chaine commune aux couches PVcase
MOTIF_OPTIMISED = "optimised"
LAYER_TOPO = "-TopoNiveau"
MOTIFS_LIGNES = {
    "cloture": ("cloture", "clôture"),
    "piste": ("piste",),
    "plateforme": ("plateforme",),
    "voirie": ("voirie",),
    "haie": ("haie",),
    "pdl": ("pdl", "pdt", "ptr"),
    "local": ("local",),
    "sdis": ("sdis",),
    "portail": ("portail",),
    # ⚠️ LE MOTIF N'EST PAS « BESS », ET CE N'EST PAS UN DETAIL. Un plan
    # PVcase porte `PVcase AC Cables (AC BESS - Transformer)` et cinq autres
    # couches de cables du meme genre : un motif « bess » nu les attraperait
    # toutes et monterait des conteneurs sur des tirees de cable. Les motifs
    # portent donc sur l'OUVRAGE — batterie, refroidissement, remise — et
    # jamais sur le lot.
    #
    # `UNI_BESS_PTR` tombe volontairement dans « pdl » avant d'arriver ici :
    # le PTR associe au BESS est un poste, et le bilan le compte comme tel
    # (« Nombre de PTR associes | 1 »).
    #
    # ⚠️ `UNI_BESS_Retention` n'est mappe par rien, et c'est voulu. Son MTEXT
    # dit « Bac de retention 120m3 » : c'est un CREUX dans le sol. Le rendre
    # en dalle de grave surelevee de 4 cm serait un ressaut que le plan ne
    # porte pas ; ne rien rendre est le seul choix honnete tant qu'on n'a pas
    # sa profondeur.
    "bess": ("bess_batterie", "bess batterie", "batterie"),
    "refroidissement": ("refroidissement",),
    "remise": ("remise",),
}


#: Categories qui sont des VOLUMES. Une couche de VRD n'en est jamais une.
VOLUMES = ("pdl", "local", "sdis", "portail", "bess", "refroidissement")


def _categorie(couche):
    """Categorie d'une couche, ou None.

    ⚠️ UNE COUCHE VRD N'EST JAMAIS UN VOLUME. « VRD » veut dire voirie et
    reseaux divers : par definition des travaux de sol. Le motif « stockage »
    attrapait `UNI_VRD_Stockage_Logistique` de Sarnois — une aire de 962 m2 —
    et le montage en faisait un conteneur de 39 x 27 m. Le motif est resserre
    sur « local », et la regle VRD garde le reste.
    """
    lay = _sans_accents(couche).lower()
    for cat, motifs in MOTIFS_LIGNES.items():
        if cat in VOLUMES and "vrd" in lay:
            continue
        if any(_sans_accents(m).lower() in lay for m in motifs):
            return cat
    return None


#: Blocs dont la geometrie ne doit pas etre montee, et pourquoi.
#:
#: Un bloc porte souvent le DETAIL d'un ouvrage : sa cuve, son bac, ses cotes.
#: Sur Sarnois IND10b, `CIT_RIGID_120m3 Bac de retention` est pose sur la
#: couche `UNI_SDIS_Bache_incendie` et donnait un rectangle de 16,9 x 3,0 m
#: monte comme une bache souple. Un bac de retention est un ouvrage de sol, pas
#: une reserve d'eau.
BLOCS_ECARTES = {
    "retention": "bac de retention : ouvrage de sol, pas une reserve",
    "bac de": "bac : ouvrage de sol, pas un volume",
}


def _bloc_ecarte(nom):
    """Dit si un bloc est ecarte, d'apres son nom."""
    n = _sans_accents(str(nom or "")).lower()
    return any(m in n for m in BLOCS_ECARTES)


#: Fleche maximale, en metres, quand on aplatit une spline en polyligne.
FLECHE_SPLINE = 0.10


def _sommets_spline(e):
    """Sommets d'une spline, aplatie en polyligne. Liste vide si on ne sait pas.

    ⚠️ UNE CITERNE SOUPLE SE DESSINE EN SPLINE, parce qu'elle a physiquement
    des coins arrondis. C'est le cas des deux plans qui portent un BESS :
    `UNI_BESS_Refroidissement` n'y porte AUCUN contour droit exploitable — a
    Auzainvilliers une seule spline et une hachure a bords splines, a Sarnois
    huit splines dans un bloc. Sans cette lecture, la citerne de 120 m3 est
    purement absente du montage, et rien ne le signale.

    Mesure : aplaties, elles donnent 11,70 x 9,32 m sur les DEUX plans, soit le
    gabarit UNITe (11,7 x 8,9, 104 m2 au bilan) au centimetre sur la longueur.

    C'est aussi le seul endroit du corpus ou une spline tombe sur une couche
    mappee : la lire ne change rien ailleurs.
    """
    try:
        from ezdxf import path as _chemin
        return [(float(v.x), float(v.y))
                for v in _chemin.make_path(e).flattening(FLECHE_SPLINE)]
    except Exception:                                         # noqa: BLE001
        return []


def _chainer(morceaux, tol=1e-3):
    """Joint des troncons qui partagent leurs bouts. Rend des contours.

    Une citerne souple n'est pas dessinee d'un trait : le bloc
    `UNI_Refroidissement` de Sarnois la decoupe en huit splines — quatre cotes
    droits et quatre coins arrondis — qui se suivent bout a bout et bouclent.
    Prises separement, elles donnent huit contours degeneres d'aire nulle ;
    chainees, le contour ferme de 11,70 x 9,32 m.

    A Auzainvilliers la meme citerne tient en UNE spline fermee. Le chainage
    traite les deux cas sans avoir a les distinguer.
    """
    restants = [list(m) for m in morceaux if len(m) >= 2]
    contours = []
    while restants:
        c = restants.pop(0)
        colle = True
        while colle:
            colle = False
            for i, m in enumerate(restants):
                for bout, suite in ((m[0], m), (m[-1], m[::-1])):
                    if math.dist(c[-1], bout) <= tol:
                        c += suite[1:]
                        restants.pop(i)
                        colle = True
                        break
                if colle:
                    break
        contours.append(c)
    return contours


#: Nombre de contours au-dela duquel un bloc est un DESSIN DE PRODUIT et non
#: un symbole de plan. Mesure sur les sept plans du corpus : le plus charge des
#: symboles dessines par un bureau d'etudes en porte 10 (`UNI_PDT`), le dessin
#: de produit `BESS Skyray` en porte 77. Le seuil tient au milieu du fosse,
#: avec un facteur 2 d'un cote et 4 de l'autre.
DETAIL_BLOC = 20


def _contour_produit(polys):
    """Ne garde que l'enveloppe d'un bloc quand c'est un dessin de produit.

    ⚠️ UN BLOC DE FABRICANT DESSINE L'OUVRAGE ET SES ENTRAILLES. `BESS Skyray`
    porte 77 contours : le conteneur de 6,06 x 3,00 m — 18,2 m2, soit le
    « conteneur 20 pieds (6x3x3m) » du tableau bilan au centimetre — mais
    aussi sa paroi interieure, trente-six racks de 2,32 x 0,12 m et leur
    boulonnerie de 5 cm. Montes, cela fait trente-huit conteneurs empiles dans
    un seul.

    La regle de nidification habituelle (`englobants`) ne sait pas trancher
    ici : elle tient le contour englobant pour une plateforme, ce qui est vrai
    d'une dalle autour d'un poste et faux d'une paroi autour d'un rack. Elle
    garderait donc les racks et jetterait le conteneur.

    On tranche donc en amont, sur ce qui separe VRAIMENT les deux cas : un
    symbole de plan tient en quelques contours, un dessin de produit en porte
    des dizaines.
    """
    if len(polys) <= DETAIL_BLOC:
        return polys
    from shapely.geometry import Polygon

    def aire(p):
        g = Polygon(p[0]).buffer(0)
        return g.area if g.is_valid else 0.0

    return [max(polys, key=aire)]


def _filles(ins, profondeur=3, nom=None):
    """Geometrie d'un bloc, EN DESCENDANT dans les blocs imbriques.

    ⚠️ `virtual_entities` ne descend QUE D'UN NIVEAU, et l'essentiel est
    parfois un cran plus bas. Sur Sarnois IND10b, `UNI_BESS_Batterie` est un
    INSERT du bloc `UNI_Batterie`, qui porte l'enveloppe de 8,06 x 6,00 m et,
    imbrique dedans, le bloc `BESS Skyray` ou se trouve le conteneur reel de
    6,1 x 3,0 m. Sans descendre, on monte l'enveloppe : un conteneur 61 % trop
    grand, et rien ne le signale.

    Sur Auzainvilliers le meme `BESS Skyray` est pose directement au
    modelspace : les deux plans se lisent alors pareil, et `englobants` fait
    son travail des deux cotes — l'enveloppe devient la dalle, le bloc devient
    le volume.

    Mesure avant d'y toucher : sur les sept plans du corpus, AUCUN INSERT
    imbrique ne tombe sur une couche mappee aujourd'hui. La descente est donc
    inerte partout, sauf la ou elle est necessaire.

    Rend des couples (nom du bloc qui dessine l'entite, entite).
    """
    nom = nom if nom is not None else str(ins.dxf.name)
    try:
        filles = list(ins.virtual_entities())
    except Exception:                                         # noqa: BLE001
        return []
    out = []
    for ve in filles:
        if ve.dxftype() != "INSERT":
            out.append((nom, ve))
        elif profondeur > 0 and not _bloc_ecarte(ve.dxf.name):
            out += _filles(ve, profondeur - 1, str(ve.dxf.name))
    return out


def _sommets_hatch(chemin):
    """Sommets d'un contour de hachure, polyligne ou suite d'aretes."""
    if hasattr(chemin, "vertices"):
        return [(float(v[0]), float(v[1])) for v in chemin.vertices]
    pts = []
    for a in getattr(chemin, "edges", ()):
        if hasattr(a, "start"):
            pts.append((float(a.start[0]), float(a.start[1])))
    return pts


def _sans_accents(s):
    for a, b in (("é", "e"), ("è", "e"), ("ê", "e"), ("à", "a"), ("ô", "o"), ("û", "u"), ("î", "i"), ("ç", "c")):
        s = s.replace(a, b).replace(a.upper(), b.upper())
    return s


@dataclass
class Table:
    q: list                    # 4 sommets (x, y, z) : haut, haut, bas, bas
    rows: int = 2
    cols: int = 26

    @property
    def largeur_pente(self):
        a, b = np.array(self.q[0]), np.array(self.q[3])
        return float(np.linalg.norm(a - b))

    @property
    def denivele(self):
        return float(self.q[0][2] - self.q[3][2])

    @property
    def inclinaison(self):
        return math.degrees(math.asin(max(-1.0, min(1.0, self.denivele / self.largeur_pente))))


@dataclass
class Scene:
    tables: list = field(default_factory=list)
    lignes: dict = field(default_factory=dict)      # categorie -> liste de polylignes 2D/3D
    topo: np.ndarray = None                          # (n, 3) ou None
    source: str = ""

    def bbox(self):
        pts = np.array([p for t in self.tables for p in t.q])
        return (pts[:, 0].min(), pts[:, 1].min(), pts[:, 0].max(), pts[:, 1].max())

    def centre(self):
        pts = np.array([p for t in self.tables for p in t.q])
        return pts.mean(axis=0)

    def azimut_modules(self):
        q = np.array([t.q for t in self.tables])
        n = np.cross(q[:, 3] - q[:, 0], q[:, 1] - q[:, 0])
        n[n[:, 2] < 0] *= -1
        az = (np.degrees(np.arctan2(n[:, 0], n[:, 1])) + 360) % 360
        return float(az.mean()), float(az.std())

    def resume(self):
        q = np.array([t.q for t in self.tables])
        largeurs = np.array([t.largeur_pente for t in self.tables])
        incl = np.array([t.inclinaison for t in self.tables])
        az, azs = self.azimut_modules()
        lignes = ", ".join(f"{k}:{len(v)}" for k, v in sorted(self.lignes.items()) if v)
        return (f"{len(self.tables)} tables | largeur {largeurs.mean():.3f} m | "
                f"inclinaison {incl.mean():.1f} deg | azimut modules {az:.1f} deg (ecart {azs:.1f})\n"
                f"  X [{q[:, :, 0].min():.0f}, {q[:, :, 0].max():.0f}]  "
                f"Y [{q[:, :, 1].min():.0f}, {q[:, :, 1].max():.0f}]  "
                f"Z [{q[:, :, 2].min():.2f}, {q[:, :, 2].max():.2f}]\n"
                f"  lignes : {lignes or 'aucune'} | topo DXF : "
                f"{len(self.topo) if self.topo is not None else 0} points")


def _quad_depuis_polyline(e):
    if e.dxftype() != "POLYLINE" or not e.is_3d_polyline:
        return None
    pts = [tuple(v.dxf.location) for v in e.vertices]
    return pts if len(pts) == 4 else None


def _quads_depuis_lignes(msp, tol=3):
    """Tables dessinees en QUATRE SEGMENTS, et non en polyligne ni en bloc.

    Troisieme structure rencontree, apres les blocs INSERT de Sarnois et les
    POLYLINE 3D de Saint-Cyr : les plans du BE sortis de PVcase en mode
    « optimised » ecrivent chaque table en quatre LINE independantes. Elles
    portent bien le Z — l'inclinaison y ressort a 15,0 degres exactement — mais
    aucune entite ne les relie : c'est la CONNEXITE DES EXTREMITES qui fait la
    table.

    Mesure : 524 segments donnent 131 quadrilateres fermes a Bedarieux, 316 en
    donnent 79 a Auzainvilliers. Tous a quatre segments et quatre sommets, sans
    exception — un plan de tables n'a pas de raison d'etre irregulier, et une
    composante qui ne ferait pas un quadrilatere signalerait autre chose sur la
    meme couche.
    """
    segs = []
    for e in msp.query("LINE"):
        if MOTIF_TABLES not in e.dxf.layer:
            continue
        a = tuple(round(float(v), tol) for v in e.dxf.start)
        b = tuple(round(float(v), tol) for v in e.dxf.end)
        if a != b:
            segs.append((a, b))
    if not segs:
        return []

    voisins = {}
    for i, (a, b) in enumerate(segs):
        voisins.setdefault(a, []).append(i)
        voisins.setdefault(b, []).append(i)

    vu, quads = set(), []
    for depart in range(len(segs)):
        if depart in vu:
            continue
        pile, comp = [depart], []
        while pile:
            j = pile.pop()
            if j in vu:
                continue
            vu.add(j)
            comp.append(j)
            for p in segs[j]:
                pile += [k for k in voisins[p] if k not in vu]
        sommets = {p for j in comp for p in segs[j]}
        if len(comp) != 4 or len(sommets) != 4:
            continue
        # Parcours du cycle : on suit les aretes de sommet en sommet.
        adj = {}
        for j in comp:
            a, b = segs[j]
            adj.setdefault(a, []).append(b)
            adj.setdefault(b, []).append(a)
        ordre = [next(iter(sommets))]
        while len(ordre) < 4:
            suite = [p for p in adj[ordre[-1]] if p not in ordre]
            if not suite:
                break
            ordre.append(suite[0])
        if len(ordre) != 4:
            continue
        quads.append(_ordonner_quad(ordre))
    return quads


def _ordonner_quad(pts):
    """Tourne un cycle de 4 sommets pour mettre les deux plus HAUTS devant.

    `Table` attend l'ordre haut, haut, bas, bas, et la rotation preserve
    l'adjacence — contrairement a un tri par altitude, qui croiserait le quad.
    """
    z = [p[2] for p in pts]
    for d in range(4):
        r = [pts[(d + k) % 4] for k in range(4)]
        if min(r[0][2], r[1][2]) > max(r[2][2], r[3][2]) - 1e-6:
            return r
    # A plat ou en biais : on rend le cycle tel quel, `lire` levera.
    return list(pts)


def _rows_cols(nom):
    m = re.match(r"(\d+)P(\d+)", nom or "")
    return (int(m.group(1)), int(m.group(2))) if m else (2, 26)


def lire(chemin):
    """Lit un DXF et renvoie une Scene. Detecte automatiquement la structure."""
    doc = ezdxf.readfile(chemin)
    msp = doc.modelspace()
    tables = []

    # structure 1 : blocs INSERT (Sarnois)
    for ins in msp.query("INSERT"):
        if MOTIF_TABLES not in ins.dxf.layer:
            continue
        for ve in ins.virtual_entities():
            q = _quad_depuis_polyline(ve)
            if q:
                r, c = _rows_cols(ins.dxf.name)
                tables.append(Table(q=q, rows=r, cols=c))
                break

    # structure 2 : POLYLINE 3D directes dans le modelspace (Saint-Cyr)
    if not tables:
        for e in msp.query("POLYLINE"):
            if MOTIF_TABLES not in e.dxf.layer:
                continue
            q = _quad_depuis_polyline(e)
            if q:
                tables.append(Table(q=q))
    # structure 3 : quatre LINE par table (PVcase « optimised », plans du BE)
    if not tables:
        for q in _quads_depuis_lignes(msp):
            tables.append(Table(q=q))
    if not tables:
        raise RuntimeError(f"aucune table trouvee (couches contenant {MOTIF_TABLES!r})")

    # ordre des sommets : les deux premiers doivent etre les plus hauts
    for t in tables:
        z = [p[2] for p in t.q]
        if not (min(z[:2]) > max(z[2:]) - 1e-6):
            raise RuntimeError("ordre des sommets inattendu : haut, haut, bas, bas attendu")

    topo = np.array([tuple(e.dxf.insert) for e in msp.query("INSERT")
                     if e.dxf.layer == LAYER_TOPO], dtype=float)
    topo = topo if len(topo) else None

    lignes = {k: [] for k in MOTIFS_LIGNES}
    for e in msp.query("LWPOLYLINE"):
        cat = _categorie(e.dxf.layer)
        if cat:
            pts = [(float(x), float(y)) for x, y in e.get_points("xy")]
            lignes[cat].append({"pts": pts, "fermee": bool(e.closed),
                                "couche": e.dxf.layer})

    for e in msp.query("SPLINE"):
        cat = _categorie(e.dxf.layer)
        pts = _sommets_spline(e) if cat else []
        if len(pts) >= 3:
            lignes[cat].append({"pts": pts, "fermee": True,
                                "couche": e.dxf.layer, "forme": "spline"})

    # LES HATCH COMPTENT, MAIS SEULEMENT LA OU ILS SONT LE SEUL TRACE. A
    # Saint-Cyr, la couche `UNI_portail` ne porte aucune polyligne : six HATCH,
    # neuf LINE et six ARC. Ne lire que les polylignes revenait a dire qu'il
    # n'y a pas de portail — et le montage en placait alors quinze, un par
    # segment et par arc, emmeles les uns dans les autres.
    #
    # ON NE DEDUPLIQUE PAS PAR LA DISTANCE. Sur `UNI_PDL`, les hachures ne
    # recouvrent pas les polylignes : ce sont d'autres rectangles, decales de
    # deux metres, dessines pour remplir des sous-parties du poste. Un seuil
    # de proximite aurait donc a trancher entre « meme ouvrage » et « ouvrage
    # voisin », ce qu'aucune valeur ne fait proprement. La regle par COUCHE,
    # elle, ne se trompe jamais : elle n'ajoute que ce qui serait invisible.
    avec_polyligne = {e.dxf.layer for e in msp.query("LWPOLYLINE")}
    for e in msp.query("HATCH"):
        cat = _categorie(e.dxf.layer)
        if not cat or e.dxf.layer in avec_polyligne:
            continue
        for chemin_h in e.paths:
            pts = _sommets_hatch(chemin_h)
            if len(pts) >= 3:
                lignes[cat].append({"pts": pts, "fermee": True,
                                    "couche": e.dxf.layer, "forme": "hatch"})

    # LES BLOCS COMPTENT AUSSI, et ils cachent parfois l'essentiel. A Sarnois
    # IND10b, le portail, le poste de transformation et la batterie sont des
    # INSERT : ne lire que polylignes et hachures les faisait disparaitre du
    # montage. Le portail y ferait 93 px de large a 152 m sur la vue 1 — un
    # ouvrage absent, et rien ne le signalait.
    #
    # Un bloc se DEVELOPPE : `virtual_entities` rend sa geometrie deja placee
    # et tournee dans le repere du modele. On y applique la meme regle que sur
    # le modelspace, mais DANS LE BLOC : ses hachures ne sont lues que s'il n'y
    # porte aucune polyligne. Le bloc du PTR en a des deux sortes, celui du
    # portail n'a que deux secteurs de battement.
    for ins in msp.query("INSERT"):
        cat = _categorie(ins.dxf.layer)
        if not cat or _bloc_ecarte(ins.dxf.name):
            continue
        # On trie PAR BLOC QUI DESSINE, pas par INSERT de tete : la regle des
        # hachures et celle du dessin de produit, ci-dessous, se jugent l'une
        # et l'autre sur le bloc, et a Sarnois l'enveloppe et le conteneur
        # sont dessines par deux blocs differents sous un seul INSERT.
        par_bloc = {}
        for nom_bloc, ve in _filles(ins):
            polys, hachs, splines = par_bloc.setdefault(nom_bloc,
                                                        ([], [], []))
            if ve.dxftype() == "SPLINE":
                p = _sommets_spline(ve)
                if len(p) >= 2:
                    splines.append(p)
            elif ve.dxftype() == "LWPOLYLINE":
                p = [(float(x), float(y)) for x, y in ve.get_points("xy")]
                if len(p) >= 3:
                    polys.append((p, bool(ve.closed)))
            elif ve.dxftype() == "POLYLINE" and not ve.is_3d_polyline:
                p = [(float(v.dxf.location[0]), float(v.dxf.location[1]))
                     for v in ve.vertices]
                if len(p) >= 3:
                    polys.append((p, bool(ve.is_closed)))
            elif ve.dxftype() == "HATCH":
                for chemin_h in ve.paths:
                    q = _sommets_hatch(chemin_h)
                    if len(q) >= 3:
                        hachs.append(q)
        for polys, hachs, splines in par_bloc.values():
            for c in _chainer(splines):
                if len(c) >= 3:
                    polys.append((c, True))
            if not polys:
                polys = [(q, True) for q in hachs]
            for p, fermee in _contour_produit(polys):
                lignes[cat].append({"pts": p, "fermee": fermee,
                                    "couche": ins.dxf.layer, "forme": "bloc"})

    return Scene(tables=tables, lignes={k: v for k, v in lignes.items() if v},
                 topo=topo, source=str(chemin))


if __name__ == "__main__":
    import sys
    from pathlib import Path
    HERE = Path(__file__).resolve().parent
    cibles = sys.argv[1:] or [
        HERE / "exemples" / "sarnois-A" / "2026_08_025-IMP-DEV-Fixe-IND10a_V2.dxf",
        HERE / "exemples" / "saint-cyr" / "20260903_SCV_IND06.dxf",
    ]
    for c in cibles:
        print(f"\n=== {Path(c).name} ===")
        print(" ", lire(c).resume().replace("\n", "\n "))
