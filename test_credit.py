#!/usr/bin/env python3
"""Tests du bandeau de credit porte sous un montage.

POURQUOI IL EXISTE
------------------
Un photomontage de concertation se montre en public, et son fond n'est pas
toujours de nous : capture Street View, photo de tiers, orthophoto IGN. La
marque d'attribution du detenteur ne s'efface pas — c'est ce qu'elle est la
pour empecher — et la bonne reponse est de CREDITER lisiblement, ce qui est
d'ailleurs la condition d'un usage permis.
"""
import numpy as np
import pytest
from PIL import Image

import montage as MO


@pytest.fixture
def vue(tmp_path):
    a = np.zeros((200, 600, 3), np.uint8)
    a[:, :] = (120, 140, 90)
    a[50:60, 100:110] = (255, 0, 0)          # un repere, pour verifier l'integrite
    f = tmp_path / "montage.jpg"
    Image.fromarray(a).save(f, quality=98)
    return f


def test_le_bandeau_s_ajoute_sous_l_image_sans_rien_recouvrir(vue):
    """⚠️ IL NE S'INCRUSTE PAS. Un credit pose SUR l'image cache des pixels du
    montage, et la piece DP 6 attend des volets de meme cadrage : un bandeau
    ajoute se recadre d'un trait, un credit incruste ne se retire plus."""
    avant = np.asarray(Image.open(vue).convert("RGB"))
    MO.crediter(vue, "Fond : © Untel")
    apres = np.asarray(Image.open(vue).convert("RGB"))
    assert apres.shape[0] > avant.shape[0]
    assert apres.shape[1] == avant.shape[1]
    # ⚠️ ON COMPARE L'INTENTION, PAS L'OCTET. Un JPEG se reencode par blocs de
    # 8 et sonne sur les bords durs : le repere rouge de ce test s'ecarte a lui
    # seul de 39 niveaux d'une passe a l'autre, sans que rien ne soit recouvert.
    # Ce qui compte est que le montage soit toujours la, et entier.
    zone = apres[:avant.shape[0]].astype(int)
    assert np.abs(zone - avant.astype(int)).mean() < 1.0
    assert tuple(zone[55, 105]) == pytest.approx((255, 0, 0), abs=20),         "le repere du montage doit survivre au bandeau"


def test_un_credit_trop_long_retrecit_au_lieu_de_deborder(vue):
    """⚠️ TRONQUE, UN CREDIT N'EN EST PLUS UN : il laisse voir la mention
    d'origine a moitie et donne l'impression qu'on a voulu l'escamoter.

    Releve sur le montage de Saint-Cyr : « ... non destine a » coupe net au
    bord droit.
    """
    long = ("Photomontage UNITe · projet photovoltaique de Saint-Cyr-en-Val (45) "
            "· Fond : © Google Street View · Document de concertation, non "
            "destine au dossier de declaration prealable")
    MO.crediter(vue, long, sortie=vue.parent / "long.jpg")
    a = np.asarray(Image.open(vue.parent / "long.jpg").convert("L"), float)
    bandeau = a[200:]
    # du texte clair doit exister jusque pres du bord droit, et s'arreter avant
    colonnes = np.flatnonzero(bandeau.max(axis=0) > 120)
    assert colonnes.size, "aucun texte lisible dans le bandeau"
    assert colonnes.max() < a.shape[1] - 2, "le texte touche le bord : il deborde"
    assert colonnes.max() > 0.80 * a.shape[1], "le texte est anormalement court"


def test_la_sortie_peut_etre_un_autre_fichier(vue):
    """On garde le montage nu : les trois volets de DP 6 n'ont pas de bandeau."""
    avant = Image.open(vue).size
    MO.crediter(vue, "credit", sortie=vue.parent / "credite.jpg")
    assert Image.open(vue).size == avant
    assert Image.open(vue.parent / "credite.jpg").size[1] > avant[1]
