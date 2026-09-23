#!/usr/bin/env python3
"""Modele de camera stenope du photomontage - implementation de reference Python.

Miroir exact du JavaScript embarque dans photomontage.html. Sert de reference
testable : test_geometrie.py confronte ce modele a OpenCV (implementation
totalement independante) et verifie que le JS produit les memes nombres.

Conventions (a ne jamais changer sans faire echouer les tests) :
  Monde   : (E, N, Up) en metres, relatif au sol sous la camera.
            E = est, N = nord, Up = altitude - altitude du sol camera.
  Camera  : X a droite, Y en haut, Z vers l'avant.
  Azimut  : 0 = Nord, sens horaire (90 = Est). C'est la direction de visee.
  Tangage : positif = camera relevee vers le ciel.
  Roulis  : rotation autour de l'axe de visee.
  Image   : u vers la droite, v vers le bas, origine coin haut gauche.
            Point principal au centre de l'image.
  Focale  : f_px = largeur_image / 24 * focale_eq35, convention "cote court du
            capteur 35 mm (24 mm) = largeur de l'image". ATTENTION : cette
            convention est fausse pour une photo rognee (voir focale_px_depuis_exif).
"""
import math

import numpy as np

MUTATIONS = (
    "aucune",
    "yaw_inverse",        # sens de rotation de l'azimut inverse
    "pitch_inverse",      # signe du tangage inverse
    "roll_inverse",       # signe du roulis inverse
    "v_vers_le_haut",     # v compte vers le haut au lieu du bas
    "est_nord_permutes",  # E et N permutes en entree
    "focale_cote_long",   # f_px calcule sur 36 mm au lieu de 24 mm
)


class Camera:
    """Camera stenope. Angles en degres, longueurs en metres, image en pixels."""

    def __init__(self, largeur, hauteur, azimut, tangage=0.0, roulis=0.0,
                 focale_eq35=26.0, hauteur_oeil=1.60, mutation="aucune"):
        if mutation not in MUTATIONS:
            raise ValueError(f"mutation inconnue : {mutation!r}")
        self.W = float(largeur)
        self.H = float(hauteur)
        self.azimut = float(azimut)
        self.tangage = float(tangage)
        self.roulis = float(roulis)
        self.focale_eq35 = float(focale_eq35)
        self.h = float(hauteur_oeil)
        self.mutation = mutation

        self.cx = self.W / 2.0
        self.cy = self.H / 2.0
        cote = 36.0 if mutation == "focale_cote_long" else 24.0
        self.f_px = self.W / cote * self.focale_eq35

    # -- rotations -----------------------------------------------------------
    @property
    def R(self):
        """Matrice monde (E, N, Up) -> camera (X droite, Y haut, Z avant)."""
        a = math.radians(self.azimut)
        t = math.radians(self.tangage)
        r = math.radians(self.roulis)
        if self.mutation == "yaw_inverse":
            a = -a
        if self.mutation == "pitch_inverse":
            t = -t
        if self.mutation == "roll_inverse":
            r = -r
        sa, ca = math.sin(a), math.cos(a)
        st, ct = math.sin(t), math.cos(t)
        sr, cr = math.sin(r), math.cos(r)

        # 1. yaw autour de Up : (E, N, Up) -> (droite, haut, avant)
        R_yaw = np.array([[ca, -sa, 0.0],
                          [0.0, 0.0, 1.0],
                          [sa,  ca, 0.0]])
        # 2. tangage autour de X
        R_pitch = np.array([[1.0, 0.0, 0.0],
                            [0.0,  ct, -st],
                            [0.0,  st,  ct]])
        # 3. roulis autour de Z
        R_roll = np.array([[cr, -sr, 0.0],
                           [sr,  cr, 0.0],
                           [0.0, 0.0, 1.0]])
        return R_roll @ R_pitch @ R_yaw

    @property
    def position(self):
        """Position de l'oeil dans le repere monde (E, N, Up)."""
        return np.array([0.0, 0.0, self.h])

    # -- projection ----------------------------------------------------------
    def vers_camera(self, points):
        """Monde (N, 3) -> repere camera (N, 3)."""
        p = np.atleast_2d(np.asarray(points, dtype=float))
        if self.mutation == "est_nord_permutes":
            p = p[:, [1, 0, 2]]
        return (self.R @ (p - self.position).T).T

    def projeter(self, points, z_min=0.5):
        """Monde (N, 3) -> pixels (N, 2). NaN pour les points rejetes (Zc <= z_min)."""
        c = self.vers_camera(points)
        Zc = c[:, 2]
        with np.errstate(divide="ignore", invalid="ignore"):
            u = self.cx + self.f_px * c[:, 0] / Zc
            signe = 1.0 if self.mutation == "v_vers_le_haut" else -1.0
            v = self.cy + signe * self.f_px * c[:, 1] / Zc
        uv = np.stack([u, v], axis=1)
        uv[Zc <= z_min] = np.nan
        return uv

    def rayon(self, uv):
        """Pixels (N, 2) -> direction monde (N, 3), non normalisee, Z camera = 1."""
        uv = np.atleast_2d(np.asarray(uv, dtype=float))
        x = (uv[:, 0] - self.cx) / self.f_px
        signe = 1.0 if self.mutation == "v_vers_le_haut" else -1.0
        y = signe * (uv[:, 1] - self.cy) / self.f_px
        z = np.ones_like(x)
        d = (self.R.T @ np.stack([x, y, z], axis=1).T).T
        if self.mutation == "est_nord_permutes":
            d = d[:, [1, 0, 2]]
        return d

    def horizon_v(self):
        """Ordonnee de l'horizon sur l'axe vertical central (px)."""
        a = math.radians(self.azimut)
        loin = 1e7
        p = [[loin * math.sin(a), loin * math.cos(a), self.h]]
        return float(self.projeter(p)[0, 1])

    def champ_deg(self):
        """Champ horizontal et vertical en degres."""
        return (2 * math.degrees(math.atan(self.W / (2 * self.f_px))),
                2 * math.degrees(math.atan(self.H / (2 * self.f_px))))

    # -- OpenCV --------------------------------------------------------------
    def opencv(self):
        """(rvec, tvec, K) pour cv2.projectPoints, sans distorsion.

        OpenCV : X droite, Y BAS, Z avant. D'ou la symetrie diag(1, -1, 1).
        """
        import cv2
        flip = np.diag([1.0, -1.0, 1.0])
        R_cv = flip @ self.R
        rvec, _ = cv2.Rodrigues(R_cv)
        tvec = (-R_cv @ self.position).reshape(3, 1)
        K = np.array([[self.f_px, 0.0, self.cx],
                      [0.0, self.f_px, self.cy],
                      [0.0, 0.0, 1.0]])
        return rvec, tvec, K

    def __repr__(self):
        return (f"Camera({self.W:.0f}x{self.H:.0f}, az={self.azimut}, "
                f"tangage={self.tangage}, roulis={self.roulis}, "
                f"f={self.focale_eq35} mm -> {self.f_px:.0f} px, h={self.h})")


