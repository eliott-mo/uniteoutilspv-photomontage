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


# --------------------------------------- la pose de depart vient du rapport
def _carte(points):
    """Une carte `photos-geoloc` reduite a ce que le generateur y lit."""
    import json
    return ('<html><body><script id="donnees-carte" type="application/json">'
            + json.dumps({"version": 6, "points": points})
            + "</script></body></html>")


def test_le_point_replace_du_rapport_est_lu(tmp_path):
    """⚠️ LE POINT DU RAPPORT VAUT MIEUX QUE L'EXIF, et c'est pour cela qu'on
    le lit.

    Le chef de projet replace le point sur le fond satellite et calibre le
    cone de visee. L'EXIF, lui, porte la position brute du telephone — 5 a
    10 m — et un cap compas mesure faux de 28 a 47 degres sur les vingt-cinq
    cliches de Sarnois.
    """
    f = tmp_path / "carte.html"
    f.write_text(_carte([
        {"nom": "IMG_0001.jpg", "lat": 46.7, "lon": 3.6, "cap": 314.0,
         "source_position": "Saisie"},
        {"nom": "IMG_0002.jpg", "lat": 46.8, "lon": 3.7, "cap": 8.0,
         "source_position": "EXIF"}]), encoding="utf-8")
    p = PC.point_du_rapport(f, "IMG_0002.jpg")
    assert p == {"lat": 46.8, "lon": 3.7, "cap": 8.0, "source": "EXIF"}


def test_le_nom_se_compare_sans_extension_ni_casse(tmp_path):
    """Le rapport garde le nom d'origine, `.HEIC` la ou le fichier est `.jpg`."""
    f = tmp_path / "carte.html"
    f.write_text(_carte([{"nom": "IMG_0420.HEIC", "lat": 46.7, "lon": 3.6,
                          "cap": 12.0, "source_position": "EXIF"}]),
                 encoding="utf-8")
    assert PC.point_du_rapport(f, "img_0420.jpg")["cap"] == 12.0


def test_une_photo_absente_du_rapport_rend_none(tmp_path):
    """L'EXIF doit alors reprendre la main, pas planter."""
    f = tmp_path / "carte.html"
    f.write_text(_carte([{"nom": "IMG_0001.jpg", "lat": 46.7, "lon": 3.6,
                          "cap": 1.0, "source_position": "EXIF"}]),
                 encoding="utf-8")
    assert PC.point_du_rapport(f, "IMG_9999.jpg") is None


def test_un_point_sans_position_rend_none(tmp_path):
    """Une photo non geolocalisee figure dans la carte, sans lat ni lon."""
    f = tmp_path / "carte.html"
    f.write_text(_carte([{"nom": "IMG_0001.jpg", "lat": None, "lon": None,
                          "cap": None, "source_position": None}]),
                 encoding="utf-8")
    assert PC.point_du_rapport(f, "IMG_0001.jpg") is None


def test_un_fichier_qui_n_est_pas_une_carte_rend_none(tmp_path):
    f = tmp_path / "pas_une_carte.html"
    f.write_text("<html><body>rien du tout</body></html>", encoding="utf-8")
    assert PC.point_du_rapport(f, "IMG_0001.jpg") is None


# ------------------------------------- le plan est un DXF ou un contrat
def test_le_plan_se_lit_indifferemment_en_dxf_ou_en_contrat(tmp_path, monkeypatch):
    """Aucun appelant en aval n'a besoin de savoir laquelle des deux sources
    il a : un contrat est un DOSSIER, un plan du BE un FICHIER."""
    import lecture_contrat as LC

    vus = []
    monkeypatch.setattr(LC, "lire", lambda d, verbose=True: vus.append(("contrat", d)))
    monkeypatch.setattr(LC.lecture_dxf, "lire", lambda f: vus.append(("dxf", f)))
    dossier = tmp_path / "PV-xxx"
    dossier.mkdir()
    fichier = tmp_path / "plan.dxf"
    fichier.write_text("", encoding="utf-8")
    LC.lire_plan(dossier, verbose=False)
    LC.lire_plan(fichier)
    assert [k for k, _ in vus] == ["contrat", "dxf"]
