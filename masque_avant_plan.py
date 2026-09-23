#!/usr/bin/env python3
"""Masque de premier plan : ce qui, sur la photo, passe DEVANT le projet.

Un photomontage compose le rendu par-dessus la photo : tout ce qui est calculé
passe devant tout ce qui est photographié. Une nappe à 200 m s'affiche donc
par-dessus la haie qui est à 20 m, et le montage se trahit aussitôt.

DEUX SOURCES, ET ELLES NE SE VALENT PAS.

1. LA LIGNE DE GARDE, qui est de la géométrie et non une estimation. Le point
   rendu le plus proche est à une distance `d_min` connue — la clôture, ici à
   107 m. Sur un terrain plat, le sol à cette distance se projette à la ligne
   `horizon + f x h_oeil / d_min`. TOUT ce qui est sous cette ligne est plus
   près que `d_min`, donc devant : la route, l'accotement, le talus. Aucun
   réglage, aucun seuil.

2. LA VÉGÉTATION DE BORD, qui est une heuristique et s'annonce comme telle.
   Un côté peut être déclaré OPAQUE (`opaques=("droite",)`) : on y prend alors
   la masse entière, trous rebouchés, au lieu du fondu par le score. C'est le
   seul jugement humain du module, et il est visible dans l'appel.
   Les masses qui encadrent le cadre — haie de gauche, buisson de droite —
   montent au-dessus de la ligne de garde. On les repère à leur couleur et à
   leur texture, et on ne garde que les amas qui TOUCHENT un bord de l'image :
   un arbre au milieu du champ, lui, peut être derrière.

LE MASQUE EST BINAIRE, ET SA LISIÈRE SEULE EST POREUSE. La nuance est
capitale. Un masque en niveaux de gris sur toute une masse compose le rendu en
semi-transparence : les panneaux deviennent translucides et l'on voit le
lointain au travers. Mais un bord net au ciseau trahit tout aussi sûrement le
montage. On pose donc 0 ou 1 sur la masse, et le flou final — quelques pixels —
fait la porosité de la lisière, qui est justement l'échelle d'un feuillage.

Usage :
    python masque_avant_plan.py photo.jpg scene.json pose.json [masque.png]
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

AIRE_MIN = 3000        # px : en deçà, ce n'est pas une masse de premier plan
ADOUCI = 1.2           # px de flou avant raidissement
RAIDEUR = 3.0          # pente de la transition ; 1 = flou pur


#: Matériaux qui ne sont pas des ouvrages et n'entrent donc pas dans `d_min`.
#: Le CAPTEUR D'OMBRE passe sous la caméra : compté, il donne une distance
#: minimale nulle, puis une division par zéro dans `ligne_de_garde`. Le sol du
#: site, lui, est bien rendu mais ne se dresse pas — il ne peut rien cacher.
HORS_DISTANCE = ("sol_ombre", "herbe", "sol", "terre")


def distance_mini(scene, hors=HORS_DISTANCE):
    """Distance horizontale de l'OUVRAGE rendu le plus proche, en mètres."""
    d = json.loads(Path(scene).read_text(encoding="utf-8"))
    dmin = math.inf
    for o in d["objets"]:
        if o.get("materiau") in hors:
            continue
        v = np.asarray(o["v"], float)
        if len(v):
            dmin = min(dmin, float(np.hypot(v[:, 0], v[:, 1]).min()))
    if not math.isfinite(dmin) or dmin <= 0.0:
        raise ValueError(
            f"distance minimale nulle ou introuvable dans {Path(scene).name} : "
            "la scene ne porte aucun ouvrage hors " + ", ".join(hors))
    return dmin


def ligne_de_garde(pose, d_min):
    """Ligne image sous laquelle tout est plus près que `d_min`."""
    return pose["horizon"] + pose["f_px"] * pose["hauteur_oeil"] / d_min


def garde_depuis_rendu(rendu, seuil_alpha=0.5, seuil_noir=12):
    """Ligne de garde par colonne, lue sur le RENDU au lieu de la géométrie.

    POURQUOI PAS LA GÉOMÉTRIE. `apercu_masque.bande_projet` projette les
    SOMMETS. Pour un ouvrage lointain, dont chaque face couvre quelques pixels,
    cela donne l'enveloppe exacte. Pour un poteau à quatre mètres, dont la face
    couvre 400 px de haut et 30 de large, c'est faux : dans les colonnes où le
    poteau n'a pas de sommet, l'enveloppe remonte au bas d'un panneau lointain.
    Mesuré sur IMG_6941 : l'ouvrage descend à v=2071 en colonne 0, l'enveloppe
    par sommets dit 1614, et le masque effaçait 457 px de clôture — 296 px en
    médiane sur 566 colonnes.

    LE RENDU, LUI, EST RASTÉRISÉ. Son pixel d'ouvrage le plus bas dans une
    colonne EST le pied de l'ouvrage dans cette colonne. On le lit donc là.

    Il faut seulement distinguer l'ouvrage de son OMBRE : le capteur d'ombre
    rend du noir pur à alpha partiel, l'ouvrage a une couleur. D'où le seuil sur
    le maximum des canaux.

    Ce n'est pas circulaire : on ne masque que ce qui est SOUS le pied de
    l'ouvrage, donc jamais l'ouvrage lui-même — seulement l'ombre portée sur un
    sol qui, à cette hauteur d'image, est devant lui.
    """
    r = np.asarray(Image.open(rendu).convert("RGBA"), dtype=float)
    ouvrage = (r[..., 3] / 255.0 > seuil_alpha) & (r[..., :3].max(axis=2) > seuil_noir)
    H, W = ouvrage.shape
    ligne = np.full(W, np.nan)
    for x in range(W):
        o = np.nonzero(ouvrage[:, x])[0]
        if len(o):
            ligne[x] = o[-1]
    return ligne


