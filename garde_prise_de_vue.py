#!/usr/bin/env python3
"""Dit si un point de vue donne un photomontage exploitable — sans rien rendre.

POURQUOI CE CONTROLE PASSE AVANT TOUS LES AUTRES
-------------------------------------------------
Le pilote de Saint-Cyr a été abandonné sans livrable, après quatre allers-retours
de correction, parce que les deux photos avaient été prises trop près : le
premier ouvrage dans le cadre y est à **2,4 m** et **9,4 m**, contre **20 m et
21 m** sur les deux vues de Sarnois qui, elles, ont été livrées. Aucun réglage
ne rattrape cela — à 2,4 m une clôture de 2 m couvre 75 % de la hauteur d'image.
Ce n'est plus une insertion paysagère, c'est une vue de détail d'ouvrage.

Le contrôle ne coûte rien — pas de rendu, pas même de photo si l'on a la
géolocalisation — et il se fait donc **avant** le calage, avant le masque,
avant Blender.

CE QUI COMPTE EST DANS LE CADRE, PAS AUTOUR
--------------------------------------------
Première version de ce module : elle mesurait la distance à l'ouvrage le plus
proche **du point de vue**, et recalait Sarnois, qui a pourtant été livré. Une
piste ou une clôture peut passer à dix mètres du photographe dans son dos : elle
ne gêne rien. Ce qui décide est le premier ouvrage **visible**.

    vue                 d au plus proche      dans le cadre
    Sarnois PV9               3,0 m              21,4 m       livré
    Sarnois PV10              3,7 m              20,0 m       livré
    Saint-Cyr PV3             3,1 m               9,4 m       abandonné
    Saint-Cyr PV4             2,4 m               2,4 m       abandonné

La première colonne ne classe rien — les quatre points de vue sont au bord d'un
chemin, donc à trois mètres d'une clôture ou d'une piste. Seule la seconde
sépare.

LES TROIS CRITERES, ET LEURS SEUILS
------------------------------------
Les seuils ne sont pas choisis a priori : ils sont calés sur ces quatre cas,
deux livrés et deux abandonnés, et placés là où l'écart est le plus large.

**1. La position doit être déterminée.** La base d'un ouvrage à la distance *d*
se projette en `horizon + f·h/d` : une erreur de position δ la déplace de
`f·h·δ/d²` pixels, en *carré inverse* de la distance. Avec un GPS de téléphone
à ±7 m : 2,3 et 2,6 % de la hauteur d'image sur Sarnois, **13,6 et 191,7 %**
sur Saint-Cyr. Le seuil est à 5 %, soit un facteur 2 de marge de part et
d'autre.

⚠️ CE CRITERE DEPEND DE CE QU'ON FERA ENSUITE, et je l'ai d'abord applique a
tort. L'incertitude du GPS n'est pas irreductible : le CALAGE par points
cliques a precisement pour objet de la reduire, et il ramene la position a
l'ordre du demi-metre. Juger une vue sur le GPS brut revient donc a la
condamner pour un defaut que l'etape suivante corrige. Mesure sur les vues
retenues de Sarnois : la vue 1 passe de 17 % a 1,2 %, la vue 6 de 11 % a
0,8 %. On passe donc `sigma=SIGMA_RELEVE` des lors qu'un calage est prevu —
ce qui est le cas dans la chaine — et `SIGMA_TELEPHONE` seulement pour trier
des positions avant d'aller sur le terrain, quand aucun calage n'est encore
possible.

**2. L'ouvrage le plus proche ne doit pas faire le premier plan.** Une clôture
de 2 m y couvre 8,6 et 9,2 % de la hauteur d'image sur Sarnois, **18,8 et
75,3 %** sur Saint-Cyr. Seuil à 12 %.

**3. Le projet doit rester lisible.** Au-delà de quelques centaines de mètres
une table de 3 m ne fait plus que quelques pixels. Seuil à 1 % ; les quatre cas
le passent, c'est le garde-fou de l'autre bout.

CE QUI N'EST PAS UN DEFAUT, ET QUE J'AI FAILLI COMPTER COMME TEL
-----------------------------------------------------------------
Que le projet ne tienne pas entier dans le cadre. Sarnois PV10 n'en montre que
25 % et a été livré : une centrale de quatre hectares vue de son bord couvre
350 degrés, et c'est bien pour cela qu'un dossier porte plusieurs vues. La
mesure est donnée pour information, elle ne recale rien.

Usage :
    python garde_prise_de_vue.py plan.dxf photo.jpg
    python garde_prise_de_vue.py plan.dxf --est 622879 --nord 6750697 --f35 23
"""
import argparse
import math
from dataclasses import dataclass, field

