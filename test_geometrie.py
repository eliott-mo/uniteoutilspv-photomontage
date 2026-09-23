#!/usr/bin/env python3
"""V1 + V2 : tests du coeur geometrique du photomontage.

V2 - modele stenope :
  - confrontation a OpenCV (implementation independante) : ecart < 0,01 px
  - reponses connues (axe de visee, hors axe, hauteur, horizon, champ)
  - aller-retour projection / rayon
  - tests de MUTATION : on casse volontairement une convention (signe, axe,
    focale) et on verifie qu'au moins un test echoue. Sans cela, une erreur de
    convention passe inapercue, comme le +1,50 m en double du brief.

V1 - extraction DXF :
  - nombre de tables, dimensions, inclinaison, pas entre rangees
  - hauteur du point bas mesuree par rapport au sol topo

Lancer :  python -m pytest test_geometrie.py -v
"""
import json
import math
from pathlib import Path

import numpy as np
import pytest

from camera import MUTATIONS, Camera, focale_px_depuis_exif

HERE = Path(__file__).resolve().parent
DXF_PATH = HERE / "exemples" / "sarnois-A" / "2026_08_025-IMP-DEV-Fixe-IND10a_V2.dxf"

# Configuration asymetrique : aucun angle nul, points hors axe.
# Une configuration symetrique masquerait les erreurs de signe.
CFG = dict(largeur=2268, hauteur=4032, azimut=336.5, tangage=-8.5, roulis=3.7,
           focale_eq35=33.5, hauteur_oeil=1.60)
TOL_PX = 0.01


def cam(mutation="aucune", **kw):
    return Camera(**{**CFG, **kw}, mutation=mutation)


def point_polaire(azimut_deg, distance, altitude):
    """Point monde a un azimut et une distance donnes, altitude au-dessus du sol."""
    a = math.radians(azimut_deg)
    return [distance * math.sin(a), distance * math.cos(a), altitude]


NUAGE = np.array([
    point_polaire(336.5, 300.0, 3.5),
    point_polaire(320.0, 180.0, 1.6),
    point_polaire(350.0, 410.0, 0.0),
    point_polaire(336.5, 50.0, 12.0),
    point_polaire(325.0, 1000.0, -2.0),
    point_polaire(348.0, 95.0, 4.2),
])


# ---------------------------------------------------------------------------
# V2.1 - confrontation a OpenCV
# ---------------------------------------------------------------------------
def test_opencv_meme_projection():
    """Notre modele et cv2.projectPoints doivent coincider a 0,01 px."""
    cv2 = pytest.importorskip("cv2")
    c = cam()
    rvec, tvec, K = c.opencv()
    attendu = c.projeter(NUAGE)
    obtenu, _ = cv2.projectPoints(NUAGE.reshape(-1, 1, 3), rvec, tvec, K, None)
    obtenu = obtenu.reshape(-1, 2)
    ecart = np.abs(attendu - obtenu).max()
    assert ecart < TOL_PX, f"ecart maximal avec OpenCV : {ecart:.5f} px"


@pytest.mark.parametrize("az,tangage,roulis", [
    (0.0, 0.0, 0.0), (336.5, -8.5, 3.7), (90.0, 12.0, -4.0),
    (180.0, -3.0, 0.5), (271.3, 7.7, -2.2),
])
def test_opencv_toutes_orientations(az, tangage, roulis):
    """La coincidence avec OpenCV tient pour toutes les orientations."""
    cv2 = pytest.importorskip("cv2")
    c = cam(azimut=az, tangage=tangage, roulis=roulis)
    pts = np.array([point_polaire(az + d, 200.0, h)
                    for d, h in ((0, 2.0), (-12, 0.0), (9, 5.0), (3, -1.0))])
    rvec, tvec, K = c.opencv()
    obtenu, _ = cv2.projectPoints(pts.reshape(-1, 1, 3), rvec, tvec, K, None)
    ecart = np.abs(c.projeter(pts) - obtenu.reshape(-1, 2)).max()
    assert ecart < TOL_PX, f"ecart {ecart:.5f} px a az={az}"