def masque_sous_rendu(rendu, adouci=1.2, **kw):
    """Masque plein sous le pied de l'ouvrage, colonne par colonne."""
    ligne = garde_depuis_rendu(rendu, **kw)
    r = Image.open(rendu)
    W, H = r.size
    m = np.zeros((H, W), float)
    for x in range(W):
        v = ligne[x]
        # Colonne sans ouvrage : tout ce que le rendu y met est de l'ombre
        # portée sur un sol qu'aucun ouvrage ne domine — donc du premier plan.
        m[0 if np.isnan(v) else int(v) + 1:, x] = 1.0
    return ndimage.gaussian_filter(m, adouci)


def garde_par_colonne(hi, adouci=2.0):
    """Ligne de garde COLONNE PAR COLONNE, tirée de la géométrie seule.

    `ligne_de_garde` prend la distance du point rendu le plus proche de TOUTE
    la scène et en tire une seule ligne horizontale. C'est le minorant global,
    et il ne vaut que si l'ouvrage est à peu près à distance constante — le cas
    d'une nappe vue de face à 120 m.

    Il ne vaut plus dès que l'ouvrage FUIT. Sur IMG_6941, la clôture part à
    3,84 m au bord gauche et s'éloigne à 245 m vers la ligne d'arbres : la
    garde globale tombe à v=2862, alors que dans les colonnes du fond le sol
    devant l'ouvrage monte jusqu'à v≈1600. Toute la bande intermédiaire — le
    blé du premier plan — restait démasquée, fils de grillage dessinés au
    travers.

    Or un ouvrage POSE SUR LE SOL : son point le plus bas dans une colonne est
    le sol à sa distance. Tout ce qui, dans cette colonne, est plus bas dans
    l'image est donc plus près que lui, et passe devant. C'est la même
    certitude géométrique que `ligne_de_garde`, rendue par colonne — et elle
    ne demande ni seuil, ni couleur, ni jugement.

    `hi` vient de `apercu_masque.bande_projet` : le bas de l'enveloppe rendue,
    colonne par colonne. Les colonnes sans ouvrage ne masquent rien.
    """
    v = np.array(hi, float)
    vus = np.isfinite(v)
    if not vus.any():
        return None
    # MAXIMUM, ET SURTOUT PAS MOYENNE. J'avais lissé par une moyenne, en
    # pensant amortir le bruit d'une maille de grillage. Mais l'enveloppe
    # ALTERNE : dans la colonne d'un poteau de clôture sa base est au sol, dans
    # la colonne d'à côté elle remonte au bas d'un panneau lointain. Une moyenne
    # remonte donc la garde dans les colonnes de poteau — et le masque y coupe
    # l'ouvrage. Mesuré sur IMG_6941, x=100 : base réelle v=1665 (pied de
    # l'acier), garde lissée 1587, soit 78 px de poteau effacés, et le bas des
    # panneaux rogné par-dessus le marché.
    #
    # Le maximum ne peut qu'ABAISSER la ligne dans l'image, donc masquer moins.
    # C'est le seul sens d'erreur acceptable : laisser voir un peu de rendu de
    # trop se corrige à l'œil, effacer l'ouvrage ne se voit pas.
    x = np.arange(len(v))
    plein = np.interp(x, x[vus], v[vus])
    return ndimage.maximum_filter1d(plein, int(max(1, adouci * 2 + 1))), vus


def masque_sous_ouvrage(hi, H, adouci=1.2):
    """Masque plein sous la base de l'ouvrage, colonne par colonne."""
    r = garde_par_colonne(hi)
    if r is None:
        return None
    ligne, vus = r
    W = len(ligne)
    m = np.zeros((H, W), float)
    for x in range(W):
        if vus[x]:
            v = int(np.clip(ligne[x], 0, H))
            m[v:, x] = 1.0
    return ndimage.gaussian_filter(m, adouci)