def focale_px_depuis_exif(largeur_px, hauteur_px, focale_eq35, largeur_capteur_native=None,
                          hauteur_capteur_native=None):
    """f_px correcte meme si la photo a ete rognee.

    La focale equivalente 35 mm de l'EXIF se rapporte au capteur COMPLET. Si
    l'application photo a rogne l'image (GPS Map Camera passe le 3:4 natif de
    l'iPhone en 9:16), la largeur de l'image ne couvre plus 24 mm de capteur
    equivalent et la convention usuelle sous-estime la focale.

    Le cote non rogne donne la bonne echelle. On suppose ici que le rognage
    ne touche que la largeur (cas GPS Map Camera en portrait) : la hauteur
    couvre alors les 36 mm du grand cote du capteur 35 mm.

    Renvoie (f_px, cote_reference, rognee).
    """
    largeur_px = float(largeur_px)
    hauteur_px = float(hauteur_px)
    portrait = hauteur_px >= largeur_px
    ratio = min(largeur_px, hauteur_px) / max(largeur_px, hauteur_px)
    natif = 3.0 / 4.0
    rognee = abs(ratio - natif) > 0.02
    if largeur_capteur_native and hauteur_capteur_native:
        rognee = abs(ratio - min(largeur_capteur_native, hauteur_capteur_native)
                     / max(largeur_capteur_native, hauteur_capteur_native)) > 0.02
    if not rognee:
        cote_px = largeur_px if not portrait else largeur_px
        return cote_px / 24.0 * focale_eq35, "largeur (24 mm)", False
    grand = max(largeur_px, hauteur_px)
    return grand / 36.0 * focale_eq35, "hauteur non rognee (36 mm)", True