def test_repere_camera_gaucher():
    """Le repere (droite, haut, avant) est GAUCHER : det(R) = -1.

    Consequence de la convention du brief : droite x haut = -avant. Ce n'est
    pas une erreur, mais il faut le savoir avant de brancher une bibliotheque
    3D. Le passage en convention OpenCV (Y vers le bas) retablit det = +1,
    et c'est cette matrice-la qui doit etre une rotation propre.
    """
    cv2 = pytest.importorskip("cv2")
    c = cam()
    R = c.R
    assert np.abs(R @ R.T - np.eye(3)).max() < 1e-12, "R doit rester orthonormale"
    assert abs(np.linalg.det(R) + 1.0) < 1e-12, "repere camera gaucher attendu"
    droite, haut, avant = R.T[:, 0], R.T[:, 1], R.T[:, 2]
    assert np.dot(np.cross(droite, haut), avant) < 0
    rvec, _, _ = c.opencv()
    R_cv, _ = cv2.Rodrigues(rvec)
    assert abs(np.linalg.det(R_cv) - 1.0) < 1e-12, "la matrice OpenCV doit etre directe"


# ---------------------------------------------------------------------------
# V2.2 - reponses connues
# ---------------------------------------------------------------------------
def test_axe_de_visee_au_centre():
    """Un point sur l'axe, a hauteur d'oeil, tangage et roulis nuls -> centre."""
    c = cam(tangage=0.0, roulis=0.0)
    uv = c.projeter([point_polaire(c.azimut, 250.0, c.h)])[0]
    assert abs(uv[0] - c.cx) < TOL_PX
    assert abs(uv[1] - c.cy) < TOL_PX


def test_sens_horaire_vers_la_droite():
    """Un azimut plus grand (sens horaire) doit apparaitre a DROITE."""
    c = cam(tangage=0.0, roulis=0.0)
    gauche = c.projeter([point_polaire(c.azimut - 10.0, 250.0, c.h)])[0]
    droite = c.projeter([point_polaire(c.azimut + 10.0, 250.0, c.h)])[0]
    assert gauche[0] < c.cx < droite[0]
    # amplitude : u = cx + f.tan(theta)
    attendu = c.cx + c.f_px * math.tan(math.radians(10.0))
    assert abs(droite[0] - attendu) < TOL_PX


def test_plus_haut_donne_v_plus_petit():
    """Un point plus haut doit avoir un v plus petit (v compte vers le bas)."""
    c = cam(tangage=0.0, roulis=0.0)
    d = 300.0
    bas = c.projeter([point_polaire(c.azimut, d, c.h)])[0]
    haut = c.projeter([point_polaire(c.azimut, d, c.h + 10.0)])[0]
    assert haut[1] < bas[1]
    attendu = c.cy - c.f_px * 10.0 / d
    assert abs(haut[1] - attendu) < TOL_PX


def test_tangage_positif_descend_l_horizon():
    """Camera relevee (tangage > 0) -> l'horizon descend dans l'image."""
    plat = cam(tangage=0.0, roulis=0.0).horizon_v()
    releve = cam(tangage=10.0, roulis=0.0).horizon_v()
    plonge = cam(tangage=-10.0, roulis=0.0).horizon_v()
    assert plonge < plat < releve
    c = cam(tangage=10.0, roulis=0.0)
    assert abs(plat - c.cy) < TOL_PX
    assert abs(releve - (c.cy + c.f_px * math.tan(math.radians(10.0)))) < TOL_PX


def test_roulis_fait_tourner_l_image():
    """Le roulis tourne l'image autour du centre, dans un sens defini.

    Convention verrouillee ici : un roulis POSITIF envoie vers la GAUCHE un
    point situe au-dessus de l'axe de visee. Le signe est teste, pas seulement
    l'amplitude, sinon une inversion de signe passerait inapercue.
    """
    d, haut = 300.0, 20.0
    p = [point_polaire(336.5, d, 1.6 + haut)]
    sans = cam(tangage=0.0, roulis=0.0).projeter(p)[0]
    plus = cam(tangage=0.0, roulis=5.0).projeter(p)[0]
    moins = cam(tangage=0.0, roulis=-5.0).projeter(p)[0]
    c = cam()
    assert abs(sans[0] - c.cx) < TOL_PX
    assert plus[0] < c.cx - 10.0, "roulis positif : le haut part a gauche"
    assert moins[0] > c.cx + 10.0
    # une rotation conserve la distance au centre
    for uv in (sans, plus, moins):
        assert abs(math.hypot(uv[0] - c.cx, uv[1] - c.cy)
                   - math.hypot(sans[0] - c.cx, sans[1] - c.cy)) < TOL_PX