def score_vegetation(a, exiger_vert=False):
    """Note de 0 à 1 : à quel point ce pixel est de la végétation.

    DEUX CRITÈRES, et il faut savoir lequel on emploie.

    Le premier, historique, additionne verdeur, obscurité et texture. Il
    convient à une scène où le premier plan est sombre et le fond clair.

    Le second, `exiger_vert`, MULTIPLIE par la verdeur : sans vert, la note
    est nulle quelle que soit la texture. Il est indispensable sur une friche
    d'août, où le chaume sec est sombre ET texturé — mesuré à Gannay, la
    friche de la trouée centrale notait 0,34 avec le premier critère, passait
    le seuil, et masquait la nappe là où rien ne se trouve. Les champs beiges
    et la forêt lointaine doivent rester DERRIÈRE les panneaux ; seule la
    végétation proche, verte, est un masque.
    """
    a = a.astype(float)
    R, G, B = a[..., 0], a[..., 1], a[..., 2]
    lum = a.mean(axis=2)
    moy = ndimage.uniform_filter(lum, 9)
    tex = np.sqrt(np.maximum(ndimage.uniform_filter(lum ** 2, 9) - moy ** 2, 0))
    texture = np.clip(tex / 22.0, 0, 1)
    if exiger_vert:
        vert = np.clip((G - np.maximum(R, B)) / 18.0, 0, 1)
        return np.clip(vert * (0.75 + 0.25 * texture), 0, 1)
    vert = np.clip((G - np.maximum(R, B)) / 60.0, 0, 1)
    sombre = np.clip((150.0 - lum) / 110.0, 0, 1)
    return np.clip(0.5 * vert + 0.25 * sombre + 0.25 * texture, 0, 1)


def silhouette_ciel(a, seuil_bleu=6, seuil_nuage=140, seuil_chaud=25,
                    seuil_vert=8):
    """Pour chaque colonne, la première ligne qui n'est PLUS du ciel.

    UN NUAGE BLANC N'EST PAS BLEU, et c'est ce qui cassait la version
    précédente. Elle exigeait B nettement au-dessus de R : vrai d'un ciel
    franc, faux d'un cirrus, dont les trois canaux sont à peu près égaux. Sur
    la vue 4 de Gannay — ciel d'août chargé de cirrus — le test échouait sur
    **733 colonnes sur 1 280**, la silhouette y retombait à la ligne 0, et le
    masque déclaré sur ces colonnes effaçait alors toute la hauteur d'image.
    Conséquence mesurée : la haie paysagère était gommée sur 591 colonnes du
    montage livré, sans que rien ne le signale.

    Le ciel se définit donc par ce qu'il n'est PAS :

      - il est bleu, OU clair et neutre — un nuage ;
      - il n'est jamais CHAUD : un champ de chaume d'août est clair lui aussi,
        mais son rouge domine son bleu ;
      - il n'est jamais VERT : un houppier au soleil est clair et neutre au
        sens ci-dessus, sa verdeur le trahit.

    Les deux exclusions font le vrai travail ; le critère de bleu ne sert plus
    qu'à rattraper un ciel sombre de zénith, plus foncé que `seuil_nuage`.
    """
    a = a.astype(float)
    R, G, B = a[..., 0], a[..., 1], a[..., 2]
    lum = a.mean(axis=2)
    bleu_ou_nuage = (B - R > seuil_bleu) | ((lum > seuil_nuage)
                                            & (R - B < seuil_chaud))
    ciel = bleu_ou_nuage & (G - np.maximum(R, B) < seuil_vert)
    H, W = ciel.shape
    out = np.full(W, H, int)
    for x in range(W):
        col = np.nonzero(~ciel[:, x])[0]
        if len(col):
            out[x] = int(col[0])
    return out


#: Demi-côté, en pixels, de la vignette prise autour d'un point d'échantillon.
RAYON_GRAINE = 7

#: Aire minimale d'un amas retenu, en pixels de la zone utile.
AIRE_AMAS = 350

#: Poids de la TEXTURE comme quatrième composante du classement, rapporté aux
#: canaux R, G, B. Mesuré le 22/09/2026 sur la vue 4 : texture médiane 28 à 33
#: pour la broussaille du premier plan, 11 à 21 pour le champ et la piste. Sans
#: elle, 13 % du champ situé DERRIÈRE la nappe était classé en avant-plan ; à
#: poids 2, plus rien. Au-delà de 4 elle reprend le dessus sur la couleur et le
#: champ redevient masque : le réglage n'est pas monotone.
POIDS_TEXTURE = 2.0


def _traits(a, poids=POIDS_TEXTURE):
    """Les quatre composantes du classement : R, G, B lissés, et la texture.

    La texture est l'écart-type local de la luminance. Elle sépare ce que la
    couleur seule ne sépare pas : une broussaille sèche et un chaume sec ont
    la même teinte, mais l'une est un enchevêtrement de brindilles et l'autre
    un aplat.
    """
    a = a.astype(float)
    lum = a.mean(axis=2)
    moy = ndimage.uniform_filter(lum, 9)
    tex = np.sqrt(np.maximum(ndimage.uniform_filter(lum ** 2, 9) - moy ** 2, 0))
    return np.dstack([ndimage.uniform_filter(a, size=(7, 7, 1)),
                      ndimage.uniform_filter(tex, 9) * poids])


def _prototypes(liss, points, rayon=RAYON_GRAINE):
    """La médiane d'une vignette autour de chaque point désigné.

    UNE MÉDIANE PAR POINT, et non une seule pour toute la classe. Un premier
    plan porte souvent deux masses de teintes distinctes — sur la vue 4, le
    buisson central est à lum 74 et la broussaille de gauche à 84, avec des
    verdeurs de -4 et -17. Les fondre en une moyenne fabriquerait une teinte
    qui n'existe nulle part, et le classement se ferait contre un fantôme.
    """
    H, W = liss.shape[:2]
    out = []
    for x, y in points:
        x, y = int(x), int(y)
        v = liss[max(0, y - rayon):y + rayon + 1,
                 max(0, x - rayon):x + rayon + 1].reshape(-1, liss.shape[2])
        if len(v):
            out.append(np.median(v, axis=0))
    return np.array(out)