import numpy as np

import lecture_dxf
import montage as M

#: Incertitude de position, en metres, selon l'origine de la geolocalisation.
SIGMA_TELEPHONE = 7.0
SIGMA_RELEVE = 0.5

#: Deplacement induit par l'incertitude, en fraction de la hauteur d'image,
#: au-dela duquel la pose n'est plus determinee.
#: Mesure : 2,3 et 2,6 % sur les vues livrees, 12 et 61 % sur les abandonnees.
FLOU_MAX = 0.05

#: Part de la hauteur d'image que l'ouvrage proche ne doit pas depasser EN
#: MEDIANE sur la largeur du cadre. Mesure : 8,6 et 9,2 % livrees, 18,8 et
#: 75,3 % abandonnees.
PART_PROCHE_MAX = 0.12

#: Pas, en degres, du decoupage en colonnes pour cette mediane.
PAS_COLONNE = 1.0

#: Part de la hauteur d'image en deca de laquelle le projet n'est plus lisible.
PART_PROJET_MIN = 0.01

#: Hauteur de reference d'une table, en metres, pour juger de la lisibilite.
HAUTEUR_TABLE = 3.0


@dataclass
class Verdict:
    """Ce que le contrôle a trouvé. `exploitable` résume, `motifs` explique."""
    exploitable: bool
    motifs: list = field(default_factory=list)
    reserves: list = field(default_factory=list)
    mesures: dict = field(default_factory=dict)
    bande: tuple = (0.0, 0.0)
    #: False quand le cap n'a pas ete fourni : le verdict porte alors sur la
    #: POSITION, pas sur ce que la photo montre reellement.
    cap_connu: bool = True

    def texte(self):
        quoi = "point de vue" if self.cap_connu else "POSITION (cap inconnu)"
        lignes = [f"{quoi} {'EXPLOITABLE' if self.exploitable else 'A REPRENDRE'}"]
        lignes += [f"  x {m}" for m in self.motifs]
        lignes += [f"  ! {r}" for r in self.reserves]
        lignes.append(f"  distance recommandee au premier ouvrage visible : "
                      f"{self.bande[0]:.0f} a {self.bande[1]:.0f} m")
        return "\n".join(lignes)


#: Pas d'echantillonnage le long des polylignes, en metres.
PAS_ECHANTILLON = 1.0


