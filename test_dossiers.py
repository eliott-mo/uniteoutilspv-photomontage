#!/usr/bin/env python3
"""Tests de la convention de dossiers : ou vont les entrees et les sorties.

Aucun de ces tests ne touche a `projets/`, qui porte des donnees de client et
n'est pas dans le depot : ils fabriquent une arborescence dans `tmp_path`. Les
noms, eux, sont ceux des quatre projets reellement charges le 27/09/2026 — ce
sont eux qui portent le piege que ces tests gardent.
"""
import pytest

import dossiers as D
import preparer_calage as PC

#: Les quatre projets charges. Noter « Loire » : il est dans DEUX d'entre eux.
NOMS = ("03. Gannay-sur-Loire", "34. Bédarieux",
        "71. Saint-Aubin-sur-Loire", "88. Auzainvilliers")


@pytest.fixture
def projets(tmp_path, monkeypatch):
    racine = tmp_path / "projets"
    for n in NOMS:
        (racine / n).mkdir(parents=True)
    monkeypatch.setattr(D, "PROJETS", racine)
    return racine


# ------------------------------------------------ designer un projet
@pytest.mark.parametrize("fragment,attendu", [
    ("Gannay", "03. Gannay-sur-Loire"),
    ("gannay", "03. Gannay-sur-Loire"),          # la casse ne compte pas
    ("88", "88. Auzainvilliers"),                # le numero de departement suffit
    ("Bédarieux", "34. Bédarieux"),
    ("03. Gannay-sur-Loire", "03. Gannay-sur-Loire"),
])
def test_un_fragment_suffit_a_designer_un_projet(projets, fragment, attendu):
    """Les dossiers portent leur numero de departement, qu'on n'a pas envie
    de retaper quinze fois."""
    assert D.projet(fragment).name == attendu


def test_un_fragment_ambigu_est_une_erreur_pas_un_choix(projets):
    """⚠️ ECRIRE DANS LE MAUVAIS PROJET NE SE VOIT PAS.

    Les fichiers portent les memes noms d'un projet a l'autre, et un montage
    depose au mauvais endroit y ressemble a un montage. « Loire » designe a la
    fois Gannay-sur-Loire et Saint-Aubin-sur-Loire : il doit s'arreter la.
    """
    with pytest.raises(D.ProjetIntrouvable, match="2 projets"):
        D.projet("Loire")


def test_un_projet_inconnu_dit_ceux_qu_il_connait(projets):
    """Une faute de frappe se corrige sans aller voir le dossier."""
    with pytest.raises(D.ProjetIntrouvable) as e:
        D.projet("Machin")
    for n in NOMS:
        assert n in str(e.value)


# ------------------------------------------------------- l'atelier
def test_l_atelier_est_a_cote_de_ses_entrees(projets):
    d = D.montages("Gannay")
    assert d.name == "montages"
    assert d.parent.name == "03. Gannay-sur-Loire"
    assert d.is_dir(), "le dossier doit etre cree"


def test_on_peut_demander_le_chemin_sans_le_creer(projets):
    d = D.montages("Bédarieux", creer=False)
    assert not d.exists()


# -------------------------------------------------------- le contrat
def test_le_contrat_se_cherche_au_lieu_de_s_exiger_a_un_chemin_fixe(projets):
    """Un zip du generateur se decompresse en `contrat/PV-xxx/` ou en
    `PV-xxx/` selon la facon de l'ouvrir, et les deux sont raisonnables."""
    c = projets / "03. Gannay-sur-Loire" / "contrat" / "PV-gan"
    c.mkdir(parents=True)
    (c / "geometries.gpkg").write_bytes(b"")
    (c / "projet.json").write_text("{}", encoding="utf-8")
    assert D.contrat("Gannay") == c


def test_sans_contrat_le_message_dit_quoi_faire(projets):
    with pytest.raises(D.ProjetIntrouvable, match="decompresse"):
        D.contrat("Auzainvilliers")


def test_deux_contrats_sont_une_erreur(projets):
    """Deux versions decompressees cote a cote : il faut trancher a la main."""
    for n in ("PV-gan", "PV-gan-v2"):
        c = projets / "03. Gannay-sur-Loire" / n
        c.mkdir(parents=True)
        (c / "geometries.gpkg").write_bytes(b"")
    with pytest.raises(D.ProjetIntrouvable, match="2 contrats"):
        D.contrat("Gannay")


# ------------------------------- ce que `--projet` resout pour le calage
@pytest.fixture
def gannay(projets):
    base = projets / "03. Gannay-sur-Loire"
    c = base / "contrat" / "PV-gan"
    c.mkdir(parents=True)
    (c / "geometries.gpkg").write_bytes(b"")
    (base / "photos").mkdir()
    (base / "photos" / "IMG_0001.jpg").write_bytes(b"")
    (base / "Photos géolocalisées.html").write_text("", encoding="utf-8")
    return base


def test_la_photo_se_retrouve_n_importe_ou_sous_le_projet(gannay):
    plan, photo, sortie, rapport = PC.depuis_projet("Gannay", "IMG_0001.jpg")
    assert photo == gannay / "photos" / "IMG_0001.jpg"
    assert plan.name == "PV-gan"


def test_la_sortie_tombe_dans_l_atelier(gannay):
    _plan, _photo, sortie, _rapport = PC.depuis_projet("Gannay", "IMG_0001.jpg")
    assert sortie.parent == gannay / "montages"
    assert sortie.name == "calage_IMG_0001.html"


def test_la_carte_du_projet_est_prise_d_office(gannay):
    _plan, _photo, _sortie, rapport = PC.depuis_projet("Gannay", "IMG_0001.jpg")
    assert rapport.name == "Photos géolocalisées.html"


def test_deux_cartes_dans_le_projet_n_en_designent_aucune(gannay):
    """Mieux vaut l'EXIF qu'une carte tiree au sort : la position replacee
    d'un AUTRE projet serait fausse sans que rien ne le signale."""
    (gannay / "autre carte.html").write_text("", encoding="utf-8")
    _p, _ph, _s, rapport = PC.depuis_projet("Gannay", "IMG_0001.jpg")
    assert rapport is None


def test_un_nom_de_photo_ambigu_s_arrete(gannay):
    (gannay / "IMG_0001.jpg").write_bytes(b"")     # le meme nom a deux endroits
    with pytest.raises(ValueError, match="2 fichier"):
        PC.depuis_projet("Gannay", "IMG_0001.jpg")


def test_un_chemin_de_photo_explicite_passe_tel_quel(gannay, tmp_path):
    """Une photo hors du projet reste utilisable : on ne force personne."""
    ailleurs = tmp_path / "ailleurs.jpg"
    ailleurs.write_bytes(b"")
    _p, photo, _s, _r = PC.depuis_projet("Gannay", ailleurs)
    assert photo == ailleurs