@pytest.mark.parametrize("roulis", [-5.0, -1.5, 0.0, 2.0, 5.0])
def test_pente_de_l_horizon_egale_moins_tangente_du_roulis(roulis):
    """Observable de terrain : le roulis incline la ligne d'horizon.

    Pente mesuree en pixels (dv/du) = -tan(roulis). C'est ce que le CDP voit
    et c'est ce qui permettra de mesurer le roulis sur une photo.
    """
    c = cam(tangage=0.0, roulis=roulis)
    a = math.radians(c.azimut)
    loin = 1e7
    pts = []
    for d in (-15.0, 15.0):
        ad = a + math.radians(d)
        pts.append([loin * math.sin(ad), loin * math.cos(ad), c.h])
    uv = c.projeter(pts)
    pente = (uv[1, 1] - uv[0, 1]) / (uv[1, 0] - uv[0, 0])
    assert abs(pente + math.tan(math.radians(roulis))) < 1e-6


def test_est_et_nord_ne_sont_pas_interchangeables():
    """A l'azimut 45, le Nord est a gauche et l'Est a droite."""
    c = cam(azimut=45.0, tangage=0.0, roulis=0.0)
    nord = c.projeter([point_polaire(0.0, 300.0, c.h)])[0]
    est = c.projeter([point_polaire(90.0, 300.0, c.h)])[0]
    assert nord[0] < c.cx < est[0]


def test_champ_et_focale():
    """f_px suit la convention 24 mm = largeur, et le champ en decoule."""
    c = cam()
    assert abs(c.f_px - CFG["largeur"] / 24.0 * CFG["focale_eq35"]) < 1e-9
    h, v = c.champ_deg()
    assert abs(h - 2 * math.degrees(math.atan(12.0 / CFG["focale_eq35"]))) < 1e-6
    assert abs(v - 2 * math.degrees(math.atan(
        CFG["hauteur"] / CFG["largeur"] * 12.0 / CFG["focale_eq35"]))) < 1e-6


def test_points_derriere_rejetes():
    """Un point derriere la camera ne doit pas etre projete."""
    c = cam()
    derriere = point_polaire(c.azimut + 180.0, 200.0, c.h)
    assert np.isnan(c.projeter([derriere])).all()


# ---------------------------------------------------------------------------
# V2.3 - aller-retour
# ---------------------------------------------------------------------------
def test_aller_retour_projection_rayon():
    """Projeter un point puis relancer un rayon redonne la meme direction."""
    c = cam()
    uv = c.projeter(NUAGE)
    ok = ~np.isnan(uv[:, 0])
    dirs = c.rayon(uv[ok])
    vrais = NUAGE[ok] - c.position
    dirs = dirs / np.linalg.norm(dirs, axis=1, keepdims=True)
    vrais = vrais / np.linalg.norm(vrais, axis=1, keepdims=True)
    assert np.abs(dirs - vrais).max() < 1e-9


def test_rayon_du_centre_suit_l_azimut():
    """Le rayon passant par le centre de l'image pointe vers l'azimut de visee."""
    c = cam(roulis=0.0)
    d = c.rayon([[c.cx, c.cy]])[0]
    az = (math.degrees(math.atan2(d[0], d[1])) + 360) % 360
    assert abs(az - c.azimut) < 1e-9
    elevation = math.degrees(math.atan2(d[2], math.hypot(d[0], d[1])))
    assert abs(elevation - c.tangage) < 1e-9


# ---------------------------------------------------------------------------
# V2.4 - tests de mutation
# ---------------------------------------------------------------------------
TESTS_SENSIBLES = [
    test_opencv_meme_projection,
    test_axe_de_visee_au_centre,
    test_sens_horaire_vers_la_droite,
    test_plus_haut_donne_v_plus_petit,
    test_tangage_positif_descend_l_horizon,
    test_roulis_fait_tourner_l_image,
    lambda: test_pente_de_l_horizon_egale_moins_tangente_du_roulis(4.0),
    test_est_et_nord_ne_sont_pas_interchangeables,
    test_champ_et_focale,
    test_aller_retour_projection_rayon,
    test_rayon_du_centre_suit_l_azimut,
]


@pytest.mark.parametrize("mutation", [m for m in MUTATIONS if m != "aucune"])
def test_mutation_detectee(mutation, monkeypatch):
    """Chaque convention cassee doit faire echouer au moins un test.

    On remplace la fabrique de camera par une version mutante et on rejoue la
    batterie : si tout passe encore, c'est que rien ne protege cette convention.
    """
    import test_geometrie as mod
    monkeypatch.setattr(mod, "cam", lambda mutation=mutation, **kw: Camera(
        **{**CFG, **kw}, mutation=mutation))
    echecs = []
    for t in TESTS_SENSIBLES:
        nom = getattr(t, "__name__", "test")
        try:
            t()
        except AssertionError:
            echecs.append(nom)
        except Exception as e:          # une mutation peut aussi lever
            echecs.append(f"{nom} ({type(e).__name__})")
    assert echecs, f"la mutation {mutation!r} n'est detectee par aucun test"