def points_projet(scn, pas=PAS_ECHANTILLON, hautes_seulement=False):
    """Points du projet, en Lambert 93, POLYLIGNES DENSIFIEES.

    ⚠️ NE PAS SE CONTENTER DES SOMMETS. Une cloture de trois cents metres peut
    n'avoir que quatre sommets ; le brin qui passe a quatre metres de
    l'objectif a alors ses deux extremites a cent metres, et « l'ouvrage le
    plus proche » ressort a cent metres au lieu de quatre. C'est la meme erreur
    que la ligne de garde calculee sur les sommets, que le README documente
    deja : un trace se juge sur sa longueur, pas sur ses points d'inflexion.
    """
    pts = [(float(p[0]), float(p[1])) for t in scn.tables for p in t.q]
    cats = (CATEGORIES_HAUTES if hautes_seulement else tuple(scn.lignes))
    for cat in cats:
        for o in scn.lignes.get(cat, []):
            a = np.asarray([(float(x), float(y)) for x, y in o["pts"]], float)
            if len(a) < 2:
                pts += [tuple(p) for p in a]
                continue
            for i in range(len(a) - 1):
                L = float(np.hypot(*(a[i + 1] - a[i])))
                n = max(1, int(math.ceil(L / pas)))
                t = np.linspace(0.0, 1.0, n + 1)[:, None]
                pts += [tuple(p) for p in a[i] + t * (a[i + 1] - a[i])]
    return np.asarray(pts, float) if pts else np.zeros((0, 2))


#: Categories qui S'ELEVENT au-dessus du sol, et masquent donc la vue.
#:
#: ⚠️ UNE PISTE N'EST PAS UN OBSTACLE, et l'oublier donne des absurdites. Les
#: photographes se tiennent sur les chemins, et ces chemins sont dessines au
#: plan : sur la vue 10 de Sarnois, le « premier ouvrage » ressortait a 0,0 m
#: — la piste sous les pieds de l'operateur. Le critere de premier plan porte
#: sur ce qui a une HAUTEUR : cloture, portail, poste, local, citerne, haie,
#: et les tables elles-memes.
CATEGORIES_HAUTES = ("cloture", "portail", "pdl", "local", "sdis", "haie")


def _segments(scn):
    """Segments du projet qui s'elevent : traces hauts et cotes de table."""
    seg = []
    for t in scn.tables:
        q = [(float(p[0]), float(p[1])) for p in t.q]
        seg += [(q[i], q[(i + 1) % len(q)]) for i in range(len(q))]
    for cat in CATEGORIES_HAUTES:
        for o in scn.lignes.get(cat, []):
            a = [(float(x), float(y)) for x, y in o["pts"]]
            seg += [(a[i], a[i + 1]) for i in range(len(a) - 1)]
    return seg


def profil_distance(scn, est, nord, vise, champ_h, pas=1.0):
    """Distance du projet le plus proche, colonne par colonne, en degres.

    ⚠️ LA DENSIFICATION SE FAIT EN ANGLE, PAS EN LONGUEUR. Echantillonner un
    trace tous les metres donne une resolution angulaire qui s'effondre de
    pres : a deux metres de l'oeil, un metre de cloture couvre vingt degres,
    et des colonnes entieres du cadre n'ont alors aucun point — le profil y
    remonte au fond du site et annonce un premier plan degage la ou il y a une
    barriere. On subdivise donc chaque segment jusqu'a ce qu'il tienne dans une
    demi-colonne.

    Rend (centres des colonnes en degres depuis l'axe, distance minimale).
    """
    n_col = max(1, int(round(champ_h / pas)))
    bornes = np.linspace(-champ_h / 2, champ_h / 2, n_col + 1)
    dmin = np.full(n_col, np.inf)

    def deposer(p):
        e = (math.degrees(math.atan2(p[0], p[1])) - vise + 180) % 360 - 180
        i = int(np.searchsorted(bornes, e)) - 1
        if 0 <= i < n_col:
            dmin[i] = min(dmin[i], float(np.hypot(*p)))
        return e

    for (ax, ay), (bx, by) in _segments(scn):
        pile = [(np.array([ax - est, ay - nord]), np.array([bx - est, by - nord]))]
        tours = 0
        while pile and tours < 20000:
            tours += 1
            p, q = pile.pop()
            ep, eq = deposer(p), deposer(q)
            # Hors cadre des deux cotes ET du meme cote : rien a y chercher.
            if abs(ep) > champ_h and abs(eq) > champ_h and ep * eq > 0:
                continue
            if abs(ep - eq) > pas / 2 and np.hypot(*(q - p)) > 1e-3:
                m = (p + q) / 2
                pile += [(p, m), (m, q)]
    return (bornes[:-1] + bornes[1:]) / 2, dmin


