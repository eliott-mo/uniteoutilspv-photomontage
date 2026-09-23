#!/usr/bin/env python3
"""Tests du lecteur de contrat.

DEUX NIVEAUX, ET LE SECOND NE TOURNE PAS PARTOUT.

Les tests de forme — analyse des formats de table, ordre des sommets, refus
nommés — ne dépendent d'aucune donnée et tournent toujours.

Le test de FOND compare le contrat au DXF sur le même projet. C'est le seul qui
prouve quelque chose, et il a besoin des deux sources : le dossier de sortie de
`generateur-dp` et le DXF correspondant, dont aucun n'est dans ce dépôt. Il se
saute proprement quand ils manquent, plutôt que d'échouer et de faire croire à
une régression.
"""
import math
from pathlib import Path

import numpy as np
import pytest

import lecture_contrat as LC

HERE = Path(__file__).resolve().parent

#: Le couple de référence : le dossier de sortie et le DXF du même projet.
#: Chemins hors dépôt, sur OneDrive.
CONTRAT = (HERE.parent / "generateur-dp" / "sortie" / "PV-Sarnois-IND10B")
DXF = HERE / "exemples" / "sarnois-B" / "2026_08_27-IMP-DEV-Fixe-IND10b_V2.dxf"

besoin_donnees = pytest.mark.skipif(
    not (CONTRAT / "geometries.gpkg").exists() or not DXF.exists(),
    reason="contrat et DXF de reference absents (hors depot)")


# ---------------------------------------------------------------- forme

def test_formats_lit_un_seul_format():
    p = {"parametres": {"structures": {"format_table": "2V26"}}}
    assert LC._formats(p) == [(2, 26)]


def test_formats_lit_deux_longueurs():
    p = {"parametres": {"structures": {"format_table": "2V26/2V13"}}}
    assert LC._formats(p) == [(2, 26), (2, 13)]


def test_formats_absent_ne_leve_pas():
    assert LC._formats({}) == []


def test_quad_garde_l_ordre_haut_haut_bas_bas():
    q = LC._quad([(0, 0, 10), (5, 0, 10), (5, 3, 8), (0, 3, 8), (0, 0, 10)])
    assert [p[2] for p in q] == [10, 10, 8, 8]


def test_quad_reordonne_un_anneau_inverse():
    """Un anneau écrit bas, bas, haut, haut doit ressortir dans le bon ordre.

    `lecture_dxf` lève si les deux premiers sommets ne sont pas les plus hauts.
    Le contrat les écrit bien, mais rien ne le garantit pour un producteur à
    venir — et un anneau retourné ferait une table penchée à l'envers, ce qui
    se verrait au rendu sans qu'on sache pourquoi.
    """
    q = LC._quad([(0, 3, 8), (5, 3, 8), (5, 0, 10), (0, 0, 10), (0, 3, 8)])
    assert [p[2] for p in q] == [10, 10, 8, 8]


def test_attribution_des_formats_par_la_longueur():
    """Deux tables deux fois plus longues l'une que l'autre reçoivent 26 et 13.

    L'attribution ne lit que la géométrie : le contrat déclare les formats du
    projet mais jamais lequel s'applique à quelle table.
    """
    longue = LC.lecture_dxf.Table(q=[(0, 0, 3), (30, 0, 3), (30, 5, 1), (0, 5, 1)])
    courte = LC.lecture_dxf.Table(q=[(0, 0, 3), (15, 0, 3), (15, 5, 1), (0, 5, 1)])
    LC._attribuer_formats([longue, courte], [(2, 26), (2, 13)], verbose=False)
    assert (longue.rows, longue.cols) == (2, 26)
    assert (courte.rows, courte.cols) == (2, 13)


def test_refus_si_dossier_sans_projet_json(tmp_path):
    with pytest.raises(LC.ErreurContrat, match="projet.json"):
        LC.parametres(tmp_path)


def test_refus_si_version_trop_recente(tmp_path):
    (tmp_path / "projet.json").write_text(
        '{"version_contrat": 99}', encoding="utf-8")
    with pytest.raises(LC.ErreurVersionContrat, match="version 99"):
        LC.parametres(tmp_path)


def test_refus_si_geometries_absent(tmp_path):
    (tmp_path / "projet.json").write_text(
        '{"version_contrat": 2}', encoding="utf-8")
    with pytest.raises(LC.ErreurContrat, match="geometries.gpkg"):
        LC.lire(tmp_path, verbose=False)


# ---------------------------------------------------------------- fond

@besoin_donnees
def test_le_contrat_donne_la_meme_geometrie_que_le_dxf():
    """LE test : deux sources indépendantes, la même centrale.

    Le DXF est lu par `lecture_dxf`, le contrat par `lecture_contrat`, et
    `generateur-dp` a fait son propre chemin entre les deux. Si les tables
    sortent identiques, c'est que rien ne s'est perdu en route.
    """
    import lecture_dxf
    d = lecture_dxf.lire(DXF)
    c = LC.lire(CONTRAT, verbose=False)

    assert len(c.tables) == len(d.tables)
    qd = np.array([t.q for t in d.tables])
    qc = np.array([t.q for t in c.tables])
    for axe in range(3):
        assert qc[:, :, axe].min() == pytest.approx(qd[:, :, axe].min(), abs=0.01)
        assert qc[:, :, axe].max() == pytest.approx(qd[:, :, axe].max(), abs=0.01)

    incl = lambda s: np.mean([t.inclinaison for t in s.tables])
    assert incl(c) == pytest.approx(incl(d), abs=0.01)
    assert c.azimut_modules()[0] == pytest.approx(d.azimut_modules()[0], abs=0.02)


@besoin_donnees
def test_les_formats_retrouvent_le_decompte_declare():
    """« 79 & 11 » au tableau bilan, retrouvé par la seule géométrie.

    `nb_tables_brut` porte ce décompte, et l'attribution ne le lit pas : elle
    mesure les longueurs. Les deux doivent tomber d'accord.
    """
    p = LC.parametres(CONTRAT)
    brut = str(p["parametres"]["structures"].get("nb_tables_brut", ""))
    attendu = sorted(int(n) for n in brut.replace("&", " ").split() if n.isdigit())
    if not attendu:
        pytest.skip("le projet ne declare pas de decompte par format")
    c = LC.lire(CONTRAT, verbose=False)
    compte = {}
    for t in c.tables:
        compte[t.cols] = compte.get(t.cols, 0) + 1
    assert sorted(compte.values()) == attendu


@besoin_donnees
def test_aucune_couche_peuplee_ne_disparait_en_silence():
    """Toute couche non vide est soit reprise, soit écartée avec une raison."""
    import fiona
    c = LC.lire(CONTRAT, verbose=False)
    for couche in fiona.listlayers(CONTRAT / "geometries.gpkg"):
        if couche == "tables_pv":
            continue
        with fiona.open(CONTRAT / "geometries.gpkg", layer=couche) as src:
            if not len(src):
                continue
        assert couche in LC.CORRESPONDANCE or couche in LC.ECARTEES, (
            f"couche '{couche}' peuplee et inconnue du lecteur : elle "
            "disparaitrait sans que rien ne le dise")
