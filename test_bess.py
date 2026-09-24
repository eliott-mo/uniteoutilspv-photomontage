#!/usr/bin/env python3
"""Tests du BESS : conteneur batterie, bache de refroidissement, zone de remise.

Aucun de ces tests ne lit un plan reel. Les valeurs viennent en revanche de
trois plans mesures — Auzainvilliers APS IND03, Sarnois IND10a V2 et IND10b V2
— et du tableau bilan `20260123_AUZ_Tableau_Bilan_V3.xlsx`, qui est la seule
source des HAUTEURS : un plan est une vue de dessus.

Ce que les trois plans disent, a l'identique :

    conteneur batterie   6,06 x 3,00 m   (18,2 m2 ; bilan : « conteneur
                                          20 pieds (6x3x3m) », 18 m2)
    dalle du conteneur   8,06 x 6,00 m   (48,3 m2 ; bilan : plateforme
                                          batteries 100 m2 pour deux)
    bache de refroid.   11,70 x 9,32 m   (108,9 m2 ; bilan : 104 m2)
    zone de remise      12,01 x 3,00 m   (36,0 m2 ; bilan : 36 m2)
"""
import math

import numpy as np
import pytest

import lecture_dxf as LD
import ouvrages_techniques as OT

E0, N0 = 913565.0, 6797348.0                    # Auzainvilliers, Lambert 93


def _rect(centre, cap, L, l, fermer=False):
    t = math.radians(cap)
    u = np.array([math.sin(t), math.cos(t)])
    v = np.array([-u[1], u[0]])
    c = np.asarray(centre, float)
    pts = [tuple(c + u * (L / 2) * sx + v * (l / 2) * sy)
           for sx, sy in ((1, 1), (1, -1), (-1, -1), (-1, 1))]
    return pts + [pts[0]] if fermer else pts


class _Scene:
    def __init__(self, lignes):
        self.lignes = lignes


def _aire_bloc(bloc):
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    v = bloc["v"]
    return unary_union([Polygon([v[i][:2] for i in f]) for f in bloc["f"]]).area


# ------------------------------------------------------- le nom de la couche
def test_une_couche_de_cables_bess_n_est_pas_un_conteneur():
    """⚠️ LE PIEGE QUI A DECIDE DES MOTIFS.

    Le plan Sarnois IND10a porte six couches PVcase du genre
    `PVcase AC Cables (AC BESS - Transformer)`. Un motif « bess » nu les
    attrapait toutes, et le montage posait des conteneurs de 6 x 3 x 3 m sur
    des tirees de cable. Les motifs portent donc sur l'OUVRAGE, jamais sur le
    lot.
    """
    for couche in ("PVcase AC BESS",
                   "PVcase AC Cables (AC BESS - Transformer)",
                   "PVcase DC Cables (DC BESS - Central inverter)"):
        assert LD._categorie(couche) is None, couche


def test_le_ptr_du_bess_reste_un_poste():
    """Le bilan le compte comme tel : « Nombre de PTR associes | 1 »."""
    assert LD._categorie("UNI_BESS_PTR") == "pdl"


def test_le_bac_de_retention_n_est_mappe_par_rien():
    """Son MTEXT dit « Bac de retention 120m3 » : c'est un CREUX dans le sol.

    Le rendre en dalle surelevee de 4 cm serait un ressaut que le plan ne
    porte pas, et on n'a pas sa profondeur.
    """
    assert LD._categorie("UNI_BESS_Rétention") is None
    assert LD._categorie("UNI_BESS_Retention") is None


@pytest.mark.parametrize("couche,attendu", [
    ("UNI_BESS_Batterie", "bess"),
    ("UNI_Batterie", "bess"),
    ("UNI_BESS_Refroidissement", "refroidissement"),
    ("UNI_BESS_Zone_remise", "remise"),
    ("UNI_Zone de remise", "remise"),
])
def test_les_couches_du_bess_tombent_ou_il_faut(couche, attendu):
    assert LD._categorie(couche) == attendu


# ------------------------------------------- assembler un contour en morceaux
def test_les_morceaux_d_une_citerne_se_chainent_en_un_contour():
    """Le bloc `UNI_Refroidissement` decoupe la bache en huit splines.

    Quatre cotes droits et quatre coins arrondis, qui se suivent bout a bout
    et bouclent. Pris separement, ils donnent huit contours d'aire nulle.
    """
    coins = _rect((E0, N0), 155.5, 11.70, 8.90)
    morceaux = [[coins[i], coins[(i + 1) % 4]] for i in range(4)]
    # dans le desordre, et un troncon retourne : le chainage ne doit pas s'en
    # soucier, un DXF ne garantit ni l'ordre ni le sens.
    melange = [morceaux[2], morceaux[0][::-1], morceaux[3], morceaux[1]]
    contours = LD._chainer(melange)
    assert len(contours) == 1
    assert len(OT.anneau(contours[0])) == 4
    (E, N), _cap, L, l = OT.rectangle_mini(contours[0])
    assert (L, l) == pytest.approx((11.70, 8.90), abs=1e-6)


