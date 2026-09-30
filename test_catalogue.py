#!/usr/bin/env python3
"""Tests du catalogue UNITe que le contrat fait voyager.

Les lignes de `CATALOGUE` sont celles du contrat reel
`PV-Saint-Cyr-en-Val-IND07`, recu le 30/09/2026 : dix-sept ouvrages cotes, que
`generateur-dp` ecrit sous `cotes_normalisees`. Aucun test ne lit ce contrat —
ils portent la copie des lignes qui ont servi a ecrire les regles.

CE QUE LE CATALOGUE A TRANCHE, ET QUE RIEN D'AUTRE NE DISAIT
------------------------------------------------------------
  - la « Zone de remise » et le « Bac de retention » ont une HAUTEUR declaree,
    donc ce sont des VOLUMES. Je les avais pris pour des ouvrages de sol ;
  - une citerne de 120 m3 fait 11,7 x 9,3 x 1 m, et non 11,7 x 8,9 x 1,5 :
    le gabarit du depot melangeait l'empreinte de la 120 et la hauteur de la 60 ;
  - la plus etroite largeur d'ouvrage est 3 m, ce qui donne enfin de quoi
    ecarter les bandes de dessin sans choisir un seuil a la main.
"""
import pytest

import ouvrages_techniques as OT

#: Extrait fidele du contrat Saint-Cyr IND07.
CATALOGUE = {"cotes_normalisees": [
    {"ouvrage": "Poste de transformation - PTR", "dimensions": "10 x 3 x 3m",
     "ordre_cotes": "largeur x longueur x hauteur"},
    {"ouvrage": "Poste de livraison et de transformation - PDL/PTR",
     "dimensions": "12 x 3 x 3m", "ordre_cotes": "longueur x largeur x hauteur"},
    {"ouvrage": "Poste de livraison - PDL", "dimensions": "9 x 3 x 3m",
     "ordre_cotes": "longueur x largeur x hauteur"},
    {"ouvrage": "Aire de charge (BESS) — Conteneurs", "dimensions": "6 x 3 x 3m",
     "ordre_cotes": "longueur x largeur x hauteur"},
    {"ouvrage": "Aire de charge (BESS) — Bac de rétention",
     "dimensions": "17,5 x 3 x 2,3 m", "ordre_cotes": "longueur x largeur x hauteur"},
    {"ouvrage": "Aire de charge (BESS) — Zone de remise", "dimensions": "12 x 3 x 3m",
     "ordre_cotes": "longueur x largeur x hauteur"},
    {"ouvrage": "Local de stockage matériel — P<=5MWc",
     "dimensions": "1 conteneur 20 pieds 6 x 3 x 3m",
     "ordre_cotes": "longueur x largeur x hauteur"},
    {"ouvrage": "Citerne incendie — 30", "dimensions": "7,95 x 4,44 x 1,3 m",
     "ordre_cotes": "longueur x largeur x hauteur"},
    {"ouvrage": "Citerne incendie — 60", "dimensions": "8,1 x 7,4 x 1,5 m",
     "ordre_cotes": "longueur x largeur x hauteur"},
    {"ouvrage": "Citerne incendie — 120", "dimensions": "11,7 x 9,3 x 1 m",
     "ordre_cotes": "longueur x largeur x hauteur"},
    {"ouvrage": "Citerne incendie — 240", "dimensions": "10,4 x 18,5 x 1,6 m",
     "ordre_cotes": "longueur x largeur x hauteur"},
    {"ouvrage": "Aire d'aspiration", "dimensions": "8 x 4 m",
     "ordre_cotes": "longueur x largeur"},
]}


def _par(nom):
    return next(l for l in OT.catalogue(CATALOGUE) if l[0].startswith(nom))


# --------------------------------------------------------- la lecture
def test_l_ordre_des_cotes_fait_foi_pas_leur_position():
    """⚠️ `ordre_cotes` CHANGE D'UNE LIGNE A L'AUTRE.

    « largeur x longueur x hauteur » pour le PTR, « longueur x largeur x
    hauteur » pour le PDL — les deux ecrits « 10 x 3 » et « 9 x 3 ». Lu a la
    position, le PTR ressortirait long de 10 et large de 3 alors que le
    catalogue dit l'inverse. Un poste dessine a l'envers ne se voit pas.
    """
    _nom, L, lg, h = _par("Poste de transformation")
    assert (L, lg, h) == (3.0, 10.0, 3.0)        # largeur 10, longueur 3
    _nom, L, lg, h = _par("Poste de livraison -")
    assert (L, lg, h) == (9.0, 3.0, 3.0)


def test_le_calibre_du_conteneur_n_est_pas_une_cote():
    """« 1 conteneur 20 pieds 6 x 3 x 3m » porte cinq nombres pour trois cotes."""
    _nom, L, lg, h = _par("Local de stockage")
    assert (L, lg, h) == (6.0, 3.0, 3.0)


