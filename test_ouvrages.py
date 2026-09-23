#!/usr/bin/env python3
"""Tests des ouvrages techniques : cotes lues au plan, portails, ouverture.

Aucun de ces tests ne lit un plan reel. Ils fabriquent leur geometrie, et
travaillent en coordonnees LAMBERT 93 — c'est-a-dire avec un nord de l'ordre de
6 750 000. Ce n'est pas un detail : le piege corrige ici tenait entierement a
cet ordre de grandeur.
"""
import math

import numpy as np
import pytest

import ouvrages_techniques as OT

E0, N0 = 622880.0, 6750700.0


def _rect(centre, cap, L, l, fermer=False):
    """Les quatre coins d'un rectangle, dans l'ordre, en Lambert 93."""
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


# --------------------------------------------------------------- l'anneau
def test_anneau_ne_confond_pas_deux_sommets_distants_en_lambert():
    """Le piege : `np.allclose` a une tolerance RELATIVE.

    rtol=1e-5 sur 6 750 000 vaut 67 m. Ecrit avec `np.allclose`, ce test
    retirait un sommet a tout secteur de portail — qui n'en a que trois — et
    plus aucun vantail n'etait reconnu : le plan semblait sans portail.
    """
    triangle = [(E0, N0), (E0 + 3.1, N0 + 1.5), (E0 + 1.5, N0 + 3.1)]
    assert len(OT.anneau(triangle)) == 3


def test_anneau_retire_bien_un_vrai_point_de_fermeture():
    carre = _rect((E0, N0), 30.0, 8.0, 6.0, fermer=True)
    assert len(carre) == 5
    assert len(OT.anneau(carre)) == 4


# ---------------------------------------------------------- le rectangle
@pytest.mark.parametrize("cap", [0.0, 17.5, 64.1, 90.0, 154.1])
def test_rectangle_mini_retrouve_cotes_et_cap(cap):
    pts = _rect((E0, N0), cap, 12.0, 3.0)
    (E, N), lu, L, l = OT.rectangle_mini(pts)
    assert (L, l) == pytest.approx((12.0, 3.0), abs=1e-6)
    assert (E, N) == pytest.approx((E0, N0), abs=1e-6)
    # Le cap est celui du grand cote, a 180 degres pres : un rectangle n'a pas
    # de sens de parcours.
    assert min(abs(lu - cap % 180.0), 180 - abs(lu - cap % 180.0)) < 1e-6


def test_rectangle_mini_refuse_une_polyligne_a_deux_points():
    """Les diagonales du symbole d'aire d'aspiration en sont."""
    assert OT.rectangle_mini([(E0, N0), (E0 + 7.1, N0 - 5.4)]) is None


# -------------------------------------------------------------- les cotes
def test_le_plan_prime_sur_le_gabarit_mais_pas_pour_la_hauteur():
    """La bache de Saint-Cyr : 8,08 x 7,40 au plan, 11,70 x 8,90 au gabarit.

    Montee au gabarit, elle debordait de 15 % de son aire hors de l'enceinte,
    et la cloture la traversait.
    """
    g = OT._cotes(None, "citerne", OT.GABARITS["citerne"], mesure=(8.08, 7.40))
    assert (g["L"], g["l"]) == pytest.approx((8.08, 7.40))
    assert g["h"] == pytest.approx(1.50)          # jamais lisible sur un plan


def test_sans_plan_le_gabarit_reprend_la_main():
    g = OT._cotes(None, "citerne", OT.GABARITS["citerne"], mesure=None)
    assert (g["L"], g["l"], g["h"]) == pytest.approx((11.7, 8.9, 1.5))


def test_ordre_cotes_fait_foi_et_non_la_position_dans_la_chaine():
    """Un PTR se cote « largeur x longueur x hauteur ». Lu dans l'ordre, il
    sort tourne d'un quart de tour, et rien ne le signale."""
    p = {"cotes_normalisees": [{"ouvrage": "PTR",
                                "ordre_cotes": "largeur x longueur x hauteur",
                                "dimensions": "3,00 x 10,00 x 3,00"}]}
    g = OT._cotes(p, "ptr", OT.GABARITS["ptr"], mesure=None)
    assert (g["L"], g["l"]) == pytest.approx((10.0, 3.0))


# ----------------------------------------------------------- les portails
def _vantail(pivot, bout, rayon=3.5):
    """Un secteur de battement : pivot, et deux rayons vers l'exterieur."""
    p, b = np.asarray(pivot, float), np.asarray(bout, float)
    u = (b - p) / np.hypot(*(b - p))
    w = np.array([-u[1], u[0]])
    # Ordre volontairement quelconque : la pointe ne doit pas dependre du rang.
    return [tuple(p + u * rayon), tuple(p + w * rayon), tuple(p)]


def test_un_portail_est_le_segment_de_cloture_entre_deux_pivots():
    a, b = (E0 + 9.734, N0 + 1.336), (E0 + 6.678, N0 + 7.633)
    scn = _Scene({
        "cloture": [{"pts": [(E0 + 11.86, N0 + 0.74), a, b,
                             (E0 + 9.60, N0 + 10.78)], "fermee": False}],
        "portail": [{"pts": _vantail(a, b)}, {"pts": _vantail(b, a)}],
    })
    p = OT.portails(scn)
    assert len(p) == 1
    (E, N), cap, L = p[0]
    assert L == pytest.approx(7.0, abs=0.01)
    assert (E, N) == pytest.approx(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))
    assert cap == pytest.approx(
        math.degrees(math.atan2(b[0] - a[0], b[1] - a[1])), abs=1e-6)


