#!/usr/bin/env python3
"""Tests du garde-fou de prise de vue.

Les configurations réelles servent d'ancrage : trois vues de Sarnois que le
chef de projet juge convenables, deux vues de Saint-Cyr abandonnées après
quatre allers-retours, et une vue où la clôture passe à quatre mètres mais
s'enfuit — le cas qui a fait reformuler le critère. Elles sont reconstituées en
géométrie synthétique — `exemples/` n'est pas dans le dépôt — avec les
distances, focales et tailles d'image effectivement mesurées.

⚠️ LES DEUX VUES DU BE NE SONT PAS UN ETALON, et j'ai commencé par les prendre
pour tel. Les photos 9 et 10 de l'étude d'impact sont extraites d'un .docx à
0,4 Mpx, sans EXIF, et leur pose a été estimée à la main : celle de la vue 10
place l'œil à **un centimètre** d'une table du plan. Calibrer des seuils sur
une pose de cette qualité revenait à mesurer avec un mètre en caoutchouc.
"""

import numpy as np
import pytest

import garde_prise_de_vue as G
import lecture_dxf

E0, N0 = 622880.0, 6750700.0


def _site(d_cloture, cote=200.0, est=E0, nord=N0, cap=0.0):
    """Une enceinte carrée dont le bord le plus proche est à `d_cloture`.

    Le site s'étend vers le nord : la caméra reste à l'origine et vise le nord.
    Les tables occupent l'enceinte moins dix mètres.
    """
    y0, y1 = nord + d_cloture, nord + d_cloture + cote
    x0, x1 = est - cote / 2, est + cote / 2
    cl = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    tables = []
    for y in np.arange(y0 + 10, y1 - 10, 20.0):
        for x in np.arange(x0 + 10, x1 - 10, 40.0):
            tables.append(lecture_dxf.Table(
                q=[(x, y + 2, 100.0), (x + 20, y + 2, 100.0),
                   (x + 20, y, 97.0), (x, y, 97.0)]))
    return lecture_dxf.Scene(tables=tables,
                             lignes={"cloture": [{"pts": cl, "fermee": True}]},
                             topo=None, source="test")


# --------------------------------------------------- les quatre cas reels
CAS = [
    # nom, distance au premier ouvrage visible, f_px, largeur, hauteur, oeil
    ("Sarnois 1 convenable", 98.4, 4291, 5712, 4284, 1.60, True),
    ("Sarnois 6 convenable", 31.4, 4291, 5712, 4284, 1.60, True),
    ("Sarnois 7 convenable", 32.8, 4291, 5712, 4284, 1.60, True),
    ("Sarnois 5 trop pres", 1.6, 4291, 5712, 4284, 1.60, False),
    ("Saint-Cyr PV3 abandonne", 9.4, 1355, 2040, 1530, 1.946, False),
    ("Saint-Cyr PV4 abandonne", 2.4, 1355, 2040, 1530, 1.60, False),
]


@pytest.mark.parametrize("nom,d,f_px,W,H,oeil,attendu", CAS)
def test_le_controle_classe_comme_l_experience(nom, d, f_px, W, H, oeil, attendu):
    """Deux vues livrées passent, deux vues abandonnées sont recalées."""
    scn = _site(d)
    v = G.evaluer(scn, E0, N0, W, H, f_px, azimut=0.0, hauteur_oeil=oeil)
    assert v.exploitable is attendu, f"{nom} : {v.texte()}"


def test_la_vue_trop_proche_dit_les_deux_raisons():
    scn = _site(2.4)
    v = G.evaluer(scn, E0, N0, 2040, 1530, 1355, azimut=0.0)
    assert any("position indeterminee" in m for m in v.motifs)
    assert any("detail d'ouvrage" in m for m in v.motifs)


def test_le_projet_trop_loin_est_illisible():
    scn = _site(2000.0)
    v = G.evaluer(scn, E0, N0, 2040, 1530, 1355, azimut=0.0)
    assert not v.exploitable
    assert any("illisible" in m for m in v.motifs)