def test_une_ligne_sans_hauteur_est_une_surface():
    """⚠️ LA SEULE FACON MACHINE-LISIBLE DE DISTINGUER LES DEUX NATURES.

    Sur les dix-sept lignes du catalogue, une seule n'a pas de hauteur :
    « Aire d'aspiration ». C'est ce qui m'a fait revenir sur la zone de remise
    et le bac de retention, que j'avais pris pour des ouvrages de sol.
    """
    assert _par("Aire d'aspiration")[3] is None
    assert _par("Aire de charge (BESS) — Zone de remise")[3] == 3.0
    assert _par("Aire de charge (BESS) — Bac de rétention")[3] == 2.3


def test_le_bac_de_retention_fait_bien_ses_120_m3():
    """17,5 x 3 x 2,3 = 120,75 m3 — le « 120m3 » que le MTEXT du plan annonce.

    C'est ce calcul qui confirme que ce n'est pas un creux : un creux de
    120 m3 n'aurait pas de hauteur declaree au-dessus du sol.
    """
    _n, L, lg, h = _par("Aire de charge (BESS) — Bac de rétention")
    assert L * lg * h == pytest.approx(120.0, abs=1.0)


# ------------------------------------------ la hauteur se choisit sur l'empreinte
@pytest.mark.parametrize("empreinte,attendu,quoi", [
    ((8.08, 7.40), 1.5, "bache de Saint-Cyr : la 60"),
    ((11.70, 9.32), 1.0, "la 120, plus large et plus basse"),
    ((7.95, 4.44), 1.3, "la 30"),
    ((18.50, 10.40), 1.6, "la 240, donnee 10,4 x 18,5 : l'ordre ne compte pas"),
])
def test_la_hauteur_d_une_citerne_vient_de_son_empreinte(empreinte, attendu, quoi):
    """⚠️ PAS DU NOM DE LA CATEGORIE.

    Le catalogue porte quatre citernes incendie et une de refroidissement.
    Chercher « citerne » par sous-chaine prenait la premiere venue. Le plan,
    lui, dit exactement laquelle c'est — par son empreinte.
    """
    g = OT._cotes(CATALOGUE, "citerne", OT.GABARITS["citerne"], empreinte)
    assert g["h"] == pytest.approx(attendu), quoi
    # Les cotes AU SOL restent celles du plan, jamais celles du catalogue.
    assert (g["L"], g["l"]) == pytest.approx(empreinte)


def test_une_empreinte_qui_ne_ressemble_a_rien_retombe_sur_le_nom():
    """Mieux vaut la hauteur de la categorie qu'une hauteur tiree au sort."""
    g = OT._cotes(CATALOGUE, "citerne", OT.GABARITS["citerne"], (40.0, 25.0))
    assert g["h"] == pytest.approx(1.3)          # la premiere « citerne » du nom
    assert (g["L"], g["l"]) == (40.0, 25.0)


# ------------------------------------- ce qui est trop etroit n'est pas un ouvrage
def test_la_plus_etroite_largeur_cotee_est_le_seuil():
    assert OT.largeur_mini(CATALOGUE) == pytest.approx(3.0)


def test_sans_catalogue_on_retombe_sur_les_gabarits():
    assert OT.largeur_mini(None) == pytest.approx(
        min(g["l"] for g in OT.GABARITS.values() if "l" in g))


def test_les_bandes_de_dessin_ne_sont_pas_des_postes():
    """⚠️ LES TROIS POSTES EMPILES DE SAINT-CYR.

    `UNI_PDL` y porte trois bandes ACCOLEES de meme cap — 3,00 / 1,50 / 1,00 m
    — formant un bloc de 12,00 x 5,50 m pose sur une plateforme de 131,4 m2,
    soit le `surface_plateforme_m2 = 132` du PDL/PTR. Elles ne se recouvrent
    pas du tout, donc la nidification n'y peut rien : seule la largeur cotee
    les separe.
    """
    import math

    import numpy as np

    class _Scene:
        def __init__(self, lignes):
            self.lignes = lignes

    E0, N0 = 622898.0, 6750696.0

    def bande(dx, largeur):
        t = math.radians(64.1)
        u = np.array([math.sin(t), math.cos(t)])
        v = np.array([-u[1], u[0]])
        c = np.array([E0, N0], float) + v * dx
        return [tuple(c + u * 6.0 * sx + v * (largeur / 2) * sy)
                for sx, sy in ((1, 1), (1, -1), (-1, -1), (-1, 1))]

    scn = _Scene({"pdl": [
        {"pts": bande(0.0, 3.0), "couche": "UNI_PDL"},
        {"pts": bande(2.25, 1.5), "couche": "UNI_PDL"},
        {"pts": bande(3.50, 1.0), "couche": "UNI_PDL"}]})
    assert OT.englobants(scn) == [], "les bandes ne se recouvrent pas"

    _b, _o, registre = OT.ouvrages(scn, lambda x, y: 100.0, E0, N0,
                                   parametres=CATALOGUE, verbose=False)
    assert len(registre) == 1, "un seul poste, pas trois"
    m = np.array(registre[0]["monte"])
    cotes = sorted((math.dist(m[0], m[1]), math.dist(m[1], m[2])))
    assert cotes == pytest.approx([3.0, 12.0], abs=1e-6)