def masque_par_couleur(a, avant, arriere, zone=None, aire_min=AIRE_AMAS,
                       plages=(), garde=None, verbose=True):
    """Masque ce qui RESSEMBLE aux échantillons d'avant-plan, dans la zone.

    POURQUOI CECI PLUTÔT QUE LA SILHOUETTE. `masque_par_silhouette` prend pour
    bord haut le contour contre le CIEL. Cela ne vaut que si la masse déclarée
    est bien celle qui fait l'horizon dans ces colonnes. Sur la vue 4 de
    Gannay elle ne l'est pas : les buissons du premier plan culminent vers
    v=555, la ligne d'arbres lointaine vers v=530, et le champ beige se voit
    ENTRE les deux ainsi que dans les trouées entre buissons. Masquer depuis
    la silhouette y recouvrait donc le lointain avec le proche — bien plus que
    le buisson, jusqu'à 25 px de hauteur sur 545 colonnes.

    ET LES CLASSES SE SÉPARENT, contrairement à ce que j'avais conclu. Mesure
    du 22/09/2026 sur vignettes lissées : buisson lum 74, broussaille 84,
    champ 114 à 117. Distances inter-classes 52 à 75, distances intra-classes
    13 à 20. Ma mesure antérieure moyennait toute la hauteur de la bande à une
    colonne donnée, donc mélangeait buisson ET champ dans le même échantillon,
    et concluait à l'inséparabilité. C'était un artefact de la mesure.

    `avant` et `arriere` sont des listes de points (x, y) relevés sur les
    règles de la planche de validation. Deux ou trois par classe suffisent.
    """
    H, W = a.shape[:2]
    v0, v1 = zone if zone else (0, H)
    v0, v1 = int(max(0, v0)), int(min(H, v1))
    liss = _traits(a)
    p_av = _prototypes(liss, avant)
    p_ar = _prototypes(liss, arriere)
    if not len(p_av) or not len(p_ar):
        raise ValueError("il faut au moins un point d'avant-plan et un "
                         "d'arrière-plan")

    bloc = liss[v0:v1]
    d_av = np.min([np.linalg.norm(bloc - m, axis=2) for m in p_av], axis=0)
    d_ar = np.min([np.linalg.norm(bloc - m, axis=2) for m in p_ar], axis=0)
    cl = d_av < d_ar

    # Nettoyage : fermer les trouées de feuillage, puis jeter les amas trop
    # petits — un pixel isolé de la teinte du buisson, au milieu du champ, est
    # du bruit et non une masse.
    cl = ndimage.binary_closing(cl, np.ones((5, 5)))
    lab, n = ndimage.label(cl)
    if n:
        aires = ndimage.sum(cl, lab, range(1, n + 1))
        retenus = {i + 1 for i, v in enumerate(aires) if v >= aire_min}
        # CONNEXION À LA LIGNE DE GARDE. Une masse de premier plan touche le
        # sol, donc elle descend jusqu'à cette ligne. Un amas qui flotte
        # au-dessus du champ, si sombre et si vert soit-il, est un ARBRE
        # LOINTAIN — la couleur ne les distingue pas, la position si.
        # Mesuré sur la vue 4 : un arbre du fond, x 165-200, était classé en
        # avant-plan et faisait monter le masque de 573 à 538.
        if garde is not None:
            ligne = int(np.clip(round(garde) - v0, 0, cl.shape[0] - 1))
            touchent = {int(i) for i in np.unique(lab[ligne:]) if i}
            avant_n = len(retenus)
            retenus &= touchent
            if verbose and len(retenus) < avant_n:
                print(f"  {avant_n - len(retenus)} amas rejete(s) : non relie(s) "
                      f"a la ligne de garde (vegetation de fond)")
        cl = np.isin(lab, list(retenus)) if retenus else np.zeros_like(cl)
    cl = ndimage.binary_fill_holes(cl)

    m = np.zeros((H, W), float)
    m[v0:v1] = cl.astype(float)
    # Sous la zone il n'y a plus d'ouvrage rendu : on prolonge la dernière
    # ligne classée, pour que la planche et le montage racontent la même chose.
    if v1 < H and v1 > v0:
        m[v1:] = m[v1 - 1]
    if plages:
        garde_col = np.zeros(W, bool)
        for x0, x1 in plages:
            garde_col[max(0, int(x0)):min(W, int(x1))] = True
        m[:, ~garde_col] = 0.0
    if verbose:
        print(f"  couleur : {len(p_av)} graine(s) avant-plan, "
              f"{len(p_ar)} arriere-plan ; {int(cl.sum())} px classes proches "
              f"dans la zone v {v0}-{v1}")
    return ndimage.gaussian_filter(m, 1.2)


#: Lignes claires consécutives tolérées pendant la remontée. Une trouée de
#: feuillage en fait une ou deux ; le champ, lui, en fait des dizaines.
TROU = 3

