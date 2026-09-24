#!/usr/bin/env python3
"""Tests du generateur de page de calage.

Ils ne touchent ni le reseau ni un plan reel : ils verrouillent le CONTRAT
entre le gabarit et le generateur. C'est la seule chose qui puisse casser en
silence — une page qui garde l'en-tete du projet precedent s'ouvre tres bien
et affiche les mauvaises coordonnees.
"""
import re

import pytest

import preparer_calage as PC

#: Ce que le generateur sait remplir. Toute autre marque dans le gabarit
#: ressortirait telle quelle dans la page livree.
MARQUES = {"__TITRE__", "__SOUS_TITRE__", "__FICHIER__", "__DONNEES__",
           "__PHOTO__", "__ORTHO__"}


@pytest.fixture(scope="module")
def gabarit():
    assert PC.GABARIT.exists(), f"gabarit absent : {PC.GABARIT}"
    return PC.GABARIT.read_text(encoding="utf-8")


def test_le_gabarit_porte_toutes_les_marques(gabarit):
    for m in MARQUES:
        assert m in gabarit, f"{m} manque au gabarit"


def test_le_gabarit_ne_porte_aucune_marque_inconnue(gabarit):
    trouvees = set(re.findall(r"__[A-Z_]+__", gabarit))
    assert trouvees <= MARQUES, f"marques non remplies : {trouvees - MARQUES}"


def test_le_gabarit_ne_garde_aucune_donnee_du_projet_precedent(gabarit):
    """Le defaut constate : l'en-tete annoncait Saint-Cyr sur une page Sarnois.

    Les coordonnees, l'appareil et la date etaient ceux de la vue precedente,
    et rien ne le signalait — la page s'ouvrait parfaitement.
    """
    for interdit in ("Saint-Cyr", "Galaxy A55", "47.852154", "1.968753",
                     "PM (3).jpg"):
        assert interdit not in gabarit, f"{interdit!r} est reste en dur"


def test_le_gabarit_lit_ses_donnees_dans_le_bloc_json(gabarit):
    assert 'id="donnees"' in gabarit
    assert "JSON.parse(document.getElementById('donnees')" in gabarit


def test_les_marques_sont_uniques(gabarit):
    """Un `replace` remplit toutes les occurrences : deux marques identiques
    a des endroits differents donneraient deux fois la meme valeur."""
    for m in MARQUES - {"__TITRE__"}:          # __TITRE__ sert au <title> ET au <h1>
        assert gabarit.count(m) == 1, f"{m} apparait {gabarit.count(m)} fois"
