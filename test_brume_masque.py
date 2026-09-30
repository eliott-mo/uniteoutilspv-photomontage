#!/usr/bin/env python3
"""Tests de la perspective aerienne et du masque de premier plan complet.

Aucun test n'ouvre Blender ni ne rend quoi que ce soit : ils portent sur ce qui
se calcule en Python — le bloc de brume ecrit a la scene, et les trois sources
du masque. Les valeurs viennent du montage de Saint-Cyr du 01/10/2026.
"""
import json

import numpy as np
import pytest
from PIL import Image

import exporter_blender as EB
import masque_avant_plan as MA


# ------------------------------------------------------ la brume
def _photo(tmp_path, ciel=(188, 194, 198), sol=(70, 80, 50), H=618, W=1224):
    a = np.zeros((H, W, 3), np.uint8)
    a[:, :] = ciel
    a[int(H * 0.72):] = sol
    f = tmp_path / "vue.jpg"
    Image.fromarray(a).save(f, quality=96)
    return f


def test_sans_declaration_il_n_y_a_pas_de_brume(tmp_path):
    """⚠️ RIEN NE CHANGE EN SILENCE SUR LES MONTAGES DEJA FAITS.

    La portee d'extinction est une propriete du JOUR ou la photo a ete prise.
    Il n'y a pas de valeur par defaut raisonnable : absente, on ne brume pas.
    """
    assert EB._brume({"horizon": 440}, _photo(tmp_path)) is None
    assert EB._brume({"brume": {}, "horizon": 440}, _photo(tmp_path)) is None


def test_la_couleur_d_air_vient_du_ciel_de_la_photo(tmp_path):
    """⚠️ PAS D'UN GRIS CHOISI. Un gris fixe ferait virer le montage des que le
    temps change, et c'est precisement ce qu'une brume doit suivre."""
    f = _photo(tmp_path, ciel=(188, 194, 198))
    b = EB._brume({"brume": {"portee_m": 1742}, "horizon": 440}, f)
    assert b["portee_m"] == 1742.0
    assert b["couleur"] == pytest.approx([188, 194, 198], abs=3)


def test_une_couleur_declaree_prime(tmp_path):
    b = EB._brume({"brume": {"portee_m": 900, "couleur": [1, 2, 3]},
                   "horizon": 440}, _photo(tmp_path))
    assert b["couleur"] == [1, 2, 3]


@pytest.mark.parametrize("d,attendu", [(0, 0.0), (200, 0.108), (400, 0.205),
                                       (1742, 0.632)])
def test_la_loi_est_celle_de_beer_lambert(d, attendu):
    """La portee se MESURE sur la photo, elle ne se choisit pas.

    Sur Saint-Cyr : vegetation sombre a L=57 vers 25 m et L=88 vers 400 m pour
    un ciel a 208, soit une part d'air de (88-57)/(208-57) = 0,205 a 400 m, donc
    une portee de -400/ln(0,795) = 1 742 m. C'est cette valeur qui a porte le
    rapport module/ciel de 0,083 a 0,238 — dans la bande des trente-sept
    montages livres (0,089 a 0,444), alors qu'il etait sous leur plancher.
    """
    import math
    assert 1.0 - math.exp(-d / 1742.0) == pytest.approx(attendu, abs=0.002)


# --------------------------------------------- les traits verticaux
def _ciel_avec(objets, H=618, W=1224, garde=431):
    """Un ciel lisse, une ligne d'arbres, et ce qu'on y plante."""
    a = np.full((H, W, 3), 200, np.uint8)
    a[:, :, 2] = 215
    a[380:garde] = 70                       # ligne d'arbres, sous le ciel
    a[garde:] = 110                         # le sol, sous la garde
    for x0, x1, y0 in objets:
        a[y0:garde, x0:x1] = 182            # un mat : faible ecart, mais long
    return a.astype(float)


def test_un_mat_fin_est_retenu():
    """⚠️ CE QUE LA REMONTEE PAR LA LUMINANCE NE PEUT PAS ATTRAPER.

    Elle monte depuis la garde tant que le pixel reste sombre et s'arrete au
    premier passage au clair. Un mat se detache SUR LE CIEL : au-dessus de la
    ligne d'arbres sa colonne redevient claire. Mesure sur Saint-Cyr, le mat
    culmine a y=330 et la remontee s'arretait a 416 — 86 px sous les tables.
    """
    a = _ciel_avec([(878, 881, 330)])
    m = MA.traits_verticaux(a, 431, verbose=False)
    assert m[335:430, 879].min() > 0.5, "le mat doit etre masque sur sa hauteur"
    assert m[335, 500] < 0.5, "le ciel voisin ne doit pas l'etre"


def test_une_masse_large_n_est_pas_un_trait():
    """Sinon la regle avalerait la ligne d'arbres du fond, et avec elle le
    projet qui est devant."""
    a = _ciel_avec([(400, 500, 330)])
    assert MA.traits_verticaux(a, 431, verbose=False).max() < 0.5


def test_un_objet_qui_flotte_dans_le_ciel_est_ecarte():
    """Un nuage sombre n'est pas ancre au sol : il ne peut rien cacher."""
    a = _ciel_avec([])
    a[100:140, 600:603] = 182               # un trait, mais loin du bas du ciel
    assert MA.traits_verticaux(a, 431, verbose=False).max() < 0.5


# ------------------------------------------------- les trois sources
def test_le_masque_complet_additionne_les_trois(tmp_path, monkeypatch):
    """⚠️ L'OUBLI D'UNE SOURCE NE SE VOIT PAS COMME UN BUG.

    Le premier montage de Saint-Cyr n'a compose qu'avec la ligne de garde : le
    conifere, le mat et le buisson passaient tous sous les tables. Le chef de
    projet l'a vu ; aucun controle ne l'aurait dit.
    """
    appels = []
    monkeypatch.setattr(MA, "masque_sous_rendu",
                        lambda *a, **k: appels.append("garde") or np.zeros((618, 1224)))
    monkeypatch.setattr(MA, "garde_depuis_rendu",
                        lambda *a, **k: np.full(1224, 431.0))
    monkeypatch.setattr(MA, "masque_remontant",
                        lambda *a, **k: appels.append("remontee") or np.zeros((618, 1224)))
    monkeypatch.setattr(MA, "traits_verticaux",
                        lambda *a, **k: appels.append("traits") or np.zeros((618, 1224)))
    f = _photo(tmp_path)
    MA.masque_complet(f, f, verbose=False)
    assert appels == ["garde", "remontee", "traits"]
