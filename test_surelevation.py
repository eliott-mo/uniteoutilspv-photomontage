#!/usr/bin/env python3
"""Tests de la surelevation hors d'eau des locaux techniques.

Les valeurs viennent du dossier de Saint-Cyr-en-Val (45), ou le PPRI impose de
mettre les locaux hors des plus hautes eaux connues : plancher a 97,75 m NGF
pour un terrain naturel a 95,5 — soit environ 2 m — sur une PLATEFORME SUR
PILOTIS, le PPRI interdisant par ailleurs tout remblai nouveau en zone
inondable. Rien de cela n'est au DXF : c'est une cote de la notice.
"""
import math

import numpy as np
import pytest

import exporter_equipements as EE
import ouvrages_techniques as OT

E0, N0 = 622898.0, 6750696.0


def _rect(centre, cap, L, l):
    t = math.radians(cap)
    u = np.array([math.sin(t), math.cos(t)]); v = np.array([-u[1], u[0]])
    c = np.asarray(centre, float)
    return [tuple(c + u * (L/2) * sx + v * (l/2) * sy)
            for sx, sy in ((1, 1), (1, -1), (-1, -1), (-1, 1))]


class _Scene:
    def __init__(self, lignes):
        self.lignes = lignes


def _scene():
    return _Scene({
        "pdl": [{"pts": _rect((E0, N0), 64.1, 12.0, 3.0), "couche": "UNI_PDL"}],
        "sdis": [{"pts": _rect((E0 + 40, N0), 64.1, 8.08, 7.40),
                  "couche": "UNI_SDIS_Bache_incendie"}]})


def _haut(blocs, cle):
    return max(v[2] for v in blocs[cle]["v"]) if cle in blocs else None


def _bas(blocs, cle):
    return min(v[2] for v in blocs[cle]["v"]) if cle in blocs else None


def test_sans_declaration_rien_ne_bouge():
    """⚠️ LA SURELEVATION EST UNE EXCEPTION, PAS UNE REGLE. Elle vient d'un PPRI
    et ne concerne qu'une minorite de sites : par defaut, les locaux sont au
    sol, comme ils l'ont toujours ete."""
    b, _o, _r = OT.ouvrages(_scene(), lambda x, y: 95.5, E0, N0, verbose=False)
    assert _haut(b, "couvertine") == pytest.approx(95.5 + 3.18, abs=0.01)


def test_le_poste_monte_de_la_hauteur_declaree():
    b, _o, _r = OT.ouvrages(_scene(), lambda x, y: 95.5, E0, N0,
                            parametres={"surelevation_ouvrages_m": 2.0},
                            verbose=False)
    assert _haut(b, "couvertine") == pytest.approx(95.5 + 2.0 + 3.18, abs=0.01)


def test_la_plateforme_descend_jusqu_au_sol():
    """⚠️ UN LOCAL SURELEVE SANS RIEN DESSOUS FLOTTE, et le defaut saute aux
    yeux la ou la surelevation, elle, ne se remarque pas."""
    b, _o, _r = OT.ouvrages(_scene(), lambda x, y: 95.5, E0, N0,
                            parametres={"surelevation_ouvrages_m": 2.0},
                            verbose=False)
    assert _bas(b, "beton") <= 95.5, "les pilotis doivent toucher le sol"
    assert _haut(b, "acier") > 95.5 + 2.0, "le garde-corps est au-dessus de la dalle"


def test_la_citerne_reste_au_sol():
    """La planche PC 5-1 la montre ANCREE : une reserve souple posee sur une
    dalle sur pilotis n'aurait aucun sens."""
    assert "citerne" not in OT.SURELEVABLES
    b, _o, _r = OT.ouvrages(_scene(), lambda x, y: 95.5, E0, N0,
                            parametres={"surelevation_ouvrages_m": 2.0},
                            verbose=False)
    assert _bas(b, "pvc") == pytest.approx(95.5, abs=0.2)


def test_la_dalle_deborde_du_local():
    """Il faut de quoi tourner autour et poser un escalier : la planche montre
    un debord sur tout le pourtour."""
    beton, acier = EE.geometrie_plateforme((E0, N0), 0.0, 95.5, 97.5, 12.0, 3.0)
    v = np.array(beton["v"], float)
    assert np.ptp(v[:, 0]) > 12.0 and np.ptp(v[:, 1]) > 3.0


def test_une_longue_dalle_recoit_des_pilotis_intermediaires():
    """Six metres est la portee courante d'une poutre ; au-dela on repique."""
    court = EE.geometrie_plateforme((E0, N0), 0.0, 95.5, 97.5, 3.0, 3.0)[0]
    long = EE.geometrie_plateforme((E0, N0), 0.0, 95.5, 97.5, 12.0, 3.0)[0]
    assert len(long["f"]) > len(court["f"])