# ------------------------------------------ ce qui n'est PAS un defaut
def test_un_projet_qui_deborde_du_cadre_n_est_pas_un_defaut():
    """Sarnois PV10 n'en montre que 25 % et a été livré.

    Une centrale de quatre hectares vue de son bord couvre 350 degrés ; c'est
    bien pour cela qu'un dossier porte plusieurs vues.
    """
    scn = _site(25.0, cote=300.0)
    v = G.evaluer(scn, E0, N0, 1600, 1200, 1109, azimut=0.0)
    # Le site deborde bel et bien du champ...
    assert v.mesures["emprise_projet_deg"] > v.mesures["champ_horizontal_deg"]
    assert v.mesures["part_projet_dans_le_cadre_pct"] < 100
    # ... et cela ne recale rien.
    assert v.exploitable
    assert not any("cadre" in m for m in v.motifs)


# ----------------------------------- ce qui est DANS le cadre, pas autour
def test_un_ouvrage_dans_le_dos_ne_compte_pas():
    """La premiere version recalait Sarnois pour une piste derriere le dos."""
    scn = _site(25.0)
    # Une cloture parasite a trois metres, DERRIERE la camera.
    scn.lignes["cloture"].append(
        {"pts": [(E0 - 5, N0 - 3), (E0 + 5, N0 - 3)], "fermee": False})
    v = G.evaluer(scn, E0, N0, 1600, 1200, 1109, azimut=0.0)
    assert v.exploitable
    assert v.mesures["distance_premier_ouvrage_visible_m"] > 20.0


# --------------------------------------------------- l'emprise angulaire
def test_l_emprise_angulaire_enjambe_le_nord():
    """350 et 10 degres font 20 degres d'emprise, pas 340."""
    assert G._emprise_angulaire([350.0, 0.0, 10.0]) == pytest.approx(20.0)
    assert G._emprise_angulaire([80.0, 100.0]) == pytest.approx(20.0)


def test_sans_cap_le_controle_prend_la_meilleure_visee_et_le_dit():
    scn = _site(25.0)
    v = G.evaluer(scn, E0, N0, 1600, 1200, 1109)
    assert abs((v.mesures["azimut_evalue_deg"] + 180) % 360 - 180) < 10
    assert any("meilleure visee" in r for r in v.reserves)


# ------------------------------------------------- la bande recommandee
def test_la_bande_recommandee_est_l_inverse_des_criteres():
    f_px, H, oeil, sigma = 1355.0, 1530, 1.946, G.SIGMA_TELEPHONE
    d0, d1 = G.bande_recommandee(f_px, H, oeil, sigma)
    # A la borne basse, les deux criteres serres sont juste satisfaits.
    assert f_px * oeil * sigma / d0 ** 2 <= G.FLOU_MAX * H + 1e-6
    assert f_px * 2.0 / d0 / H <= G.PART_PROCHE_MAX + 1e-6
    # A la borne haute, le projet est juste encore lisible.
    assert f_px * G.HAUTEUR_TABLE / d1 / H == pytest.approx(G.PART_PROJET_MIN)


def test_un_releve_au_gps_differentiel_rapproche_la_borne_basse():
    """Une position connue a 0,5 m autorise de s'approcher davantage."""
    tel = G.bande_recommandee(1355.0, 1530, 1.946, G.SIGMA_TELEPHONE)[0]
    releve = G.bande_recommandee(1355.0, 1530, 1.946, G.SIGMA_RELEVE)[0]
    assert releve < tel
    # Mais jamais en deca de ce que le premier plan autorise.
    assert releve >= 1355.0 * 2.0 / (G.PART_PROCHE_MAX * 1530) - 1e-6