def points_tables(scn):
    """Les seuls sommets de tables, pour juger de la lisibilite."""
    return np.asarray([(float(p[0]), float(p[1]))
                       for t in scn.tables for p in t.q], float)


def _emprise_angulaire(az):
    """Ouverture angulaire minimale contenant tous les azimuts, en degres.

    Un simple max - min se trompe dès que le projet enjambe le nord : des
    azimuts de 350 et 10 degrés donneraient 340 au lieu de 20. On cherche donc
    le plus grand TROU entre deux azimuts consécutifs, et l'emprise est son
    complément.
    """
    if len(az) < 2:
        return 0.0
    a = np.sort(np.asarray(az, float) % 360.0)
    trous = np.diff(np.append(a, a[0] + 360.0))
    return float(360.0 - trous.max())


def _meilleure_visee(az, champ_h, pas=2.0):
    """Azimut qui met le plus de points du projet dans le cadre.

    Sert quand la photo ne donne pas son cap : le verdict porte alors sur ce
    que le point de vue permet AU MIEUX, ce qui est la bonne question quand on
    choisit où aller avant de s'y rendre.
    """
    caps = np.arange(0.0, 360.0, pas)
    ecart = np.abs((az[None, :] - caps[:, None] + 180) % 360 - 180)
    dedans = (ecart < champ_h / 2).sum(axis=1)
    return float(caps[int(np.argmax(dedans))])


def bande_recommandee(f_px, hauteur_img, hauteur_oeil, sigma):
    """Intervalle de distance où les trois critères tiennent, en mètres."""
    d_flou = math.sqrt(f_px * hauteur_oeil * sigma / (FLOU_MAX * hauteur_img))
    d_proche = f_px * M.HAUTEUR_CLOTURE / (PART_PROCHE_MAX * hauteur_img)
    d_loin = f_px * HAUTEUR_TABLE / (PART_PROJET_MIN * hauteur_img)
    return max(d_flou, d_proche), d_loin


