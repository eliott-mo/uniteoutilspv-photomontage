#!/usr/bin/env python3
"""Tests de la clôture et du portail SUR UNE ENCEINTE PROPRE.

Ces deux defauts ne se voyaient pas tant que les plans venaient d'un DXF, ou
la cloture est tracee en dizaines de segments courts — celle de Sarnois en a
cinquante-quatre, d'une dizaine de metres. Ils sont sortis ensemble au premier
montage depuis un CONTRAT reconstitue par `generateur-dp` a partir d'un plan
PDF, ou l'enceinte est un quadrilatere PROPRE.

Valeurs mesurees sur le contrat `PV-gan` (Gannay-sur-Loire, origine
`plan_pdf`), recu le 26/09/2026 :

    enceinte     4 segments de 164,5 a 187,2 m, 697,7 m au total, fermee
    relief       201,4 a 201,9 m sur l'enceinte — un site PLAT
    portail      5 entites, dont un segment de 6,99 m dont les deux bouts
                 sont a 0,11 et 0,13 m de la cloture
"""
import math

import numpy as np
import pytest

import exporter_blender as EB
import montage as M
import ouvrages_techniques as OT

E0, N0 = 745850.0, 6625810.0            # Gannay, Lambert 93


class _Scene:
    def __init__(self, lignes):
        self.lignes = lignes


def _cloture_longue(L=180.0):
    """Un cote d'enceinte, tel qu'un contrat l'ecrit : deux points, 180 m."""
    return [{"pts": [(E0, N0), (E0 + L, N0)], "fermee": False}]


# ------------------------------------------- le grillage suit le sol
def test_le_grillage_suit_le_sol_sur_un_long_segment():
    """⚠️ LES PIQUETS SUIVENT LE SOL, LE GRILLAGE DOIT LE SUIVRE AUSSI.

    Les piquets prennent l'altitude un par un tous les trois metres. La nappe,
    elle, faisait UN quad par segment de polyligne et interpolait donc en
    ligne droite d'un bout a l'autre : sur un cote de 180 m, elle se detachait
    de ses propres piquets.

    Mesure sur Gannay, pourtant plat (201,4 a 201,9 m sur l'enceinte) :
    jusqu'a 0,49 m d'ecart, soit le QUART de la hauteur de cloture, et toujours
    vers le haut. Le defaut grandit avec le relief.

    ⚠️ CE TEST MESURE LA NAPPE, PAS SES SOMMETS. Ecrit sur les sommets il
    passait sur le code fautif : celui-ci n'en pose que deux par segment, les
    deux BOUTS, et un bout est toujours exactement sur le sol. Tout le defaut
    est entre eux. C'est le meme piege que l'echantillonnage du garde-fou de
    prise de vue, ou une cloture de 300 m a quatre sommets cachait le brin qui
    passe a deux metres de l'objectif.
    """
    # Un sol en cloche : nul aux deux bouts, 2 m au milieu. Une nappe tendue
    # d'un bout a l'autre passe donc 2 m SOUS le sol a mi-parcours.
    def sol(x, y):
        t = (x - E0) / 180.0
        return 100.0 + 2.0 * math.sin(math.pi * max(0.0, min(1.0, t)))

    _bois, gr = EB.geometrie_cloture(_Scene({"cloture": _cloture_longue()}),
                                     sol, E0 + 90.0, N0, dmax=300.0)
    v = np.array(gr["v"], float)
    pire = 0.0
    for f in gr["f"]:
        q = v[list(f)]
        bas = q[q[:, 2] <= q[:, 2].min() + 1e-6 + (q[:, 2].max() - q[:, 2].min()) / 2]
        for t in np.linspace(0.0, 1.0, 9):        # le long de l'arete basse
            p = bas[0] + (bas[-1] - bas[0]) * t
            pire = max(pire, abs(float(p[2]) - sol(p[0], p[1])))
    assert pire < 0.05, f"la nappe s'ecarte du sol de {pire:.2f} m"


def test_le_grillage_est_decoupe_au_pas_des_piquets():
    """Un panneau va d'un piquet au suivant : c'est ce qu'est une cloture."""
    scn = _Scene({"cloture": _cloture_longue(180.0)})
    _bois, gr = EB.geometrie_cloture(scn, lambda x, y: 100.0, E0 + 90.0, N0,
                                     dmax=300.0)
    assert len(gr["f"]) == pytest.approx(180.0 / M.PAS_PIQUET, abs=1)


