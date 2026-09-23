#!/usr/bin/env python3
"""Planche de validation du masque de premier plan, AVANT tout rendu.

POURQUOI CET OUTIL EXISTE
-------------------------
Le détourage du premier plan est la seule étape du photomontage où la machine
ne tranche pas seule. Cette décision était jusqu'ici prise APRÈS coup, en
regardant le montage fini — neuf allers-retours sur seize pour les trois vues
de Gannay, à chaque fois un rendu Blender complet pour découvrir un contour
faux. Cette planche la déplace AVANT.

ELLE MONTRE LE MASQUE COMPLET, ET C'EST LA RÈGLE PREMIÈRE
---------------------------------------------------------
La première version n'affichait que le classement par couleur, en laissant de
côté la ligne de garde. Le chef de projet a donc signalé comme oubliées deux
masses qui étaient masquées à 100 % et 98 % — elles tombaient sous la ligne de
garde, et rien ne le disait. Un aller-retour perdu, et perdu par l'outil censé
les économiser.

La planche appelle donc `masque_avant_plan.masque` avec les réglages de la vue,
et teinte SON résultat. Elle ne reproduit aucun morceau du calcul : ce qui est
montré est, par construction, ce qui sera composé.

CE QUI REND LA QUESTION PETITE
------------------------------
La bande orange est l'enveloppe du projet, projetée depuis la scène sans
rendu. Le masque ne compte que là — partout ailleurs il ne recouvre aucun
ouvrage. Cette bande fait 31 à 37 px de haut sur les vues de Gannay, pour des
images de 960 : d'où le bandeau du bas, qui la reprend étirée, seule échelle
où l'on juge vraiment ce qui passe devant.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import masque_avant_plan as MA                                     # noqa: E402

#: Matériaux qui ne sont pas des ouvrages : le sol du site bouche les jeux
#: entre tables mais ne se voit pas, et l'inclure étirerait la bande jusqu'au
#: bas de l'image pour rien.
#:
#: `sol_ombre` EST LE PIÈGE. C'est le capteur d'ombre des scènes Sarnois : une
#: nappe de 260 m de rayon centrée SOUS la caméra, invisible au rendu, qui ne
#: sert qu'à recevoir les ombres portées. Comptée dans l'enveloppe, elle place
#: la base de l'ouvrage à quelques mètres de l'objectif, donc très bas dans
#: l'image — et la garde par colonne efface alors tout le bas de la centrale.
#: Mesuré sur IMG_6941 : poteaux et pieux masqués à 91 %.
HORS_OUVRAGE = ("herbe", "sol", "terre", "sol_ombre")

#: Matériaux de la mesure paysagère. Ils comptent dans la bande — une haie
#: monte plus haut que la nappe.
FEUILLAGE = ("feuillage", "feuillage_carte")

#: Hauteur conservée de part et d'autre de la bande du projet : la ZONE UTILE.
FENETRE = 70

#: Teintes de la planche. Le masque est vert, la bande du projet orange, la
#: ligne de garde rouge — trois rôles, trois couleurs, jamais mélangées.
MASQUE = (60, 255, 120)
BANDE = (255, 130, 0)
GARDE = (255, 50, 50)
MARQUE_AVANT = (60, 255, 120)
MARQUE_ARRIERE = (255, 210, 60)

#: Largeur visée de la planche, pour que les libellés restent lisibles.
LARGEUR_CIBLE = 1800

#: Étirement vertical du bandeau de détail.
ETIREMENT = 3

#: Largeur minimale, en colonnes, pour qu'une masse jugée reçoive un numéro.
#: En deçà, elle ne se voit pas à l'écran et un numéro de plus ne fait que
#: gêner la lecture.
LARGEUR_NUMEROTEE = 40


def _police(taille):
    """Une TrueType du système, ou le pis-aller bitmap de Pillow."""
    for base in ("C:/Windows/Fonts/", "/usr/share/fonts/truetype/dejavu/"):
        for nom in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
            try:
                return ImageFont.truetype(base + nom, taille)
            except OSError:
                continue
    return ImageFont.load_default()


def bande_projet(scene, W, H, avec_feuillage=True):
    """Hauteurs min et max du projet, colonne par colonne, en pixels image.

    On projette les sommets de la scène avec la caméra qu'elle porte — la même
    que Blender emploiera. C'est une enveloppe par colonne, pas une silhouette
    exacte : elle suffit à dire OÙ REGARDER, et elle ne coûte pas un rendu.
    """
    d = json.loads(Path(scene).read_text(encoding="utf-8"))
    c = d["camera"]
    R, P, f = np.array(c["R"]), np.array(c["position"]), float(c["f_px"])
    cx, cy = W / 2.0, H / 2.0
    lo, hi = np.full(W, np.inf), np.full(W, -np.inf)
    for o in d["objets"]:
        mat = o.get("materiau", "")
        if mat in HORS_OUVRAGE or (not avec_feuillage and mat in FEUILLAGE):
            continue
        if not o.get("v"):
            continue
        cam = (R @ (np.asarray(o["v"], float) - P).T).T
        Z = cam[:, 2]
        devant = Z > 0.5           # un sommet derrière la caméra ne se projette pas
        if not devant.any():
            continue
        u = cx + f * cam[devant, 0] / Z[devant]
        v = cy - f * cam[devant, 1] / Z[devant]
        dedans = (u >= 0) & (u < W)
        if not dedans.any():
            continue
        xi = u[dedans].astype(int)
        np.minimum.at(lo, xi, v[dedans])
        np.maximum.at(hi, xi, v[dedans])
    return lo, hi


def zone_utile(lo, hi, H):
    """Bande du projet élargie de `FENETRE` : la seule zone qui se juge."""
    vues = np.isfinite(lo)
    if not vues.any():
        return (0, H), vues
    return (int(max(0, np.nanmin(lo[vues]) - FENETRE)),
            int(min(H, np.nanmax(hi[vues]) + FENETRE))), vues


def planche(photo, pose, scene, sortie=None, verbose=True):
    """Écrit la planche de validation, et renvoie le masque qu'elle montre.

    Le masque vient de `masque_avant_plan.masque`, appelé avec les réglages
    que la vue déclare. La planche ne recalcule rien.
    """
    photo = Path(photo)
    a = np.array(Image.open(photo).convert("RGB"))
    H, W = a.shape[:2]
    lo, hi = bande_projet(scene, W, H)
    zone, vues = zone_utile(lo, hi, H)
    reglages = dict(pose.get("masque", {}))
    d_min = MA.distance_mini(scene)
    m = MA.masque(photo, pose, d_min, zone=zone, verbose=verbose, **reglages)
    garde = MA.ligne_de_garde(pose, d_min)

    # --- peinture : masque, puis bande, puis règle ------------------------
    # DEUX INTENSITÉS, PARCE QU'IL Y A DEUX NATURES DE MASQUE. Sous la ligne
    # de garde, c'est de la géométrie : tout y est plus près que `d_min`, il
    # n'y a rien à juger et une teinte forte n'y ferait que noyer la planche.
    # Au-dessus, c'est un jugement — couleur ou silhouette — et c'est LUI que
    # le chef de projet relit. Il ne doit donc regarder que le vert franc.
    fond = a.astype(float)
    pris = m > 0.5
    vg = int(round(garde))
    juge = pris.copy()
    juge[max(0, vg):] = False
    certain = pris & ~juge
    for c in range(3):
        fond[..., c] = np.where(certain,
                                fond[..., c] * 0.86 + MASQUE[c] * 0.14,
                                fond[..., c])
        fond[..., c] = np.where(juge,
                                fond[..., c] * 0.52 + MASQUE[c] * 0.48,
                                fond[..., c])
    for x in np.nonzero(vues)[0]:
        b0, b1 = int(max(0, lo[x])), int(min(H - 1, hi[x]))
        if b1 >= b0:
            fond[b0:b1 + 1, x] = (fond[b0:b1 + 1, x] * 0.42
                                  + np.array(BANDE, float) * 0.58)
    # LE HAUT DU MASQUE, EN BLANC. Sans ce trait, on voit bien qu'une zone est
    # verte mais pas à quelle silhouette elle s'arrête — et c'est justement la
    # question : le masque suit-il la cime du buisson proche, ou monte-t-il
    # jusqu'à la ligne d'arbres du fond ? Le trait la tranche d'un coup d'œil.
    for x in range(W):
        col = np.nonzero(pris[:, x])[0]
        if len(col) and zone[0] - 30 <= col[0] < zone[1]:
            fond[col[0]:min(col[0] + 2, H), x] = (255, 255, 255)
    if 0 <= vg < H:
        fond[vg:min(vg + 2, H), ::3] = GARDE
    peint = np.clip(fond, 0, 255).astype(np.uint8)

    im = Image.fromarray(peint)
    detail = Image.fromarray(peint[zone[0]:zone[1]])
    echelle = max(1.0, LARGEUR_CIBLE / W)
    im = im.resize((int(W * echelle), int(H * echelle)), Image.LANCZOS)
    Wp = im.width
    f, fp = (_police(int(17 * min(echelle, 1.6))),
             _police(int(13 * min(echelle, 1.6))))

    # NUMÉROTER LES MASSES JUGÉES : c'est par ces numéros que la correction se
    # dit. Seules les masses au JUGEMENT en reçoivent un — le masque
    # géométrique n'est pas discutable, le numéroter inviterait à le discuter.
    coul_pts = reglages.get("couleurs")
    # NUMÉROTER PAR PLAGES DE COLONNES, et non par composantes connexes. Sur
    # la vue 4 le masque jugé ne fait qu'un seul tenant d'un bord à l'autre :
    # une composante, donc un seul numéro pour tout, avec lequel on ne peut
    # rien dire. Or c'est en colonnes que la correction s'énonce — « la masse
    # entre 430 et 550 est derrière ». On découpe donc là où le masque cesse
    # d'occuper la bande.
    haut, bas = (int(np.nanmin(lo[vues])), int(round(garde))) if vues.any()         else (zone[0], int(round(garde)))
    occupe = (juge[max(0, haut):max(haut + 1, bas)] > 0).mean(axis=0) > 0.08
    masses, debut = [], None
    for x in range(W + 1):
        plein = x < W and occupe[x]
        if plein and debut is None:
            debut = x
        elif not plein and debut is not None:
            if x - debut >= LARGEUR_NUMEROTEE:
                cx = (debut + x) // 2
                col = np.nonzero(juge[:, cx])[0]
                masses.append((len(masses) + 1, debut, x - 1, cx,
                               int(np.median(col)) if len(col) else haut))
            debut = None

    # TROIS SYMBOLES, TROIS RÔLES, ET LA LÉGENDE DOIT LES SÉPARER. La version
    # précédente les mélangeait — numéros de masse, graines d'avant-plan et
    # graines de fond portaient tous un chiffre — et le lecteur ne pouvait pas
    # savoir lesquels attendaient une réponse de lui. Les masses sont des
    # RÉSULTATS et se tranchent ; les graines sont des ENTRÉES et se déplacent.
    lignes = [f"{photo.name}   {W} x {H} px   —   masque COMPLET, "
              f"{pris.mean() * 100:.0f} % de l'image dont "
              f"{juge.mean() * 100:.0f} % au jugement"]
    if masses:
        lignes.append(f"A RELIRE : les {len(masses)} masse(s) en VERT FRANC, "
                      f"numerotees [1] a [{len(masses)}] sur fond noir. "
                      "Repondez par ces numeros —")
        lignes.append('   "2 est derriere", "3 est un grillage a 25 %", '
                      '"il manque x 430-550", ou "rien a dire".')
    else:
        lignes.append("Aucune masse au jugement : tout le masque est "
                      "geometrique. Rien a trancher sur cette vue.")
    lignes.append("TRAIT BLANC = haut du masque : c'est la silhouette qu'il "
                  "suit. S'il colle a la cime du fond, il prend le lointain.")
    lignes.append(f"ACQUIS : vert pale = sous la ligne de garde v={garde:.0f} "
                  f"(d_min={d_min:.0f} m), tout y est plus pres que le projet.")
    if vues.any():
        lignes.append(f"ORANGE = ou le projet se projette, lignes "
                      f"{int(np.nanmin(lo[vues]))} a {int(np.nanmax(hi[vues]))}"
                      " : le masque ne compte que la.")
    if coul_pts:
        lignes.append("Ronds A = graines d'AVANT-PLAN, ronds F = graines de "
                      "FOND. Ce sont les ENTREES du classement, pas des "
                      "masses :")
        lignes.append("   une masse fausse vient presque toujours d'une "
                      "graine mal placee — dites laquelle et ou la mettre.")
    h_ligne = int(24 * min(echelle, 1.6))
    h_tete = h_ligne * len(lignes) + 14
    h_det = int(detail.height * echelle * ETIREMENT) + 34

    out = Image.new("RGB", (Wp, h_tete + im.height + h_det), (0, 0, 0))
    out.paste(im, (0, h_tete))
    out.paste(detail.resize((Wp, h_det - 34), Image.LANCZOS),
              (0, h_tete + im.height + 34))
    d = ImageDraw.Draw(out, "RGBA")
    for i, t in enumerate(lignes):
        d.text((10, 7 + i * h_ligne), t, font=f,
               fill=(255, 255, 255) if i == 0 else (215, 215, 215))

    if coul_pts:
        for nom, pts, c in (("A", coul_pts["avant"], MARQUE_AVANT),
                            ("F", coul_pts["arriere"], MARQUE_ARRIERE)):
            for i, (x, y) in enumerate(pts):
                for base, ech, dy in ((h_tete, echelle, 0),
                                      (h_tete + im.height + 34,
                                       echelle * ETIREMENT, -zone[0])):
                    cy = base + (y + dy) * ech
                    if not base <= cy < base + (im.height if dy == 0
                                                else h_det - 34):
                        continue
                    cx = x * echelle
                    # DISCRÈTES : une graine est un repère de réglage,
                    # elle ne doit pas concurrencer les numéros de masse.
                    d.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], outline=c,
                              width=2)
                    d.text((cx + 9, cy - 7), f"{nom}{i + 1}", font=fp, fill=c)

    for num, x0, x1, cx, cy in masses:
        for base, ech, dy in ((h_tete, echelle, 0),
                              (h_tete + im.height + 34, echelle * ETIREMENT,
                               -zone[0])):
            y = base + (cy + dy) * ech
            if not base <= y < base + (im.height if dy == 0 else h_det - 34):
                continue
            x = cx * echelle
            d.rectangle([x - 19, y - 17, x + 19, y + 17],
                        fill=(0, 0, 0, 215), outline=MASQUE, width=2)
            d.text((x - 8, y - 12), str(num), font=f, fill=MASQUE)

    for base, dec in ((h_tete + im.height - int(26 * echelle), 0),
                      (h_tete + im.height + 40, 0)):
        for x in range(0, W, 200):
            d.text((x * echelle + 3, base), str(x), font=fp,
                   fill=(255, 255, 255))
    if masses:
        d.text((10, h_tete + 6), "  ".join(
            f"[{num}] x {x0}-{x1}" for num, x0, x1, _, _ in masses),
            font=fp, fill=MASQUE)
    d.text((10, h_tete + im.height + 9),
           f"detail : lignes {zone[0]} a {zone[1]}, etire x{ETIREMENT}",
           font=fp, fill=(255, 180, 90))

    sortie = Path(sortie) if sortie else photo.with_name(
        f"masque_a_valider_{photo.stem}.jpg")
    out.save(sortie, quality=92)
    if verbose:
        print(f"ecrit : {sortie}")
    return m, sortie


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(__doc__)
        print("Usage : python apercu_masque.py <photo> <pose.json> "
              "<scene.json> [sortie.jpg]")
        raise SystemExit(2)
    planche(sys.argv[1],
            json.loads(Path(sys.argv[2]).read_text(encoding="utf-8")),
            sys.argv[3],
            sortie=sys.argv[4] if len(sys.argv) > 4 else None)