# ---------------------------------------------------------------------------
# V2.5 - focale d'une photo rognee
# ---------------------------------------------------------------------------
def test_photo_native_non_rognee():
    f_px, cote, rognee = focale_px_depuis_exif(3024, 4032, 26.0)
    assert not rognee
    assert cote.startswith("largeur")
    assert abs(f_px - 3024 / 24.0 * 26.0) < 1e-9


def test_photo_rognee_9_16_detectee():
    """IMG_6941 : 2268x4032 = 9:16, rognee par rapport au 3:4 natif."""
    f_px, cote, rognee = focale_px_depuis_exif(2268, 4032, 26.0)
    assert rognee, "le rognage 9:16 doit etre detecte"
    assert f_px > 2268 / 24.0 * 26.0, "la focale corrigee doit etre plus grande"
    assert abs(f_px - 4032 / 36.0 * 26.0) < 1e-9


# ---------------------------------------------------------------------------
# V2.6 - parite avec le JavaScript du HTML
# ---------------------------------------------------------------------------
def test_js_du_html_inchange_depuis_la_comparaison():
    """Le modele JS a ete compare numeriquement a camera.py (ecart 4e-12 px).

    Node.js n'etant pas installe, la comparaison se fait dans le navigateur.
    Ce test verrouille la source de makeCam : si elle change, il faut rejouer
    `python parite_js.py` (mode d'emploi dans le fichier).
    """
    import json

    import parite_js
    ref_path = HERE / "parite_js.json"
    if not (HERE / "photomontage.html").exists():
        pytest.skip("photomontage.html absent : lancer proto_photomontage.py")
    if not ref_path.exists():
        pytest.skip("parite jamais verrouillee : voir parite_js.py")
    ref = json.loads(ref_path.read_text(encoding="utf-8"))
    assert parite_js.empreinte_js() == ref["empreinte_makeCam"], (
        "makeCam a change depuis la derniere comparaison JS/Python "
        f"(verifiee le {ref['verifie_le']}) : rejouer python parite_js.py")


def test_solveur_js_du_gabarit_inchange():
    """Le solveur JS de l'outil de calage a ete compare au solveur Python.

    Sur des donnees identiques, les deux convergent au meme minimum : ecart
    maximal 0,0002 m sur la position, 1e-6 deg sur les angles, 0,0004 px sur
    la focale. Toute modification du modele ou du solveur doit relancer cette
    comparaison.
    """
    import json

    import parite_js
    ref_path = HERE / "parite_gabarit.json"
    if not parite_js.GABARIT.exists():
        pytest.skip("gabarit_vue.html absent")
    if not ref_path.exists():
        pytest.skip("parite du gabarit jamais verrouillee")
    ref = json.loads(ref_path.read_text(encoding="utf-8"))
    assert parite_js.empreinte_gabarit() == ref["empreinte"], (
        "le modele ou le solveur du gabarit a change depuis la comparaison "
        f"du {ref['verifie_le']} : rejouer la comparaison JS/Python")


# ---------------------------------------------------------------------------
# V4 - solveur de pose
# ---------------------------------------------------------------------------
IMG = dict(largeur=4080, hauteur=3060)
POSE = {"est": 622900.0, "nord": 6750500.0, "hauteur": 1.62, "azimut": 13.8,
        "tangage": -2.5, "roulis": 1.1, "f_px": 2607.0}


def _points(n, rng, hauteurs=None, etendue=32.0):
    import solveur
    ang = np.linspace(-etendue, etendue, n) + rng.normal(0, 2.0, n)
    dist = rng.uniform(40, 380, n)
    a = np.radians(POSE["azimut"] + ang)
    h = np.zeros(n) if hauteurs is None else hauteurs
    return np.column_stack([POSE["est"] + dist * np.sin(a),
                            POSE["nord"] + dist * np.cos(a),
                            95.0 + h])