#: Remontée maximale au-dessus de la ligne de garde, en FRACTION de la hauteur
#: d'image. Elle borne l'erreur : une masse qui monterait plus haut se déclare
#: à la silhouette.
#:
#: EN FRACTION, ET NON EN PIXELS. La valeur tenait 120 px, réglée sur les
#: images de 960 px de Gannay. Sur IMG_6941, qui en fait 4032, elle n'autorisait
#: plus que 3 % de l'image : les épis de blé du premier plan culminent 460 px
#: au-dessus de la ligne de garde et restaient donc démasqués, avec les fils du
#: grillage dessinés au travers. 120/960 = 0,125 : la fraction reproduit
#: exactement l'ancien comportement sur Gannay.
REMONTEE_MAX = 0.125


def _otsu(v):
    """Seuil d'Otsu sur un échantillon de luminances."""
    h, _ = np.histogram(v, bins=64, range=(0, 256))
    p = h / max(h.sum(), 1)
    w = np.cumsum(p)
    mu = np.cumsum(p * (np.arange(64) * 4 + 2))
    with np.errstate(invalid="ignore", divide="ignore"):
        inter = (mu[-1] * w - mu) ** 2 / (w * (1 - w))
    return float((np.nanargmax(inter) * 4 + 2))


def masque_remontant(a, plages, garde, zone, trou=TROU, hauteur_max=None,
                     seuil=None, verbose=True):
    """Étend le masque VERS LE HAUT depuis la ligne de garde.

    L'IDÉE, ET POURQUOI ELLE EST LA BONNE. Une masse de premier plan touche le
    sol, donc elle traverse la ligne de garde — qui est, elle, une certitude
    géométrique. On part donc de cette certitude et on remonte tant que le
    pixel reste sombre, c'est-à-dire tant qu'on est encore dans la masse. On
    s'arrête au premier passage au clair : le champ, qui est derrière.

    CE QUE J'AVAIS FAIT AVANT, ET QUI ÉTAIT FAUX. Je cherchais la cime en
    descendant depuis le haut de la bande, au premier passage au sombre. Mais
    le premier passage au sombre, c'est la LIGNE D'ARBRES LOINTAINE, pas le
    buisson proche. Mesure sur la vue 4 : le masque rejoignait la silhouette
    du ciel sur 530 colonnes sur 600, écart médian nul — autrement dit il
    prenait tout le lointain. En remontant depuis la garde : 101 colonnes sur
    600, écart médian 8 px, et la ligne d'arbres reste visible au-dessus du
    buisson, ce qu'elle doit être.

    Entre les deux il y a le champ clair, et c'est lui qui arrête la remontée.
    Une masse qui n'est PAS reliée à la ligne de garde par une continuité de
    pixels sombres n'est donc jamais prise : c'est exactement la définition du
    premier plan qu'on cherchait, et elle ne demande aucun classement.

    LE SEUIL EST LA MÉDIANE DES PIXELS QUI NE SONT NI CIEL NI SOUS LA GARDE,
    sur les colonnes déclarées. Ce découpage n'est pas un détail : pris sur une
    fenêtre fixe au-dessus de la garde, le seuil dépend entièrement de sa
    hauteur — mesuré sur la vue 4, il vaut 105 sur 30 px et 150 sur 50, parce
    que le ciel entre dans la statistique et la tire vers le haut. À 150 la
    remontée traverse le champ et rejoint le lointain sur 572 colonnes sur 600.
    Otsu se trompe pour la même raison, en sens inverse : il donne 138 ici,
    car il suppose deux modes de poids voisins.

    En excluant le ciel, il n'y a plus de fenêtre à choisir et le seuil vaut
    98 sur la vue 4. La remontée y est alors PRUDENTE : cime médiane 568 quand
    le vrai sommet du buisson est vers 563, et 20 colonnes sur 600 seulement
    remontent jusqu'au lointain, contre 530 avec la méthode précédente. Elle
    sous-masque donc de quelques pixels plutôt que de surmasquer, et c'est le
    bon sens de l'erreur : un peu de projet visible en trop se corrige à la
    main, du lointain avalé par le masque ne se voit pas.
    """
    H, W = a.shape[:2]
    if hauteur_max is None:
        hauteur_max = int(round(REMONTEE_MAX * H))
    v0, v1 = int(max(0, zone[0])), int(min(H, zone[1]))
    vg = int(min(max(int(round(garde)), v0 + 1), H - 1))
    lum = ndimage.uniform_filter(a.astype(float).mean(axis=2), (3, 5))
    cols = [x for x0, x1 in plages for x in range(max(0, int(x0)),
                                                  min(W, int(x1)))]
    if not cols:
        return np.zeros((H, W), float)
    if seuil is None:
        ciel = silhouette_ciel(a)
        vals = [lum[ciel[x] + 2:vg, x] for x in cols if ciel[x] + 2 < vg]
        seuil = float(np.median(np.concatenate(vals))) if vals else 110.0
    m = np.zeros((H, W), float)
    cimes = []
    for x in cols:
        v, creux = vg, 0
        while v > vg - hauteur_max and v > 0:
            if lum[v - 1, x] < seuil:
                creux = 0           # toujours dans la masse
            else:
                creux += 1
                if creux > trou:    # une vraie trouée claire : on est sorti
                    break
            v -= 1
        cime = v + creux
        cimes.append(cime)
        m[cime:, x] = 1.0
    if verbose:
        c = np.array(cimes)
        print(f"  remontee depuis la garde : seuil {seuil:.0f}, cime mediane "
              f"v={np.median(c):.0f} (q10 {np.quantile(c, .1):.0f}, q90 "
              f"{np.quantile(c, .9):.0f}), remontee mediane "
              f"{vg - np.median(c):.0f} px")
    return ndimage.gaussian_filter(m, 1.2)


