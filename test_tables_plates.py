#!/usr/bin/env python3
"""Tests de la reconstruction 3D d'un contrat plat.

Aucun de ces tests ne lit un contrat reel ni ne touche au reseau : ils
fabriquent des empreintes de modules et un sol synthetique. Les valeurs
viennent en revanche de deux contrats mesures — Gannay (plan PDF, 4 752
modules, inclinaison 15 deg) et Les Islettes (HelioScope, 1 590 modules,
inclinaison 25 deg).
"""
import math

import numpy as np
import pytest

import tables_plates as TP

E0, N0 = 745800.0, 6625800.0


def _module(centre, cap, larg, prof):
    """Empreinte au sol d'un module : un rectangle."""
    t = math.radians(cap)
    u = np.array([math.sin(t), math.cos(t)])          # le long de la rangee
    v = np.array([-u[1], u[0]])                       # la pente
    c = np.asarray(centre, float)
    return [tuple(c + u * (larg / 2) * sx + v * (prof / 2) * sy)
            for sx, sy in ((1, 1), (1, -1), (-1, -1), (-1, 1))]


def _bandeau(depart, cap_rangee, n_larg, n_prof, larg=1.134, prof=2.301,
             joint=0.012):
    """Un bloc de modules contigus : `n_larg` en travers, `n_prof` en profondeur."""
    t = math.radians(cap_rangee)
    u = np.array([math.sin(t), math.cos(t)])
    v = np.array([-u[1], u[0]])
    d = np.asarray(depart, float)
    mods = []
    for i in range(n_larg):
        for j in range(n_prof):
            c = d + u * i * (larg + joint) + v * j * (prof + joint)
            mods.append(_module(c, cap_rangee, larg, prof))
    return mods


def _params(inclinaison=15.0, cap_rangees=0.436, point_bas=1.1,
            larg=1.134, projetee=2.301):
    return {"modules": {"inclinaison_deg": inclinaison, "largeur_m": larg,
                        "longueur_projetee_m": projetee},
            "structures": {"point_bas_m": point_bas},
            "generalites": {"azimut_rangees_l93_deg": cap_rangees}}


def _azimut_normale(t):
    q = np.asarray(t.q, float)
    n = np.cross(q[3] - q[0], q[1] - q[0])
    if n[2] < 0:
        n = -n
    return float(np.degrees(math.atan2(n[0], n[1])) % 360)


# ------------------------------------------------- le sens de la pente
def test_les_modules_regardent_le_sud():
    """La regle physique : une centrale de l'hemisphere nord fait face au sud."""
    mods = _bandeau((E0, N0), 90.0, 6, 3)          # rangee est-ouest
    t = TP.reconstruire(mods, _params(cap_rangees=0.0),
                        lambda x, y: 200.0, verbose=False)
    assert len(t) == 1
    az = _azimut_normale(t[0])
    assert 90.0 < az < 270.0, f"les modules regardent {az:.0f} deg"
    # Et le bord bas est bien plus au sud que le bord haut.
    q = np.asarray(t[0].q, float)
    assert q[2:, 1].mean() < q[:2, 1].mean()


def test_une_pente_est_ouest_est_refusee_bruyamment():
    """Mieux vaut un refus qu'une centrale montee a l'envers.

    Le defaut ne saute pas aux yeux sur un rendu : les modules y sont juste
    tournes, et le montage a l'air normal.
    """
    # Rangees orientees nord-sud : la pente serait est-ouest, sans composante sud.
    mods = _bandeau((E0, N0), 0.0, 6, 3)
    with pytest.raises(TP.ErreurPente, match="sud"):
        TP.reconstruire(mods, _params(cap_rangees=90.0),
                        lambda x, y: 200.0, verbose=False)


# --------------------------------------------- la table est un plan rigide
@pytest.mark.parametrize("pente_sol", [0.0, 0.05, -0.08])
def test_l_inclinaison_ne_suit_pas_le_terrain(pente_sol):
    """Ce sont les pieux qu'on recoupe, pas le panneau qui ondule.

    Prendre le sol sous le bord HAUT ajoutait la pente du terrain a celle du
    panneau : mesure aux Islettes, l'inclinaison ressortait entre 24,4 et
    26,6 degres pour 25 declares.
    """
    mods = _bandeau((E0, N0), 90.0, 6, 3)
    t = TP.reconstruire(mods, _params(inclinaison=15.0, cap_rangees=0.0),
                        lambda x, y: 200.0 + pente_sol * (y - N0),
                        verbose=False)
    assert t[0].inclinaison == pytest.approx(15.0, abs=1e-6)


def test_le_bord_bas_est_a_la_hauteur_declaree():
    mods = _bandeau((E0, N0), 90.0, 6, 3)
    t = TP.reconstruire(mods, _params(point_bas=1.1, cap_rangees=0.0),
                        lambda x, y: 200.0, verbose=False)
    q = np.asarray(t[0].q, float)
    assert q[2:, 2].min() == pytest.approx(201.1, abs=1e-6)


# ------------------------------------- l'azimut des rangees tranche, pas la taille
def test_une_table_presque_carree_suit_l_azimut_du_contrat():
    """Gannay : 6,87 x 6,93 m. La regle du plus grand cote s'y trompe.

    ⚠️ `azimut_rangees_l93_deg` est la direction d'ESPACEMENT des rangees,
    donc celle de la pente. Lu comme la direction dans laquelle elles courent,
    il donnait les deux sites de reference face a l'ouest.
    """
    mods = _bandeau((E0, N0), 90.0, 6, 3)          # 6,87 large x 6,93 profond
    a = np.vstack([np.asarray(m, float) for m in mods])
    assert abs(np.ptp(a[:, 0]) - np.ptp(a[:, 1])) < 0.2, "le cas doit rester carre"
    t = TP.reconstruire(mods, _params(cap_rangees=0.0), lambda x, y: 200.0,
                        verbose=False)
    az = _azimut_normale(t[0])
    assert 150.0 < az < 210.0, f"les modules regardent {az:.0f} deg au lieu du sud"


# ------------------------------------------------------- la contiguite
def test_un_jeu_de_table_separe_les_blocs():
    """0,49 m entre deux tables a Gannay, 1,2 cm entre deux modules."""
    a = _bandeau((E0, N0), 90.0, 6, 3)
    b = _bandeau((E0 + 6 * 1.146 + 0.49, N0), 90.0, 6, 3)
    t = TP.reconstruire(a + b, _params(cap_rangees=0.0), lambda x, y: 200.0,
                        verbose=False)
    assert len(t) == 2


def test_le_joint_entre_modules_ne_separe_rien():
    mods = _bandeau((E0, N0), 90.0, 6, 3, joint=0.012)
    t = TP.reconstruire(mods, _params(cap_rangees=0.0), lambda x, y: 200.0,
                        verbose=False)
    assert len(t) == 1
    assert t[0].cols == 6 and t[0].rows == 3


def test_sans_inclinaison_au_contrat_on_refuse():
    mods = _bandeau((E0, N0), 90.0, 6, 3)
    p = _params(cap_rangees=0.0)
    p["modules"]["inclinaison_deg"] = 0.0
    with pytest.raises(TP.ErreurPente, match="inclinaison"):
        TP.reconstruire(mods, p, lambda x, y: 200.0, verbose=False)
