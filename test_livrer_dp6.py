#!/usr/bin/env python3
"""Tests de la livraison DP 6.

Aucun de ces tests n'a besoin des donnees de projet : ils fabriquent leurs
images. C'est voulu — la convention de nommage et le controle de cadrage sont
justement ce qui doit tenir sans qu'on aille regarder un dossier reel.
"""
import json

import pytest
from PIL import Image

import livrer_dp6 as L


def _decor(tmp_path, rogner=None, taille=(200, 150)):
    """Une pose, sa photo, et deux montages de meme taille."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", taille, (10, 20, 30)).save(tmp_path / "vue.jpg")
    pose = {"photo": "vue.jpg"}
    if rogner:
        pose["rogner"] = rogner
    (tmp_path / "pose_7.json").write_text(json.dumps(pose), encoding="utf-8")
    finale = (taille[0], rogner or taille[1])
    for nom in ("m.jpg", "mh.jpg"):
        Image.new("RGB", finale, (40, 50, 60)).save(tmp_path / nom)
    return tmp_path / "pose_7.json"


def test_trois_volets_quand_il_y_a_une_mesure_paysagere(tmp_path):
    pose = _decor(tmp_path)
    cible = tmp_path / "out"
    ecrits = L.livrer(pose, tmp_path / "m.jpg", tmp_path / "mh.jpg",
                      projet="PV-Test", dossier=cible, verbose=False)
    assert [p.name for p in ecrits] == [
        "vue7_1_etat_actuel.jpg", "vue7_2_projet.jpg",
        "vue7_3_mesures_paysageres.jpg"]


def test_deux_volets_sans_mesure_paysagere(tmp_path):
    pose = _decor(tmp_path)
    ecrits = L.livrer(pose, tmp_path / "m.jpg", projet="PV-Test",
                      dossier=tmp_path / "out", verbose=False)
    assert len(ecrits) == 2
    assert ecrits[-1].name == "vue7_2_projet.jpg"


def test_l_etat_actuel_est_rogne_comme_les_montages(tmp_path):
    """Le bandeau GPS se coupe apres composition : l'etat actuel doit suivre.

    Sans cela DP 6 empile trois images qui ne se superposent pas, et la
    comparaison avant/apres ne compare plus rien.
    """
    pose = _decor(tmp_path, rogner=90)
    ecrits = L.livrer(pose, tmp_path / "m.jpg", tmp_path / "mh.jpg",
                      projet="PV-Test", dossier=tmp_path / "out", verbose=False)
    tailles = {Image.open(p).size for p in ecrits}
    assert tailles == {(200, 90)}


def test_refus_si_un_volet_n_a_pas_le_meme_cadrage(tmp_path):
    pose = _decor(tmp_path, rogner=90)
    Image.new("RGB", (200, 150), (0, 0, 0)).save(tmp_path / "mauvais.jpg")
    with pytest.raises(L.ErreurLivraison, match="cadrage"):
        L.livrer(pose, tmp_path / "mauvais.jpg", projet="PV-Test",
                 dossier=tmp_path / "out", verbose=False)


def test_refus_sans_nom_de_projet(tmp_path):
    pose = _decor(tmp_path)
    with pytest.raises(L.ErreurLivraison, match="projet"):
        L.livrer(pose, tmp_path / "m.jpg", dossier=tmp_path / "out",
                 verbose=False)


def test_refus_si_un_montage_manque(tmp_path):
    pose = _decor(tmp_path)
    with pytest.raises(L.ErreurLivraison, match="introuvable"):
        L.livrer(pose, tmp_path / "absent.jpg", projet="PV-Test",
                 dossier=tmp_path / "out", verbose=False)


def test_le_tri_alphabetique_groupe_par_vue_et_ordonne_les_volets(tmp_path):
    """La propriete sur laquelle repose toute la convention.

    L'application de generateur-dp ecrit les photographies sous leur propre
    nom : le nom est le seul canal. Trois vues melangees doivent se retrouver
    groupees et dans l'ordre par un simple tri.
    """
    cible = tmp_path / "out"
    for vue in (12, 2, 7):
        pose = _decor(tmp_path / f"v{vue}")
        L.livrer(pose, tmp_path / f"v{vue}" / "m.jpg",
                 tmp_path / f"v{vue}" / "mh.jpg", projet="PV-Test", vue=vue,
                 dossier=cible, verbose=False)
    noms = sorted(p.name for p in cible.iterdir())
    # Chaque groupe de trois porte la meme vue, et ses volets sont en ordre.
    for debut in range(0, len(noms), 3):
        groupe = noms[debut:debut + 3]
        assert len({n.split("_")[0] for n in groupe}) == 1
        assert [n.split("_")[1] for n in groupe] == ["1", "2", "3"]