def masque_par_silhouette(a, plages, adouci=1.2):
    """Masque plein SOUS la silhouette, sur les plages de colonnes données.

    POURQUOI CE DÉTOUR. Sur la vue 4 de Gannay, la masse de broussailles du
    premier plan n'est pas verte : sa verdeur mesurée vaut -2 à -22, soit
    exactement la signature de la friche sèche qui est, elle, DERRIÈRE la
    nappe. Aucun critère de couleur ne peut les séparer — je l'ai vérifié.

    Mais au-dessus de ces masses il y a le CIEL, et au-dessus de la friche il
    y a la nappe. Leur silhouette contre le ciel est donc un contour exact et
    gratuit. Le seul jugement humain est la plage de colonnes où la masse se
    trouve, ce qui se lit sur la photo et s'écrit dans la vue.

    Chaque plage vaut (x0, x1) ou (x0, x1, opacite). L'opacite sert aux
    masses AJOUREES : un grillage a maille losange ne bouche qu'un quart de
    ce qu'il couvre, et l'ouvrage doit rester partiellement visible derriere.

    LE BORD LATÉRAL, LUI, EST VERTICAL, ET IL FAUT SAVOIR CE QUE CELA VAUT.
    Une plage à deux colonnes coupe la masse au couteau sur ses côtés. C'est
    localement JUSTE — au point le plus large d'un buisson, son contour est
    tangent à une verticale — et l'erreur croît à mesure qu'on s'en éloigne en
    hauteur. Dans la bande du projet, qui fait 31 à 37 px sur les vues de
    Gannay, elle reste petite. Sur une masse haute recoupée par un ouvrage
    haut, elle ne l'est plus.

    JE N'AI PAS TROUVÉ D'AUTOMATISME POUR CE BORD, et ce n'est pas faute
    d'essais : distance aux statistiques de la graine, classifieur à deux
    moyennes, champ lissé, recherche de chemin par programmation dynamique,
    prolongement de la pente du sommet. Les trois premiers donnent un bord qui
    saute de 40 à 65 px d'une ligne à l'autre ; le quatrième est continu mais
    dérive de 80 à 90 px et ramène le bord franc d'un pilier maçonné 45 px
    trop à gauche ; le cinquième ne produit rien là où il faudrait et un flanc
    de 70 px sur le pilier, qui est justement le seul bord vraiment vertical
    de la scène. La cause est mesurée : au niveau de la nappe, la broussaille
    proche et le champ lointain ont la même signature — séparation des deux
    médianes de 25 sur 255 à la borne x=545 de la vue 4. Le bord latéral d'une
    masse est une discontinuité de PROFONDEUR, et elle n'a pas de signature
    dans l'image.

    D'OÙ LE PROFIL. Une plage peut porter, en quatrième terme, une polyligne
    de points (x, v) qui remplace la silhouette sur son étendue. L'opérateur
    la relève sur les deux règles de la planche de validation, en trois ou
    quatre points, et elle descend le flanc jusque sous la bande du projet —
    où la coupe verticale qui subsiste ne se voit plus. C'est du travail
    humain, mais seulement là où le bord traverse un ouvrage.
    """
    H, W = a.shape[:2]
    sil = silhouette_ciel(a)
    m = np.zeros((H, W), float)
    for plage in plages:
        x0, x1 = int(plage[0]), int(plage[1])
        op = float(plage[2]) if len(plage) > 2 else 1.0
        haut = _profil(plage[3], W) if len(plage) > 3 and plage[3] else sil
        for x in range(max(0, x0), min(W, x1)):
            m[int(haut[x]):, x] = np.maximum(m[int(haut[x]):, x], op)
    return ndimage.gaussian_filter(m, adouci)


def _profil(points, W):
    """Une polyligne (x, v) rendue colonne par colonne, par interpolation.

    Hors de son étendue, elle prolonge ses extrémités : une masse déclarée un
    peu plus large que son profil ne doit pas se retrouver démasquée.
    """
    pts = sorted((int(x), float(v)) for x, v in points)
    xs = np.array([p[0] for p in pts], float)
    vs = np.array([p[1] for p in pts], float)
    return np.interp(np.arange(W), xs, vs, left=vs[0], right=vs[-1])