def evaluer(scn, est, nord, largeur, hauteur, f_px, azimut=None,
            hauteur_oeil=1.60, sigma=SIGMA_TELEPHONE):
    """Juge un point de vue. Rend un `Verdict`.

    `azimut` est facultatif. Sans lui, le contrôle prend la visée qui montre le
    plus de projet et le dit : le verdict porte alors sur ce que le point de
    vue permet au mieux.
    """
    pts = points_projet(scn, hautes_seulement=True)
    if not len(pts):
        raise ValueError("le plan ne porte aucun point exploitable")

    d = np.hypot(pts[:, 0] - est, pts[:, 1] - nord)
    az = np.degrees(np.arctan2(pts[:, 0] - est, pts[:, 1] - nord)) % 360.0
    champ_h = 2 * math.degrees(math.atan(largeur / (2 * f_px)))

    vise = azimut if azimut is not None else _meilleure_visee(az, champ_h)
    ecart = (az - vise + 180) % 360 - 180
    dans = np.abs(ecart) < champ_h / 2
    if not dans.any():
        return Verdict(False, [f"aucun point du projet dans le cadre a "
                               f"l'azimut {vise:.0f} deg."],
                       mesures={"champ_horizontal_deg": champ_h},
                       bande=bande_recommandee(f_px, hauteur, hauteur_oeil,
                                               sigma),
                       cap_connu=azimut is not None)

    d_proche = float(d[dans].min())
    d_median = float(np.median(d[dans]))
    # COLONNE PAR COLONNE, ET EN MEDIANE — parce qu'une cloture qui FUIT n'est
    # pas une cloture EN TRAVERS. Juger sur le seul point le plus proche
    # confond les deux : un chemin qui longe l'emprise met un brin de cloture
    # a trois metres au bord du cadre, et la barre de fer y couvre la moitie
    # de l'image, alors que sur toute la largeur elle file vers l'horizon et
    # conduit l'oeil dans le projet. Mesure sur la vue 22 de Sarnois :
    # cloture a 3,9 m, hauteur apparente MAXIMALE 10,0 %, MEDIANE 7,9 %.
    # A l'inverse, la vue 3 donne 49,4 % au maximum et 12,3 % en mediane :
    # la mediane, elle, separe les deux cas.
    _c, dcol = profil_distance(scn, est, nord, vise, champ_h, PAS_COLONNE)
    dcol = dcol[np.isfinite(dcol)]
    if not len(dcol):
        dcol = np.array([d_proche])
    hauteurs = f_px * M.HAUTEUR_CLOTURE / dcol / hauteur
    part_proche = float(np.median(hauteurs))
    part_proche_max = float(hauteurs.max())
    d_proche = float(min(d_proche, dcol.min()))
    flou = f_px * hauteur_oeil * sigma / d_proche ** 2

    # LA LISIBILITE SE JUGE SUR LA TABLE VISIBLE LA PLUS PROCHE, et non sur la
    # distance mediane du projet. Des que le cadre coupe les rangees proches —
    # ce qui arrive sur toute vue rapprochee — la mediane bascule vers le fond
    # du site et annonce un projet illisible alors que sa premiere rangee
    # occupe le cadre. Mesure : mediane 306 m contre 35 m pour la premiere
    # table, sur une vue ou l'on voit parfaitement les modules.
    tb = points_tables(scn)
    d_lisible = d_median
    if len(tb):
        dt = np.hypot(tb[:, 0] - est, tb[:, 1] - nord)
        azt = np.degrees(np.arctan2(tb[:, 0] - est, tb[:, 1] - nord)) % 360.0
        vt = np.abs((azt - vise + 180) % 360 - 180) < champ_h / 2
        if vt.any():
            d_lisible = float(dt[vt].min())
    part_projet = f_px * HAUTEUR_TABLE / d_lisible / hauteur

    mesures = {
        "azimut_evalue_deg": vise,
        "distance_premier_ouvrage_visible_m": d_proche,
        "distance_mediane_projet_visible_m": d_median,
        "distance_premiere_table_visible_m": d_lisible,
        "distance_max_projet_visible_m": float(d[dans].max()),
        "flou_position_px": flou,
        "flou_position_pct_hauteur": 100 * flou / hauteur,
        # CE QUE LE CALAGE RAMENERA, pour que l'ecart entre les deux se voie.
        "flou_apres_calage_pct_hauteur":
            100 * f_px * hauteur_oeil * SIGMA_RELEVE / d_proche ** 2 / hauteur,
        "part_ouvrage_proche_pct": 100 * part_proche,
        "part_ouvrage_proche_max_pct": 100 * part_proche_max,
        "part_projet_pct": 100 * part_projet,
        "champ_horizontal_deg": champ_h,
        "emprise_projet_deg": _emprise_angulaire(az),
        "part_projet_dans_le_cadre_pct": 100 * float(dans.mean()),
        "sigma_position_m": sigma,
    }

    motifs, reserves = [], []
    if flou > FLOU_MAX * hauteur:
        motifs.append(
            f"position indeterminee : une incertitude de {sigma:.0f} m deplace "
            f"le premier ouvrage visible de {flou:.0f} px "
            f"({100 * flou / hauteur:.0f} % de la hauteur d'image). A "
            f"{d_proche:.1f} m, l'erreur varie en carre inverse de la distance. "
            f"Un calage la ramenerait a "
            f"{100 * f_px * hauteur_oeil * SIGMA_RELEVE / d_proche ** 2 / hauteur:.1f} %.")
    if part_proche > PART_PROCHE_MAX:
        motifs.append(
            f"vue de detail d'ouvrage : une cloture de {M.HAUTEUR_CLOTURE:.0f} m "
            f"couvre {100 * part_proche:.0f} % de la hauteur d'image en mediane "
            f"sur la largeur du cadre ({100 * part_proche_max:.0f} % au plus "
            f"fort, a {d_proche:.1f} m). Le paysage n'est plus le sujet.")
    if part_projet < PART_PROJET_MIN:
        motifs.append(
            f"projet illisible : la premiere table visible est a "
            f"{d_lisible:.0f} m et une table de {HAUTEUR_TABLE:.0f} m n'y "
            f"couvre que {100 * part_projet:.2f} % de la hauteur d'image.")

    if azimut is None:
        reserves.append(
            f"CE VERDICT PORTE SUR LA POSITION, PAS SUR CETTE PHOTO. Faute de "
            f"cap, il est rendu pour la meilleure visee possible ({vise:.0f} "
            f"deg) : il dit qu'on PEUT faire une bonne vue d'ici, pas que "
            f"celle-ci en est une. Mesure sur Sarnois : la vue 6 passe a ce "
            f"titre, et son cap reel — 340,7 deg, cale sur quatre mats "
            f"d'eoliennes — ne met que 12 % des tables dans le cadre.")
    if dans.mean() < 0.5:
        reserves.append(
            f"le cadre ne prend que {100 * dans.mean():.0f} % des points du "
            f"projet, qui s'etend sur {mesures['emprise_projet_deg']:.0f} deg. "
            f"Ce n'est pas un defaut — un dossier porte plusieurs vues.")

    return Verdict(not motifs, motifs, reserves, mesures,
                   bande_recommandee(f_px, hauteur, hauteur_oeil, sigma),
                   cap_connu=azimut is not None)