def test_v4_pose_retrouvee_points_au_sol():
    """Points au sol, focale fixee : la pose doit revenir a quelques centimetres."""
    import solveur
    rng = np.random.default_rng(7)
    mnt = solveur.MntPlat(95.0)
    p = np.array([POSE[k] for k in solveur.NOMS])
    monde = _points(8, rng)
    uv = solveur.projeter(p, monde, mnt, IMG["largeur"], IMG["hauteur"])
    assert np.isfinite(uv).all()
    depart = dict(POSE, est=POSE["est"] + 7, nord=POSE["nord"] - 6,
                  azimut=POSE["azimut"] + 17, tangage=0.0, roulis=0.0, hauteur=1.60)
    r = solveur.resoudre(monde, uv, depart, mnt, IMG["largeur"], IMG["hauteur"], sigma_px=1.0)
    assert r["rms_px"] < 0.05, f"RMS {r['rms_px']:.3f} px sur des donnees sans bruit"
    assert math.hypot(r["pose"]["est"] - POSE["est"], r["pose"]["nord"] - POSE["nord"]) < 0.2
    for k in ("azimut", "tangage", "roulis"):
        assert abs(r["pose"][k] - POSE[k]) < 0.05, f"{k} : {r['pose'][k]:.3f}"


def test_v4_robuste_au_bruit():
    """Avec 2 px de bruit et 10 points, la position reste a moins de 3 m."""
    import solveur
    rng = np.random.default_rng(11)
    mnt = solveur.MntPlat(95.0)
    p = np.array([POSE[k] for k in solveur.NOMS])
    reussites = 0
    for _ in range(10):
        monde = _points(10, rng)
        uv = solveur.projeter(p, monde, mnt, IMG["largeur"], IMG["hauteur"])
        if not np.isfinite(uv).all():
            continue
        uv = uv + rng.normal(0, 2.0, uv.shape)
        depart = dict(POSE, est=POSE["est"] + rng.uniform(-8, 8),
                      nord=POSE["nord"] + rng.uniform(-8, 8),
                      azimut=POSE["azimut"] + rng.uniform(-20, 20),
                      tangage=0.0, roulis=0.0, hauteur=1.60)
        r = solveur.resoudre(monde, uv, depart, mnt, IMG["largeur"], IMG["hauteur"], sigma_px=2.0)
        if (math.hypot(r["pose"]["est"] - POSE["est"], r["pose"]["nord"] - POSE["nord"]) < 3.0
                and abs(r["pose"]["azimut"] - POSE["azimut"]) < 1.0):
            reussites += 1
    assert reussites >= 9, f"{reussites}/10 seulement"


def test_v4_focale_libre_refusee_si_tout_au_sol():
    """Garde-fou : points coplanaires, la focale ne se separe pas du tangage."""
    import solveur
    rng = np.random.default_rng(3)
    mnt = solveur.MntPlat(95.0)
    monde = _points(8, rng)
    uv = solveur.projeter(np.array([POSE[k] for k in solveur.NOMS]), monde, mnt,
                          IMG["largeur"], IMG["hauteur"])
    with pytest.raises(ValueError, match="au sol"):
        solveur.resoudre(monde, uv, POSE, mnt, IMG["largeur"], IMG["hauteur"],
                         libre=tuple(solveur.NOMS))


def test_v4_focale_retrouvee_avec_points_en_hauteur():
    """Avec des points eleves, la focale se retrouve a mieux que 1 %."""
    import solveur
    rng = np.random.default_rng(5)
    mnt = solveur.MntPlat(95.0)
    h = np.where(np.arange(10) % 2 == 0, rng.uniform(4, 12, 10), 0.0)
    monde = _points(10, rng, hauteurs=h)
    uv = solveur.projeter(np.array([POSE[k] for k in solveur.NOMS]), monde, mnt,
                          IMG["largeur"], IMG["hauteur"]) + rng.normal(0, 1.5, (10, 2))
    depart = dict(POSE, f_px=POSE["f_px"] * 0.88, tangage=0.0, roulis=0.0, hauteur=1.60)
    r = solveur.resoudre(monde, uv, depart, mnt, IMG["largeur"], IMG["hauteur"],
                         libre=tuple(solveur.NOMS), sigma_px=1.5)
    assert abs(r["pose"]["f_px"] - POSE["f_px"]) / POSE["f_px"] < 0.01


def test_v4_refus_si_pas_assez_de_points():
    import solveur
    rng = np.random.default_rng(2)
    mnt = solveur.MntPlat(95.0)
    monde = _points(2, rng)
    uv = solveur.projeter(np.array([POSE[k] for k in solveur.NOMS]), monde, mnt,
                          IMG["largeur"], IMG["hauteur"])
    with pytest.raises(ValueError, match="insuffisantes"):
        solveur.resoudre(monde, uv, POSE, mnt, IMG["largeur"], IMG["hauteur"])