def masque(photo, pose, d_min, seuil=0.30, marge_laterale=0.30,
           remontee=110, opaques=(), seuil_opaque=0.40,
           exiger_vert=False, adouci=None, raideur=None,
           silhouettes=(), couleurs=None, fonds=(), seuil_fond=None,
           arriere_plan=(), zone=None, verbose=True):
    a = np.array(Image.open(photo).convert("RGB"))
    H, W = a.shape[:2]
    garde = ligne_de_garde(pose, d_min)
    s = score_vegetation(a, exiger_vert)

    m = np.zeros((H, W), float)
    # --- 1. sous la ligne de garde : certitude géométrique -----------------
    v0 = int(max(0, min(H - 1, math.floor(garde))))
    m[v0:, :] = 1.0
    if verbose:
        print(f"  ligne de garde : v={garde:.0f} pour d_min={d_min:.0f} m "
              f"({(H - v0) / H * 100:.0f} % de la hauteur d'image)")

    # --- 1 bis. masses declarees, classees par la COULEUR -------------------
    # C'est la voie à préférer quand la masse de premier plan ne fait pas
    # l'horizon : elle suit alors son vrai contour, laisse le fond visible
    # dans les trouées, et n'a aucun bord vertical.
    if couleurs:
        z = zone or (int(max(0, garde - 160)), H)
        mc = masque_par_couleur(a, couleurs["avant"], couleurs["arriere"],
                                zone=z, plages=couleurs.get("plages", ()),
                                garde=garde, verbose=verbose)
        m = np.maximum(m, mc)

    # --- 1 ter. masses etendues VERS LE HAUT depuis la ligne de garde -------
    if fonds:
        z = zone or (int(max(0, garde - 160)), H)
        m = np.maximum(m, masque_remontant(a, fonds, garde, z, seuil=seuil_fond,
                                           verbose=verbose))

    # --- 1 ter bis. plages DÉCLARÉES en arrière-plan -----------------------
    #
    # LE DERNIER MOT REVIENT À L'OPÉRATEUR, et il en faut un. Un arbre
    # lointain dont le houppier touche, dans l'image, la masse proche qui est
    # devant lui forme une colonne sombre continue : la remontée y monte, le
    # classement par couleur le prend pour du feuillage proche — il l'est, en
    # teinte — et le filtre médian ne le rejette pas non plus, parce que le
    # feuillage VRAIMENT proche qui le jouxte monte tout aussi haut. Mesuré
    # sur la vue 4, colonnes 990-1035 : cime à 523, médiane locale 537, donc
    # aucune pointe à détecter.
    #
    # Rien dans l'image ne sépare ces deux-là. On arrête donc d'inventer des
    # règles et on laisse dire : ces colonnes sont du fond, le masque y
    # retombe sur la seule ligne de garde.
    # ELLES PASSENT AVANT LES SILHOUETTES DÉCLARÉES, et l'ordre est le sens
    # même de la chose : on annule ce que les automatismes ont cru voir, PUIS
    # l'opérateur redéclare ce qui s'y trouve vraiment — souvent un profil,
    # quand la masse proche continue plus bas que ce qui a été rejeté.
    if arriere_plan:
        v0 = int(max(0, min(H - 1, math.floor(garde))))
        for x0, x1 in arriere_plan:
            m[:v0, max(0, int(x0)):min(W, int(x1))] = 0.0
        if verbose:
            larg = sum(min(W, int(b)) - max(0, int(a)) for a, b in arriere_plan)
            print(f"  {len(arriere_plan)} plage(s) declaree(s) en arriere-plan : "
                  f"{larg} colonnes ramenees a la ligne de garde")


    # --- 1 quater. masses declarees, detourees a leur SILHOUETTE ------------
    if silhouettes:
        ms = masque_par_silhouette(a, silhouettes)
        m = np.maximum(m, ms)
        if verbose:
            print(f"  {len(silhouettes)} masse(s) detourees a la silhouette : "
                  f"{int((ms > 0.5).sum())} px")

    # --- 2. végétation des MARGES, juste au-dessus de la ligne de garde ----
    #
    # DEUX BORNES, et elles sont nécessaires. Sans elles, la végétation forme
    # UN SEUL amas de 369 000 px qui va de la haie de gauche à la ligne
    # d'arbres du fond en passant par la friche : le masquer effacerait la
    # nappe derrière les arbres lointains, qui sont pourtant DERRIÈRE elle.
    #
    #   - en X, on ne regarde que les marges : ce qui encadre le cliché est
    #     près, ce qui est au centre peut être loin ;
    #   - en Y, on ne remonte que de `remontee` pixels au-dessus de la ligne
    #     de garde. Une masse proche dépasse peu cette ligne — la haie de
    #     gauche culmine 26 px au-dessus — alors que la ligne d'arbres est
    #     cent pixels plus haut.
    #
    # C'est une heuristique, pas une mesure. Un obstacle au centre du cadre,
    # ou une masse haute et proche, demande le masque dessiné à la main.
    mx = int(W * marge_laterale)
    fenetre = np.zeros((H, W), bool)
    fenetre[max(0, v0 - remontee):v0, :mx] = True
    fenetre[max(0, v0 - remontee):v0, W - mx:] = True
    veg = (s > seuil) & fenetre
    veg = ndimage.binary_closing(veg, np.ones((7, 7)))
    # on ne garde que ce qui DESCEND jusqu'a la ligne de garde : une masse de
    # premier plan est contigue au sol, un houppier isole ne l'est pas.
    lab, n = ndimage.label(veg)
    garde_ids = {int(i) for i in np.unique(lab[v0 - 2:v0, :]) if i}
    garde_ids = {i for i in garde_ids
                 if int((lab == i).sum()) >= AIRE_MIN // 6}
    if garde_ids:
        # BINAIRE, et non un fondu par le score. Un masque a 0,6 compose le
        # rendu a 40 % : les panneaux deviennent translucides et l'on voit le
        # lointain au travers. Mesure sur la vue 4 : 30 % des pixels de rendu
        # PLEIN tombaient sur un masque entre 0,05 et 0,95.
        #
        # La porosite d'une lisiere se joue sur quelques pixels, pas sur toute
        # une masse : c'est le flou final, `ADOUCI`, qui s'en charge.
        sel = ndimage.binary_fill_holes(np.isin(lab, list(garde_ids)))
        m = np.maximum(m, sel.astype(float))
        # --- zones DECLAREES opaques --------------------------------------
        #
        # Le fondu par le score est juste pour une lisiere qu'on traverse du
        # regard. Il ne l'est pas pour une masse pleine : un buisson dense se
        # bouche entierement, et le laisser a 60 % d'opacite laisse voir la
        # cloture au travers. L'operateur declare donc les cotes pleins, et on
        # y prend la masse ENTIERE — au-dela de la fenetre de recherche, trous
        # rebouches — au lieu de son score.
        #
        # C'est le seul endroit du module ou un jugement humain entre, et il
        # entre explicitement : `opaques=("droite",)` se lit dans l'appel.
        if opaques:
            # SEUIL RELEVE, et c'est la clef. A 0,26 la vegetation ne forme
            # qu'une seule composante d'un bord a l'autre, et la remplir
            # effaçait la moitie du montage. A 0,40, la masse dense du buisson
            # se detache : mesure sur ce cliche, son score median passe de
            # 0,30 a x=1550 a 0,46 a x=1600, et la composante sort a
            # x 1502-1995 — exactement le buisson, sans la friche.
            #
            # On garde alors la composante ENTIERE, trous rebouches : c'est
            # sa silhouette qui masque, pas une tranche de l'image.
            plein = ndimage.binary_closing(s > seuil_opaque, np.ones((9, 9)))
            lab2, _ = ndimage.label(plein)
            for cote in opaques:
                zone = slice(0, mx // 2) if cote == "gauche" else slice(W - mx // 2, W)
                pris = {int(i) for i in np.unique(lab2[:, zone]) if i}
                pris = {i for i in pris if int((lab2 == i).sum()) >= AIRE_MIN}
                if not pris:
                    continue
                masse = ndimage.binary_fill_holes(np.isin(lab2, list(pris)))
                m = np.maximum(m, masse.astype(float))
                if verbose:
                    ys, xs = np.nonzero(masse)
                    print(f"  cote {cote} declare opaque : {int(masse.sum())} px "
                          f"portes a 1,0, silhouette x {xs.min()}-{xs.max()} "
                          f"y {ys.min()}-{ys.max()}")
    if verbose:
        print(f"  marges : {len(garde_ids)} masse(s) retenues sur {n} amas "
              f"(marge {marge_laterale*100:.0f} %, remontee {remontee} px)")
        print(f"  masque : {m.mean()*100:.0f} % de l'image, "
              f"{(m > 0.5).mean()*100:.0f} % au-dessus de 0,5")
    # LISIERE COURTE ET FRANCHE. Un flou seul etale la transition sur trois a
    # quatre pixels ; sur une nappe qui n'en fait que vingt-trois de haut, et
    # dont la silhouette d'occultation passe justement en plein milieu, cela
    # compose 29 % de l'ouvrage en semi-transparence — on voit le lointain au
    # travers des panneaux. On floute donc peu, puis on RAIDIT : la transition
    # retombe a un pixel ou deux, assez pour ne pas decouper au ciseau, trop
    # courte pour delaver quoi que ce soit.
    m = ndimage.gaussian_filter(m, ADOUCI if adouci is None else adouci)
    k = RAIDEUR if raideur is None else raideur
    return np.clip((m - 0.5) * k + 0.5, 0.0, 1.0)


def composer(photo, rendu, sortie, m):
    """Compose en ATTÉNUANT le rendu par le masque, sans l'effacer."""
    ph = Image.open(photo).convert("RGB")
    r = Image.open(rendu).convert("RGBA")
    if r.size != ph.size:
        r = r.resize(ph.size, Image.LANCZOS)
    c = np.array(r).astype(float)
    a = c[..., 3] / 255.0 * (1.0 - m)
    out = np.array(ph).astype(float) * (1 - a[..., None]) + c[..., :3] * a[..., None]
    Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).save(sortie, quality=95)
    return int((a > 0.02).sum())


if __name__ == "__main__":
    photo, scene, pose_f = sys.argv[1], sys.argv[2], sys.argv[3]
    sortie = sys.argv[4] if len(sys.argv) > 4 else "masque.png"
    p = json.loads(Path(pose_f).read_text(encoding="utf-8"))
    d_min = distance_mini(scene)
    m = masque(photo, p, d_min)
    Image.fromarray((m * 255).astype(np.uint8)).save(sortie)
    print(f"ecrit : {sortie}")
