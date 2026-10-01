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


def test_une_brindille_de_cime_n_est_pas_un_trait():
    """⚠️ CE QUI DECOUPAIT DES FENTES DANS LE POSTE LOINTAIN.

    « Long devant sa largeur » laissait passer des amas de 6 a 13 px de haut
    sur 1 a 2 de large — des brindilles de la cime lointaine — et le masque
    ouvrait alors des fentes claires dans le poste rendu derriere elles. Cinq
    faux sur huit amas retenus, vus par le chef de projet. Le mat fait 40 px
    de haut sur une image de 618 : le seuil coupe au milieu d'un fosse de 3.
    """
    a = _ciel_avec([])
    a[368:378, 600:602] = 182               # brindille de 10 px, collee au ciel bas
    assert MA.traits_verticaux(a, 431, verbose=False).max() < 0.5


def test_le_masque_suit_la_largeur_reelle_pas_la_boite():
    """Le mat de Saint-Cyr tient dans une boite de 10 colonnes — haubanage et
    bruit l'elargissent — pour une largeur mediane de 3. Masquer la boite
    ouvrait dans les tables un trou trois fois trop large."""
    a = _ciel_avec([(878, 881, 330)])
    a[332, 872] = 182                       # un pixel de bruit, loin du mat
    a[334, 888] = 182
    m = MA.traits_verticaux(a, 431, verbose=False)
    larges = (m[400] > 0.5).sum()
    assert larges <= 5, f"{larges} colonnes masquees pour un mat de 3 px"
    assert m[400, 879] > 0.5


def test_les_plages_bornent_la_remontee(tmp_path, monkeypatch):
    """⚠️ LA REMONTEE NE SAIT PAS CE QUI EST DEVANT LA CLOTURE.

    Un buisson plante deux metres DERRIERE la touche autant qu'un arbre deux
    metres devant : la photo ne porte aucune profondeur a cet endroit. Sur
    Saint-Cyr elle a masque toute la haie, quand trois objets seulement passent
    devant. Les plages sont le jugement humain, et il est visible dans l'appel.
    """
    vues = []
    monkeypatch.setattr(MA, "masque_sous_rendu",
                        lambda *a, **k: np.zeros((618, 1224)))
    monkeypatch.setattr(MA, "garde_depuis_rendu",
                        lambda *a, **k: np.full(1224, 431.0))
    monkeypatch.setattr(MA, "traits_verticaux",
                        lambda *a, **k: np.zeros((618, 1224)))
    monkeypatch.setattr(MA, "masque_remontant",
                        lambda a, plages, *r, **k: vues.append(plages)
                        or np.zeros((618, 1224)))
    f = _photo(tmp_path)
    MA.masque_complet(f, f, verbose=False)
    assert vues[-1] == [(0, 1224)], "sans declaration, toute la largeur"
    MA.masque_complet(f, f, plages=[(350, 405), (862, 895)], verbose=False)
    assert vues[-1] == [(350, 405), (862, 895)]


def test_le_masque_suit_l_axe_d_un_mat_penche():
    """⚠️ UN MAT PENCHE, ET UNE BANDE VERTICALE NE LE SUIT PAS.

    Celui de Saint-Cyr derive d'une dizaine de pixels sur sa hauteur. Masque
    par un rectangle vertical, il laissait sur les tables une fente pale qui
    ne se superposait pas au pylone — visible a l'oeil. On ajuste donc une
    droite sur les centres de l'amas, ligne par ligne, et on la prolonge.
    """
    H, W, garde = 618, 1224, 431
    a = np.full((H, W, 3), 200, np.uint8)
    a[:, :, 2] = 215
    a[380:garde] = 70
    a[garde:] = 110
    for y in range(330, 378):               # mat incline : 10 px de derive
        x = 860 + int(round((y - 330) * 10 / 48))
        a[y, x:x + 3] = 182
    m = MA.traits_verticaux(a.astype(float), garde, verbose=False)
    haut = np.flatnonzero(m[335] > 0.5)
    bas = np.flatnonzero(m[425] > 0.5)
    assert haut.size and bas.size, "le mat doit etre masque en haut comme en bas"
    derive = bas.mean() - haut.mean()
    assert derive > 8, f"le masque ne suit pas l'inclinaison ({derive:.1f} px)"


def test_un_amas_trop_penche_est_ecarte():
    """⚠️ CE QUI A OUVERT UNE BANDE EN PLEIN MILIEU DES TABLES.

    Un amas de brindilles a 33 degres de la verticale, large de 8,5 px,
    ajustait une droite qui derivait de 51 px en descendant jusqu'a la garde :
    le masque y tracait un coin pale en travers du projet. Le vrai mat de
    Saint-Cyr penche de 5 degres ; un pylone, un poteau, un cable tendu sont
    tous proches de la verticale.
    """
    H, W, garde = 618, 1224, 431
    a = np.full((H, W, 3), 200, np.uint8); a[:, :, 2] = 215
    a[380:garde] = 70
    a[garde:] = 110
    for y in range(340, 378):               # 33 degres : derive de 25 px
        x = 600 + int(round((y - 340) * 0.65))
        a[y, x:x + 3] = 182
    assert MA.traits_verticaux(a.astype(float), garde, verbose=False).max() < 0.5


def test_on_n_extrapole_pas_plus_loin_qu_on_a_vu():
    """Un amas de 28 px de haut extrapole sur 381 derivait de 80 px.

    La droite vaut sur l'etendue de l'amas ; au-dela, elle devine. On prolonge
    d'au plus deux hauteurs d'amas, puis on descend tout droit.
    """
    H, W, garde = 618, 1224, 431
    a = np.full((H, W, 3), 200, np.uint8); a[:, :, 2] = 215
    a[200:garde] = 70                        # ciel bas : l'amas est tout en haut
    a[garde:] = 110
    for y in range(140, 198):
        x = 300 + int(round((y - 140) * 0.30))
        a[y, x:x + 3] = 182
    m = MA.traits_verticaux(a.astype(float), garde, verbose=False)
    haut = np.flatnonzero(m[145] > 0.5)
    bas = np.flatnonzero(m[425] > 0.5)
    assert haut.size and bas.size
    derive = bas.mean() - haut.mean()
    assert derive < 0.30 * 2 * 58 + 4, f"derive de {derive:.0f} px, non bornee"