# ---------------------------------------------------------------------------
# V3 - re-audit de IMG_6941 sur des reperes mesures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def photo():
    pytest.importorskip("PIL")
    import audit_sarnois
    if not audit_sarnois.PHOTO.exists():
        pytest.skip("IMG_6941.jpeg absente")
    return audit_sarnois, audit_sarnois._charger()


def test_v3_fut_eolienne_vertical_dans_l_image(photo):
    """Le fut de l'eolienne gauche est vertical a 0,2 deg pres : le roulis est nul.

    Piege verrouille ici : mesurer le fut par le maximum de contraste attrape
    une pale et donne +2,6 deg. Il faut cibler la bande sombre.
    """
    audit, im = photo
    tilt, sig, _, res, n = audit.mesurer_fut(im, **audit.FENETRE_FUT_GAUCHE)
    assert n > 50, f"{n} lignes exploitables seulement"
    assert res < 1.0, f"residu {res:.2f} px : la mesure suit autre chose que le fut"
    assert abs(tilt) < 0.2, f"inclinaison du fut {tilt:+.2f} deg"


def test_v3_ligne_arbres_presque_horizontale(photo):
    """Mesure independante du roulis par une horizontale lointaine."""
    audit, im = photo
    roulis, res, n = audit.mesurer_ligne_arbres(im)
    assert n > 80
    assert abs(roulis) < 1.0, f"roulis deduit de la ligne d'arbres {roulis:+.2f} deg"


def test_v3_regle_exif_naive_exclue(photo):
    """La focale EXIF appliquee a la largeur rognee est incompatible avec les mats."""
    audit, im = photo
    H, W = im.shape
    tilt, sig, u_gauche, res, n = audit.mesurer_fut(im, **audit.FENETRE_FUT_GAUCHE)
    obs = np.array([u_gauche, 2061.0])
    ecarts = {}
    for f in (2457.0, 2912.0, 3166.0):
        from scipy.optimize import least_squares
        r = least_squares(lambda p: audit.u_predit(p[0], f, -8.5, 0.0, W, H) - obs,
                          [336.5], bounds=([320], [350]))
        ecarts[f] = float(np.abs(r.fun).max())
    assert ecarts[2457.0] > 20.0, "la regle naive devrait etre franchement exclue"
    assert ecarts[2912.0] < 12.0
    assert ecarts[3166.0] < 6.0


# ---------------------------------------------------------------------------
# V1 - extraction DXF
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def dxf():
    ezdxf = pytest.importorskip("ezdxf")
    if not DXF_PATH.exists():
        pytest.skip(f"DXF absent : {DXF_PATH}")
    import proto_photomontage as proto
    doc = ezdxf.readfile(DXF_PATH)
    msp = doc.modelspace()
    tables = proto.extraire_tables(msp)
    topo = proto.extraire_topo(msp)
    return proto, msp, tables, topo


def test_dxf_85_tables(dxf):
    _, _, tables, _ = dxf
    assert len(tables) == 85


def test_dxf_dimensions_tables(dxf):
    """Largeur suivant la pente, denivele et inclinaison des 85 tables."""
    _, _, tables, _ = dxf
    q = np.array([t["q"] for t in tables])
    largeur = np.linalg.norm(q[:, 3] - q[:, 0], axis=1)
    dz = q[:, 0, 2] - q[:, 3, 2]
    tilt = np.degrees(np.arcsin(dz / largeur))
    assert abs(largeur.mean() - 4.784) < 0.01, f"largeur {largeur.mean():.3f} m"
    assert largeur.std() < 0.01
    assert abs(dz.mean() - 2.022) < 0.01, f"denivele {dz.mean():.3f} m"
    assert abs(tilt.mean() - 25.0) < 0.1, f"inclinaison {tilt.mean():.2f} deg"
    assert tilt.std() < 0.1


def test_dxf_ordre_des_sommets(dxf):
    """Sommets : haut, haut, bas, bas. Les deux premiers sont les plus hauts."""
    _, _, tables, _ = dxf
    q = np.array([t["q"] for t in tables])
    assert (q[:, :2, 2].min(axis=1) > q[:, 2:, 2].max(axis=1)).all()


