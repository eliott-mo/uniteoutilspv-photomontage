#!/usr/bin/env python3
"""Tests du contrôle de conformité au plan.

Chaque test reconstitue UN défaut réellement observé sur Saint-Cyr, et vérifie
que le contrôle l'aurait signalé. C'est le but du module : ces trois défauts
ont coûté quatre allers-retours parce qu'aucun ne se lisait sur le rendu.
"""
import math

import numpy as np
import pytest

import conformite as CF
import ouvrages_techniques as OT

E0, N0 = 622880.0, 6750700.0


def _rect(centre, cap, L, l):
    t = math.radians(cap)
    u = np.array([math.sin(t), math.cos(t)])
    v = np.array([-u[1], u[0]])
    c = np.asarray(centre, float)
    return [tuple(c + u * (L / 2) * sx + v * (l / 2) * sy)
            for sx, sy in ((1, 1), (1, -1), (-1, -1), (-1, 1))]


class _Scene:
    def __init__(self, lignes):
        self.lignes = lignes


def _nappe(coins, z=100.0):
    """Un bloc de sol : deux triangles, en coordonnees LOCALES (E-E0, N-N0)."""
    v = [[x - E0, y - N0, z] for x, y in coins]
    return {"materiau": "grave", "v": v, "f": [[0, 1, 2], [0, 2, 3]]}


def _plan_avec_piste():
    piste = _rect((E0, N0 + 20.0), 0.0, 20.0, 6.0)
    return _Scene({"piste": [{"pts": piste, "couche": "UNI_VRD_Piste_a_creer"}],
                   "cloture": [{"pts": _rect((E0, N0 + 20.0), 0.0, 80.0, 60.0),
                                "fermee": True}]}), piste


# ----------------------------------------------------- 1. surface hors plan
def test_un_tablier_de_grave_absent_du_plan_est_signale():
    """Le defaut qui a coute quatre iterations : 356 m2 inventes."""
    scn, piste = _plan_avec_piste()
    tablier = _rect((E0 + 15.0, N0 + 20.0), 0.0, 12.0, 8.0)   # nulle part au plan
    scene = {"objets": [_nappe(piste), _nappe(tablier)], "registre": []}
    a = CF.verifier(scene, scn, E0, N0)
    assert any("aucun polygone du plan" in x for x in a)
    assert any("96 m2" in x for x in a)


def test_une_grave_qui_suit_le_plan_ne_dit_rien():
    scn, piste = _plan_avec_piste()
    scene = {"objets": [_nappe(piste)], "registre": []}
    assert CF.verifier(scene, scn, E0, N0) == []


# ------------------------------------------------- 2. debord hors enceinte
def test_un_volume_qui_sort_de_l_enceinte_est_signale():
    """La bache montee au gabarit : 15 % de son aire dehors."""
    scn, _ = _plan_avec_piste()
    dehors = _rect((E0 + 42.0, N0 + 20.0), 0.0, 10.0, 8.0)
    scene = {"objets": [{"materiau": "pvc",
                         "v": [[x - E0, y - N0, 100.0] for x, y in dehors],
                         "f": [[0, 1, 2], [0, 2, 3]]}], "registre": []}
    a = CF.verifier(scene, scn, E0, N0)
    assert any("hors de l'enceinte" in x for x in a)


def test_une_piste_a_le_droit_de_sortir_de_l_enceinte():
    """Elle rejoint la voie publique. Seuls les VOLUMES doivent rester dedans."""
    scn, _ = _plan_avec_piste()
    scn.lignes["piste"].append(
        {"pts": _rect((E0 + 42.0, N0 + 20.0), 0.0, 10.0, 6.0),
         "couche": "UNI_VRD_Piste_a_creer"})
    sortante = _rect((E0 + 42.0, N0 + 20.0), 0.0, 10.0, 6.0)
    scene = {"objets": [_nappe(sortante)], "registre": []}
    assert CF.verifier(scene, scn, E0, N0) == []