def test_six_vantaux_font_trois_portails_et_non_six():
    """Le defaut releve : quinze traces, quinze portails emmeles."""
    scn = {"cloture": [], "portail": []}
    for k in range(3):
        a = (E0 + 20 * k, N0)
        b = (E0 + 20 * k + 7.0, N0)
        scn["cloture"].append({"pts": [(a[0] - 5, a[1]), a, b, (b[0] + 5, b[1])],
                               "fermee": False})
        scn["portail"] += [{"pts": _vantail(a, b)}, {"pts": _vantail(b, a)}]
    assert len(OT.portails(_Scene(scn))) == 3


def test_sans_cloture_les_pivots_s_apparient_quand_meme():
    a, b = (E0, N0), (E0 + 6.0, N0)
    scn = _Scene({"cloture": [],
                  "portail": [{"pts": _vantail(a, b)}, {"pts": _vantail(b, a)}]})
    p = OT.portails(scn)
    assert len(p) == 1 and p[0][2] == pytest.approx(6.0)


def test_un_ecartement_invraisemblable_ne_fait_pas_un_portail():
    a, b = (E0, N0), (E0 + 60.0, N0)
    scn = _Scene({"cloture": [],
                  "portail": [{"pts": _vantail(a, b)}, {"pts": _vantail(b, a)}]})
    assert OT.portails(scn) == []


# ------------------------------------------------- l'ouverture de cloture
def test_la_cloture_s_ouvre_au_portail():
    """Sans cela le grillage traverse le vantail — vu sur la vue 4."""
    import exporter_blender as EB

    a, b = (E0, N0), (E0 + 7.0, N0)
    scn = _Scene({"cloture": [{"pts": [(E0 - 30.0, N0), a, b, (E0 + 37.0, N0)],
                               "fermee": False}]})
    plein, _ = EB.geometrie_cloture(scn, lambda x, y: 100.0, E0, N0)
    ouvert, _ = EB.geometrie_cloture(
        scn, lambda x, y: 100.0, E0, N0,
        ouvertures=[((a[0] + b[0]) / 2, N0, 7.0 / 2 + 0.6)])
    assert len(ouvert["f"]) < len(plein["f"])
    # Aucun piquet ne subsiste dans l'ouverture.
    V = np.array(ouvert["v"], float)
    if len(V):
        assert not np.any(np.hypot(V[:, 0] - (E0 + 3.5), V[:, 1] - N0) < 3.5)


# ------------------------------------------------------- surfaces dures
def _aire_bloc(bloc):
    """Aire au sol d'un bloc triangule."""
    v = np.asarray(bloc["v"], float)
    def aire(f):
        a, b, c = v[f[0]][:2], v[f[1]][:2], v[f[2]][:2]
        return abs((b[0] - a[0]) * (c[1] - a[1])
                   - (c[0] - a[0]) * (b[1] - a[1])) / 2
    return sum(aire(f) for f in bloc["f"])


def test_la_grave_est_l_union_du_plan_et_rien_de_plus():
    """La regle qui a demande quatre iterations pour etre posee.

    Les tabliers fabriques par `geometrie_poste` et `geometrie_citerne`
    ajoutaient 356 m2 de grave absents du plan, qui se recouvraient entre eux
    et debordaient sur la cloture et la haie.
    """
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    # Deux surfaces qui se CHEVAUCHENT, comme piste et plateforme sur un plan.
    p1 = _rect((E0, N0), 0.0, 10.0, 6.0, fermer=True)
    p2 = _rect((E0 + 4.0, N0), 0.0, 10.0, 6.0, fermer=True)
    scn = _Scene({"piste": [{"pts": p1, "couche": "UNI_VRD_Piste"}],
                  "plateforme": [{"pts": p2, "couche": "UNI_VRD_Plateforme"}]})
    bloc = OT.surfaces(scn, lambda x, y: 100.0, E0, N0, verbose=False)
    attendu = unary_union([Polygon(OT.anneau(p1)), Polygon(OT.anneau(p2))]).area
    # 10 x 6 chacun, decales de 4 m : 2 m de recouvrement sur 10 m de long.
    assert attendu == pytest.approx(100.0)       # 60 + 60 - 20
    assert _aire_bloc(bloc) == pytest.approx(attendu, rel=1e-6)


def test_la_bache_ne_pose_aucune_grave():
    """Le plan ne lui dessine pas de plateforme : on ne lui en met pas."""
    bache = _rect((E0 + 11.4, N0 + 16.2), 64.1, 8.08, 7.40, fermer=True)
    scn = _Scene({"sdis": [{"pts": bache, "couche": "UNI_SDIS_Bache_incendie"}]})
    blocs, _ouv, _reg = OT.ouvrages(scn, lambda x, y: 100.0, E0, N0, verbose=False)
    assert "pvc" in blocs
    assert "grave" not in blocs


def test_l_aire_d_aspiration_passe_par_les_surfaces_et_une_seule_fois():
    aire = _rect((E0 + 6.0, N0 + 13.5), 154.1, 8.0, 4.0, fermer=True)
    scn = _Scene({"sdis": [{"pts": aire, "couche": "UNI_SDIS_Aire_d-aspiration"},
                           # les deux diagonales du symbole : pas des aires
                           {"pts": [aire[0], aire[2]], "couche": "UNI_SDIS_Aire_d-aspiration"},
                           {"pts": [aire[1], aire[3]], "couche": "UNI_SDIS_Aire_d-aspiration"}]})
    blocs, _ouv, _reg = OT.ouvrages(scn, lambda x, y: 100.0, E0, N0, verbose=False)
    assert _aire_bloc(blocs["grave"]) == pytest.approx(32.0, rel=1e-6)
    assert "pvc" not in blocs