def test_dxf_normale_vers_le_sud(dxf):
    """Les modules regardent le secteur SE-S-SO (hypothese de l'outil)."""
    _, _, tables, _ = dxf
    q = np.array([t["q"] for t in tables])
    n = np.cross(q[:, 3] - q[:, 0], q[:, 1] - q[:, 0])
    n[n[:, 2] < 0] *= -1
    az = (np.degrees(np.arctan2(n[:, 0], n[:, 1])) + 360) % 360
    assert 112.5 <= az.mean() <= 247.5, f"azimut modules {az.mean():.1f} deg"


def test_dxf_point_bas_mesure_par_rapport_au_sol(dxf):
    """Les coins bas de CE DXF sont deja a 1,50 m du sol : ne pas rajouter 1,50 m.

    C'est l'erreur du brief, corrigee le 14/09/2026. Le test verrouille la
    mesure pour qu'un changement d'export PVcase soit detecte.
    """
    _, _, tables, topo = dxf
    low = np.array([t["q"][2:] for t in tables], dtype=float).reshape(-1, 3)
    d2 = ((low[:, None, :2] - topo[None, :, :2]) ** 2).sum(axis=-1)
    idx = np.argsort(d2, axis=1)[:, :3]
    w = 1.0 / np.sqrt(np.take_along_axis(d2, idx, 1) + 1e-6)
    z_sol = (topo[idx, 2] * w).sum(axis=1) / w.sum(axis=1)
    res = low[:, 2] - z_sol
    assert abs(res.mean() - 1.50) < 0.05, f"point bas mesure {res.mean():.3f} m"
    assert res.std() < 0.05, f"dispersion {res.std():.3f} m"


def test_dxf_rehausse_nulle_sur_ce_fichier(dxf):
    """rehausser_point_bas() ne doit rien ajouter a ce DXF."""
    proto, _, tables, topo = dxf
    dz = proto.rehausser_point_bas([dict(t) for t in tables], topo)
    assert abs(dz) < 0.05, f"rehausse appliquee {dz:+.3f} m"


def test_dxf_pas_entre_rangees(dxf):
    """15 rangees espacees de 10,33 m.

    Piege : il faut projeter TOUS les centroides sur UNE SEULE direction (la
    normale moyenne). Projeter chaque table sur sa propre normale donne des
    scalaires non comparables et un resultat absurde.
    """
    _, _, tables, _ = dxf
    q = np.array([t["q"] for t in tables])
    cen = q.mean(axis=1)
    n = np.cross(q[:, 3] - q[:, 0], q[:, 1] - q[:, 0])
    n[n[:, 2] < 0] *= -1
    nh = n[:, :2] / np.linalg.norm(n[:, :2], axis=1, keepdims=True)
    u = nh.mean(axis=0)
    u /= np.linalg.norm(u)
    proj = np.sort((cen[:, :2] * u).sum(axis=1))
    rangees, cur = [], [proj[0]]
    for v in proj[1:]:
        if v - cur[-1] < 2.0:
            cur.append(v)
        else:
            rangees.append(float(np.mean(cur)))
            cur = [v]
    rangees.append(float(np.mean(cur)))
    assert len(rangees) == 15, f"{len(rangees)} rangees detectees"
    gaps = np.diff(rangees)
    courants = gaps[gaps < 11.0]
    assert len(courants) >= 10
    assert abs(np.median(courants) - 10.33) < 0.1, f"pas median {np.median(courants):.2f} m"
    assert courants.std() < 0.05, "le pas courant doit etre regulier"


def test_dxf_cloture_et_topo(dxf):
    proto, msp, _, topo = dxf
    cloture, haie, pistes, zones = proto.extraire_lignes(msp, topo)
    assert len(cloture) == 21
    assert len(topo) == 4044
    assert len(pistes) >= 10
    assert haie is not None and len(haie) == 14


def test_dxf_ocs_non_utilise(dxf):
    """Les coordonnees brutes des INSERT sont en OCS et absurdes : garde-fou."""
    _, msp, tables, _ = dxf
    brut = [e.dxf.insert for e in msp.query("INSERT")
            if e.dxf.layer == "PVcase PV Modules (full frames)"][0]
    assert brut.x > 1e6, "coordonnee OCS attendue hors zone L93"
    q = np.array([t["q"] for t in tables])
    assert 621000 < q[:, :, 0].min() and q[:, :, 0].max() < 623000
    assert 6953000 < q[:, :, 1].min() and q[:, :, 1].max() < 6956000

# --- V5 : parite avec Blender -------------------------------------------------