def test_un_contour_deja_ferme_traverse_le_chainage_intact():
    """A Auzainvilliers la meme bache tient en UNE spline fermee."""
    ferme = _rect((E0, N0), 41.6, 11.70, 8.90, fermer=True)
    contours = LD._chainer([ferme])
    assert len(contours) == 1
    assert len(OT.anneau(contours[0])) == 4


# --------------------------------------- symbole de plan / dessin de produit
def test_un_symbole_de_plan_garde_tous_ses_contours():
    """Le plus charge du corpus en porte dix (`UNI_PDT`), et ils comptent."""
    polys = [(_rect((E0, N0), 50.4, 13.3 - i, 3.2 - i * 0.1), True)
             for i in range(10)]
    assert len(LD._contour_produit(polys)) == 10


def test_un_dessin_de_produit_se_reduit_a_son_enveloppe():
    """⚠️ `BESS Skyray` porte 77 contours : le conteneur, sa paroi, trente-six
    racks de 2,32 x 0,12 m et leur boulonnerie de 5 cm.

    Montes, cela faisait trente-huit conteneurs empiles dans un seul. Et la
    regle de nidification ne sait pas trancher ici : elle tient le contour
    englobant pour une plateforme — vrai d'une dalle autour d'un poste, faux
    d'une paroi autour d'un rack — donc elle garderait les racks et jetterait
    le conteneur.
    """
    conteneur = _rect((E0, N0), 123.3, 6.06, 3.00)
    paroi = _rect((E0, N0), 123.3, 5.23, 2.36)
    racks = [(_rect((E0 + 0.1 * i, N0), 33.3, 2.32, 0.12), True)
             for i in range(75)]
    garde = LD._contour_produit([(conteneur, True), (paroi, True)] + racks)
    assert len(garde) == 1
    (_c, _cap, L, l) = OT.rectangle_mini(garde[0][0])
    assert (L, l) == pytest.approx((6.06, 3.00), abs=1e-6)


# ------------------------------------------------- la dalle et le conteneur
def test_le_conteneur_batterie_est_monte_au_plan_et_sa_dalle_devient_grave():
    """La nidification fait tout le travail, sans nommer les couches.

    Les deux plans ne posent pourtant pas la meme chose au meme endroit : a
    Auzainvilliers le bloc `BESS Skyray` est au modelspace a cote de son
    enveloppe, a Sarnois il est imbrique DANS le bloc `UNI_Batterie`. Une fois
    lus, les deux donnent ces deux contours-la.
    """
    dalle = _rect((E0, N0), 123.3, 8.06, 6.00, fermer=True)
    conteneur = _rect((E0, N0), 123.3, 6.06, 3.00, fermer=True)
    scn = _Scene({"bess": [{"pts": dalle, "couche": "UNI_BESS_Batterie"},
                           {"pts": conteneur, "couche": "UNI_BESS_Batterie"}]})
    blocs, _ouv, registre = OT.ouvrages(scn, lambda x, y: 100.0, E0, N0,
                                        verbose=False)
    assert [r["nom"] for r in registre] == ["conteneur BESS"]
    m = np.array(registre[0]["monte"])
    cotes = sorted((math.dist(m[0], m[1]), math.dist(m[1], m[2])))
    assert cotes == pytest.approx([3.00, 6.06], abs=1e-6)
    assert _aire_bloc(blocs["grave"]) == pytest.approx(8.06 * 6.00, rel=1e-6)


def test_le_conteneur_batterie_fait_trois_metres_de_haut():
    """⚠️ LA HAUTEUR NE VIENT QUE DU BILAN — un plan est une vue de dessus.

    Et ce n'est pas la hauteur d'un vrai conteneur 20 pieds maritime : le
    gabarit `local` vaut 2,59 m, le bilan dit 3,00 m pour la batterie.
    """
    assert OT.GABARITS["bess"]["h"] == 3.0
    assert OT.GABARITS["local"]["h"] != OT.GABARITS["bess"]["h"]

    conteneur = _rect((E0, N0), 123.3, 6.06, 3.00, fermer=True)
    scn = _Scene({"bess": [{"pts": conteneur, "couche": "UNI_BESS_Batterie"}]})
    blocs, _ouv, _reg = OT.ouvrages(scn, lambda x, y: 100.0, E0, N0,
                                    verbose=False)
    haut = max(v[2] for b in blocs.values() for v in b["v"])
    assert haut - 100.0 == pytest.approx(3.0, abs=0.01)


# ------------------------------------------------ la bache de refroidissement
def test_la_bache_de_refroidissement_est_une_citerne_pas_un_groupe_froid():
    """Le MTEXT de la couche dit « Citerne Souple / 120m3 »."""
    bache = _rect((E0, N0), 41.6, 11.70, 9.32, fermer=True)
    scn = _Scene({"refroidissement":
                  [{"pts": bache, "couche": "UNI_BESS_Refroidissement"}]})
    blocs, _ouv, registre = OT.ouvrages(scn, lambda x, y: 100.0, E0, N0,
                                        verbose=False)
    assert "pvc" in blocs
    assert [r["nom"] for r in registre] == ["citerne"]
    # Pas de plateforme fabriquee : le plan n'en dessine pas.
    assert "grave" not in blocs