# ------------------------------------------------ 3. ouvrage hors du plan
def test_un_ouvrage_monte_au_gabarit_au_lieu_du_plan_est_signale():
    """8,08 x 7,40 au plan, monte 11,70 x 8,90 : 59 % de recouvrement."""
    scn, _ = _plan_avec_piste()
    plan = _rect((E0, N0 + 20.0), 64.1, 8.08, 7.40)
    monte = _rect((E0, N0 + 20.0), 64.1, 11.70, 8.90)
    scene = {"objets": [], "registre": [
        {"nom": "citerne", "couche": "UNI_SDIS_Bache_incendie",
         "plan": plan, "monte": monte}]}
    a = CF.verifier(scene, scn, E0, N0)
    assert any("citerne" in x and "recouvrement" in x for x in a)


def test_un_ouvrage_tourne_d_un_quart_de_tour_est_signale():
    """Le piege `ordre_cotes` : 12 x 3 dessine 3 x 12 se rend parfaitement."""
    scn, _ = _plan_avec_piste()
    scene = {"objets": [], "registre": [
        {"nom": "poste", "couche": "UNI_PDL",
         "plan": _rect((E0, N0 + 20.0), 64.1, 12.0, 3.0),
         "monte": _rect((E0, N0 + 20.0), 64.1, 3.0, 12.0)}]}
    assert any("poste" in x for x in CF.verifier(scene, scn, E0, N0))


def test_un_ouvrage_pose_sur_son_trace_ne_dit_rien():
    scn, _ = _plan_avec_piste()
    r = _rect((E0, N0 + 20.0), 64.1, 12.0, 3.0)
    scene = {"objets": [], "registre": [
        {"nom": "poste", "couche": "UNI_PDL", "plan": r, "monte": r}]}
    assert CF.verifier(scene, scn, E0, N0) == []


# --------------------------------------------------- bout en bout, sur le plan
def test_le_registre_sort_de_ouvrages_et_se_confronte():
    """Ce que `ouvrages` monte doit se relire sans rejouer l'export."""
    bache = _rect((E0, N0 + 20.0), 64.1, 8.08, 7.40)
    scn = _Scene({"sdis": [{"pts": bache, "couche": "UNI_SDIS_Bache_incendie"}]})
    _blocs, _ouv, registre = OT.ouvrages(scn, lambda x, y: 100.0, E0, N0,
                                         verbose=False)
    assert len(registre) == 1 and registre[0]["nom"] == "citerne"
    from shapely.geometry import Polygon
    p, m = Polygon(registre[0]["plan"]), Polygon(registre[0]["monte"])
    assert p.intersection(m).area / p.union(m).area == pytest.approx(1.0, abs=1e-3)


def test_ce_que_le_plan_met_dehors_n_est_pas_signale():
    """Un poste de livraison est dehors par construction.

    Il doit rester accessible au gestionnaire de reseau depuis la voie
    publique. Mesure sur Sarnois IND10b : `UNI_PDL` est a 100 % hors de
    l'enceinte AU PLAN. Le signaler etait un faux positif — et un faux positif
    repete quinze fois finit par etre ignore.
    """
    scn, _ = _plan_avec_piste()
    dehors = _rect((E0 + 42.0, N0 + 20.0), 0.0, 10.0, 8.0)
    scene = {"objets": [{"materiau": "beton",
                         "v": [[x - E0, y - N0, 100.0] for x, y in dehors],
                         "f": [[0, 1, 2], [0, 2, 3]]}],
             "registre": [{"nom": "poste", "couche": "UNI_PDL",
                           "plan": dehors, "monte": dehors}]}
    assert CF.verifier(scene, scn, E0, N0) == []


def test_un_debord_que_le_plan_ne_prevoyait_pas_reste_signale():
    """La bache montee au gabarit : le plan la mettait dedans."""
    scn, _ = _plan_avec_piste()
    plan = _rect((E0, N0 + 20.0), 0.0, 8.0, 7.0)
    monte = _rect((E0 + 42.0, N0 + 20.0), 0.0, 10.0, 8.0)
    scene = {"objets": [{"materiau": "pvc",
                         "v": [[x - E0, y - N0, 100.0] for x, y in monte],
                         "f": [[0, 1, 2], [0, 2, 3]]}],
             "registre": [{"nom": "citerne", "couche": "UNI_SDIS_Bache",
                           "plan": plan, "monte": monte}]}
    a = CF.verifier(scene, scn, E0, N0)
    assert any("hors de l'enceinte" in x for x in a)