def depuis_photo(chemin):
    """Taille, focale et position d'une photo, depuis son EXIF."""
    import preparer_vue
    import terrain

    e = preparer_vue.exif_photo(chemin)
    if e["lon"] is None or e["lat"] is None:
        raise ValueError(f"{chemin} n'a pas de geolocalisation EXIF")
    if e["f_px"] is None:
        raise ValueError(f"{chemin} n'a pas de focale EXIF")
    est, nord = terrain._VERS_L93.transform(e["lon"], e["lat"])
    return dict(est=float(est), nord=float(nord), largeur=e["largeur"],
                hauteur=e["hauteur"], f_px=e["f_px"])


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("plan")
    p.add_argument("photo", nargs="?")
    p.add_argument("--est", type=float)
    p.add_argument("--nord", type=float)
    p.add_argument("--f35", type=float)
    p.add_argument("--largeur", type=int, default=2040)
    p.add_argument("--hauteur", type=int, default=1530)
    p.add_argument("--azimut", type=float)
    p.add_argument("--oeil", type=float, default=1.60)
    p.add_argument("--releve", action="store_true",
                   help="position relevee au GPS differentiel, non au telephone")
    a = p.parse_args()

    scn = lecture_dxf.lire(a.plan)
    if a.photo:
        d = depuis_photo(a.photo)
    else:
        import camera
        if a.est is None or a.nord is None or a.f35 is None:
            p.error("sans photo, il faut --est, --nord et --f35")
        d = dict(est=a.est, nord=a.nord, largeur=a.largeur, hauteur=a.hauteur,
                 f_px=camera.focale_px_depuis_exif(a.largeur, a.hauteur,
                                                   a.f35)[0])

    v = evaluer(scn, azimut=a.azimut, hauteur_oeil=a.oeil,
                sigma=SIGMA_RELEVE if a.releve else SIGMA_TELEPHONE, **d)
    print()
    print(v.texte())
    print()
    for k, x in v.mesures.items():
        print(f"    {k:38s} {x:9.2f}")
    return 0 if v.exploitable else 1


if __name__ == "__main__":
    raise SystemExit(main())