def test_parite_blender_verrouillee():
    """Le rendu 3D doit projeter comme camera.py, et le verrou doit rester valide.

    Le sandbox interdit de lancer blender.exe depuis Python, donc ce test ne
    relance pas Blender : il verifie que le resultat enregistre existe et que ni
    camera.py ni le script Blender n'ont bouge depuis. Meme role que le verrou
    d'empreinte du JavaScript.
    """
    import hashlib
    verrou = json.loads((HERE / "parite_blender.json").read_text(encoding="utf-8"))
    assert verrou["ecart_max_px"] < 0.05, "parite Blender non validee"
    for f, e in verrou["empreintes"].items():
        vu = hashlib.sha256((HERE / f).read_bytes()).hexdigest()[:16]
        assert vu == e, (
            f"{f} a change depuis la verification de parite avec Blender. "
            f"Relancer parite_blender.py (preparer / blender / comparer) puis "
            f"mettre a jour parite_blender.json.")


# --------------------------------------------------------------------------
# Contrat entre le LECTEUR DE PLAN et le RENDU
#
# Un bug reel, passe inapercu : `fiche_equipements.geometrie_equipements` a
# gagne de nouvelles cles — dont `portails`, qui est une LISTE et non un dict —
# et la boucle de `montage.peindre_sol` s'est mise a lever un TypeError. Les
# 50 tests passaient avant comme apres, parce qu'aucun ne touchait ce chemin.
#
# Plutot qu'un test de rendu complet, lent et fragile, on verrouille le
# CONTRAT : toute cle rendue par le lecteur doit etre soit dessinable, soit
# explicitement ecartee, et toute categorie de revetement doit avoir sa teinte.
# C'est exactement ce qui manquait pour attraper le bug.

def _plan_sarnois():
    pytest.importorskip("ezdxf")
    import montage as M
    if not Path(M.DXF).exists():
        pytest.skip("plan Sarnois absent")
    return M


def test_lecteur_de_plan_toutes_cles_traitees():
    """Chaque cle du lecteur est dessinee ou sciemment ignoree — jamais subie."""
    M = _plan_sarnois()
    import fiche_equipements as fe
    geo = fe.geometrie_equipements(M.DXF)
    connues = set(M.DESSINABLES) | {
        "pdl", "bess", "stockage", "refroidissement", "remise",
        "contention", "portails"}
    inconnues = set(geo) - connues
    assert not inconnues, (
        f"cles nouvelles non prevues par le rendu : {sorted(inconnues)}. "
        f"Les ajouter a montage.DESSINABLES si elles doivent etre dessinees, "
        f"ou a la liste de ce test si elles sont volontairement ignorees.")


def test_boucle_du_montage_supporte_listes_et_dicts():
    """La boucle qui alimente le montage ne doit rien lever, quelle que soit
    la forme des valeurs — c'est precisement ce qui avait casse."""
    M = _plan_sarnois()
    import fiche_equipements as fe
    geo = fe.geometrie_equipements(M.DXF)
    vus = 0
    for cle, g in geo.items():
        if cle not in M.DESSINABLES:
            continue
        for gg in (g if isinstance(g, list) else [g]):
            assert isinstance(gg, dict) and "centre" in gg and "angle" in gg, (
                f"{cle} n'a pas la forme attendue par le rendu : {type(gg)}")
            math.hypot(gg["centre"][0], gg["centre"][1])
            vus += 1
    assert vus >= 2, "le poste et la citerne au moins doivent etre dessinables"


def test_tous_les_revetements_ont_une_teinte():
    """Un calque de revetement renomme ne doit pas retomber en silence sur la
    teinte par defaut : le plan en distingue six, le rendu doit les retrouver."""
    M = _plan_sarnois()
    import lecture_dxf
    from lecture_dxf import _sans_accents
    scn = lecture_dxf.lire(M.DXF)
    orphelins = set()
    trouves = set()
    for cat in M.SOL_CATEGORIES:
        for p in scn.lignes.get(cat, []):
            lay = _sans_accents(p.get("couche", "")).lower()
            cle = next((m for m, _, _ in M.SOL_TEINTES if m in lay), None)
            (trouves if cle else orphelins).add(p.get("couche", "?"))
    assert not orphelins, (
        f"calques de revetement sans teinte dediee : {sorted(orphelins)}. "
        f"Ajouter un motif a montage.SOL_TEINTES.")
    assert len(trouves) >= 4, f"trop peu de revetements reconnus : {sorted(trouves)}"