# ----------------------------------- le premier plan, colonne par colonne
def test_la_mediane_par_colonnes_est_bornee_par_le_maximum():
    """Le critere porte sur la MEDIANE, le maximum n'est donne qu'en repere.

    ⚠️ CE RAFFINEMENT N'A RIEN SAUVE, et il faut le dire. Il a ete ecrit pour
    distinguer une cloture EN TRAVERS d'une cloture qui FUIT, sur l'intuition
    qu'un chemin longeant l'emprise pourrait donner une vue propre malgre une
    cloture a trois metres. Mesure sur les 25 points de vue de Sarnois : la
    mediane et le maximum ne classent jamais differemment. Ce qui faisait
    passer les vues 1, 6 et 7 n'etait pas la fuite de la cloture mais le CAP :
    le compas EXIF y est faux de 44 a 107 degres, et une fois la visee
    corrigee, le premier ouvrage VISIBLE est a 31-98 m.

    La mediane reste la bonne grandeur — une barre de fer au coin du cadre
    n'est pas un premier plan — mais elle ne dispense pas de viser juste.
    """
    v = G.evaluer(_site(4.0), E0, N0, 2040, 1530, 1355, azimut=0.0)
    m = v.mesures
    assert m["part_ouvrage_proche_pct"] <= m["part_ouvrage_proche_max_pct"]


def test_une_cloture_en_travers_recale_la_vue():
    v = G.evaluer(_site(4.0), E0, N0, 2040, 1530, 1355, azimut=0.0)
    assert v.mesures["part_ouvrage_proche_pct"] > 100 * G.PART_PROCHE_MAX
    assert any("detail d'ouvrage" in x for x in v.motifs)


def test_une_piste_sous_les_pieds_n_est_pas_un_obstacle():
    """Vue 10 de Sarnois : le « premier ouvrage » ressortait a 0,0 m.

    Les photographes se tiennent sur les chemins, et ces chemins sont dessines
    au plan. Une piste n'a pas de hauteur : elle ne masque rien.
    """
    scn = _site(60.0)
    scn.lignes["piste"] = [{"pts": [(E0 - 50, N0), (E0 + 50, N0)], "fermee": False}]
    v = G.evaluer(scn, E0, N0, 5712, 4284, 4291, azimut=0.0)
    assert v.mesures["distance_premier_ouvrage_visible_m"] > 50.0
    assert v.exploitable


# ------------------------- position exploitable n'est pas photo exploitable
def test_sans_cap_le_verdict_porte_sur_la_position_et_le_dit():
    """La confusion qui m'a fait valider la vue 6 de Sarnois.

    Sans cap, le controle prend la meilleure visee : il repond « on peut faire
    une bonne vue d'ici », pas « cette photo en est une ». Le cap reel de la
    vue 6, cale sur quatre mats d'eoliennes a 0,4 deg de dispersion, vaut
    340,7 deg et ne met que 12 % des tables dans le cadre.
    """
    scn = _site(60.0)
    v = G.evaluer(scn, E0, N0, 5712, 4284, 4291)
    assert v.exploitable and not v.cap_connu
    assert "POSITION" in v.texte()
    assert any("PAS SUR CETTE PHOTO" in r for r in v.reserves)


def test_avec_un_cap_le_verdict_porte_bien_sur_la_photo():
    scn = _site(60.0)
    v = G.evaluer(scn, E0, N0, 5712, 4284, 4291, azimut=0.0)
    assert v.cap_connu and "POSITION" not in v.texte()


def test_le_flou_apres_calage_est_donne_a_cote_du_flou_brut():
    """L'incertitude GPS n'est pas irreductible : le calage la reduit.

    Juger une vue sur le GPS brut la condamne pour un defaut que l'etape
    suivante corrige. Mesure sur les vues retenues de Sarnois : la vue 1 passe
    de 17 % a 1,2 %, la vue 6 de 11 % a 0,8 %.
    """
    v = G.evaluer(_site(8.0), E0, N0, 2268, 4032, 3029, azimut=0.0)
    m = v.mesures
    assert m["flou_apres_calage_pct_hauteur"] < m["flou_position_pct_hauteur"]
    rapport = m["flou_position_pct_hauteur"] / m["flou_apres_calage_pct_hauteur"]
    assert rapport == pytest.approx(G.SIGMA_TELEPHONE / G.SIGMA_RELEVE, rel=1e-6)