def test_l_aire_qui_borde_la_bache_ne_devient_pas_une_seconde_bache():
    """Sarnois : 8,00 x 4,00 m a cote de la bache, SANS la recouvrir du tout.

    La nidification ne peut donc rien en dire. Monte en bache, ce rectangle
    donnait une seconde reserve de 120 m3 la ou le bilan n'en compte qu'une.
    """
    bache = _rect((E0, N0), 155.5, 11.70, 9.32, fermer=True)
    aire = _rect((E0 + 14.0, N0 + 6.0), 155.5, 8.00, 4.00, fermer=True)
    scn = _Scene({"refroidissement":
                  [{"pts": bache, "couche": "UNI_BESS_Refroidissement"},
                   {"pts": aire, "couche": "UNI_BESS_Refroidissement"}]})
    from shapely.geometry import Polygon
    assert Polygon(OT.anneau(bache)).intersection(
        Polygon(OT.anneau(aire))).area == 0.0

    assert [o["pts"] for o in OT.aires_de_citerne(scn)] == [aire]
    blocs, _ouv, registre = OT.ouvrages(scn, lambda x, y: 100.0, E0, N0,
                                        verbose=False)
    assert [r["nom"] for r in registre] == ["citerne"]
    assert _aire_bloc(blocs["grave"]) == pytest.approx(32.0, rel=1e-6)


def test_deux_baches_identiques_restent_deux_baches():
    """Le seuil ne coupe qu'entre 29 % et 100 % : un site a deux BESS en a deux."""
    a = _rect((E0, N0), 155.5, 11.70, 9.32, fermer=True)
    b = _rect((E0 + 200.0, N0), 155.5, 11.70, 9.32, fermer=True)
    scn = _Scene({"refroidissement":
                  [{"pts": a, "couche": "UNI_BESS_Refroidissement"},
                   {"pts": b, "couche": "UNI_BESS_Refroidissement"}]})
    assert OT.aires_de_citerne(scn) == []
    _blocs, _ouv, registre = OT.ouvrages(scn, lambda x, y: 100.0, E0, N0,
                                         dmax=400.0, verbose=False)
    assert [r["nom"] for r in registre] == ["citerne", "citerne"]


def test_une_diagonale_isolee_n_est_pas_une_citerne():
    """⚠️ SANS CONTOUR, ON RETOMBAIT SUR LE GABARIT.

    La couche de Sarnois IND10b porte deux polylignes de DEUX points, longues
    de 8,944 m — soit exactement hypot(8,00 ; 4,00), les diagonales du
    rectangle voisin. `rectangle_mini` rendait None, le gabarit prenait le
    relais, et chaque diagonale devenait une reserve souple de 120 m3 : trois
    baches la ou le bilan en compte une.
    """
    aire = _rect((E0, N0), 155.5, 8.00, 4.00)
    assert math.dist(aire[0], aire[2]) == pytest.approx(8.944, abs=1e-3)
    bache = _rect((E0 + 14.0, N0), 155.5, 11.70, 9.32, fermer=True)
    scn = _Scene({"refroidissement": [
        {"pts": bache, "couche": "UNI_BESS_Refroidissement"},
        {"pts": [aire[0], aire[2]], "couche": "UNI_BESS_Refroidissement"},
        {"pts": [aire[1], aire[3]], "couche": "UNI_BESS_Refroidissement"}]})
    _blocs, _ouv, registre = OT.ouvrages(scn, lambda x, y: 100.0, E0, N0,
                                         verbose=False)
    assert [r["nom"] for r in registre] == ["citerne"]


# ------------------------------------------------------- la zone de remise
def test_la_zone_de_remise_est_une_surface_pas_un_conteneur_de_plus():
    """12,01 x 3,00 m — l'empreinte exacte d'un conteneur 40 pieds, et c'est
    justement pourquoi le doute existe.

    Le bilan la compte en SURFACE (« Zone de remise (36m2) ») la ou il compte
    les conteneurs en NOMBRE, et la liste separement du « local de stockage
    materiel », qui fait aussi 36 m2. On tranche donc pour l'aire durcie.

    ⚠️ Le doute est assume DANS CE SENS-LA : monter un volume de 3 m de haut
    qui n'existe pas se voit sur un photomontage, poser une dalle plate la ou
    le sol est nu ne se voit a aucune distance utile.
    """
    assert "remise" in OT.SURFACES
    assert "remise" not in OT.MONTAGE

    zone = _rect((E0, N0), 137.7, 12.01, 3.00, fermer=True)
    scn = _Scene({"remise": [{"pts": zone, "couche": "UNI_BESS_Zone_remise"}]})
    blocs, _ouv, registre = OT.ouvrages(scn, lambda x, y: 100.0, E0, N0,
                                        verbose=False)
    assert registre == []
    assert set(blocs) == {"grave"}
    assert _aire_bloc(blocs["grave"]) == pytest.approx(36.03, rel=1e-6)