# ------------------------------- une ouverture n'efface que ce qu'elle couvre
def test_un_portail_n_efface_que_les_panneaux_qu_il_couvre():
    """⚠️ LE DEFAUT LE PLUS COUTEUX DES DEUX, ET LE PLUS INVISIBLE.

    L'ouverture se jugeait sur le MILIEU du segment de polyligne. Deux effets,
    tous deux muets :

      - un portail tombant au milieu d'un segment de 180 m en effacait les
        180 metres. Sur l'enceinte a quatre cotes de Gannay, il ne restait que
        TROIS cotes sur quatre — soit 3 faces de grillage au lieu de 166 ;
      - un portail tombant ailleurs qu'au milieu n'ouvrait rien du tout, et le
        grillage traversait alors le vantail.
    """
    scn = _Scene({"cloture": _cloture_longue(180.0)})
    sol = lambda x, y: 100.0                                    # noqa: E731
    plein, gr_plein = EB.geometrie_cloture(scn, sol, E0 + 90.0, N0, dmax=300.0)
    # portail de 7 m au MILIEU, la ou l'ancienne regle effacait tout
    _b, gr = EB.geometrie_cloture(scn, sol, E0 + 90.0, N0, dmax=300.0,
                                  ouvertures=[(E0 + 90.0, N0, 7.0 / 2 + 0.6)])
    assert len(gr["f"]) > 0.9 * len(gr_plein["f"]), (
        "l'ouverture a efface bien plus que le portail")
    assert len(gr["f"]) < len(gr_plein["f"]), "l'ouverture n'a rien efface"
    # et rien ne subsiste DANS l'ouverture
    v = np.array(gr["v"], float)
    assert not np.any(np.abs(v[:, 0] - (E0 + 90.0)) < 3.0)


def test_un_portail_hors_du_milieu_ouvre_quand_meme():
    """L'autre moitie du meme defaut : au quart du segment, rien ne s'ouvrait."""
    scn = _Scene({"cloture": _cloture_longue(180.0)})
    sol = lambda x, y: 100.0                                    # noqa: E731
    _b, plein = EB.geometrie_cloture(scn, sol, E0 + 90.0, N0, dmax=300.0)
    _b, gr = EB.geometrie_cloture(scn, sol, E0 + 90.0, N0, dmax=300.0,
                                  ouvertures=[(E0 + 45.0, N0, 7.0 / 2 + 0.6)])
    assert len(gr["f"]) < len(plein["f"])
    v = np.array(gr["v"], float)
    assert not np.any(np.abs(v[:, 0] - (E0 + 45.0)) < 3.0)


# ------------------------------------- le portail dessine prime sur le deduit
def test_un_portail_dessine_en_corde_de_cloture_se_lit_tel_quel():
    """⚠️ QUAND LE PLAN DESSINE LE PORTAIL, ON LE LIT AU LIEU DE LE DEDUIRE.

    Le contrat de Gannay ecrit le portail en cinq entites : un segment de
    6,99 m dont les deux bouts touchent la cloture, deux vantaux de 3,50 m et
    deux arcs de battement. L'heuristique des pivots, elle, cherche un segment
    de CLOTURE de la bonne largeur — or cette enceinte n'a que quatre cotes de
    170 a 190 m. Faute de le trouver, elle retombait sur l'ecartement des
    pivots et donnait **3,38 m pour un portail declare a 7,00 m**.
    """
    a = (E0 + 88.0, N0)
    b = (E0 + 94.99, N0)
    scn = _Scene({"cloture": _cloture_longue(180.0),
                  "portail": [{"pts": [a, b]}]})
    p = OT.portails(scn)
    assert len(p) == 1
    (E, N), cap, L = p[0]
    assert L == pytest.approx(6.99, abs=1e-6)
    assert (E, N) == pytest.approx(((a[0] + b[0]) / 2, N0))
    assert cap == pytest.approx(90.0, abs=1e-6)


def test_une_corde_loin_de_la_cloture_n_est_pas_un_portail():
    """Les VANTAUX aussi partent de la cloture, mais leur pointe s'en ecarte.

    Mesure sur Gannay : 0,11 m pour le bout tenu, 3,39 m pour la pointe. Une
    regle qui ne testerait qu'un seul bout prendrait chaque vantail pour un
    portail.
    """
    scn = _Scene({"cloture": _cloture_longue(180.0),
                  "portail": [{"pts": [(E0 + 88.0, N0),
                                       (E0 + 88.0, N0 + 3.5)]}]})
    assert OT._cordes(scn) == []


def test_sans_corde_dessinee_l_heuristique_des_pivots_reprend_la_main():
    """Saint-Cyr ne trace que des vantaux : cette voie doit rester vivante."""
    a, b = (E0, N0), (E0 + 7.0, N0)

    def vantail(p, q):
        c = np.array(p, float)
        d = np.array(q, float) - c
        r = math.hypot(*d)
        ang = math.atan2(d[1], d[0])
        return [tuple(c), tuple(c + r * np.array([math.cos(ang - 0.7),
                                                  math.sin(ang - 0.7)])),
                tuple(c + r * np.array([math.cos(ang), math.sin(ang)]))]

    scn = _Scene({"cloture": [{"pts": [(E0 - 30.0, N0), a, b, (E0 + 37.0, N0)],
                               "fermee": False}],
                  "portail": [{"pts": vantail(a, b)}, {"pts": vantail(b, a)}]})
    assert OT._cordes(scn) == []                 # aucun segment a deux points
    p = OT.portails(scn)
    assert len(p) == 1 and p[0][2] == pytest.approx(7.0, abs=0.01)
