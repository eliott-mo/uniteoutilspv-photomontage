#!/usr/bin/env python3
"""Efface la végétation vouée au défrichement, en prolongeant le ciel.

POURQUOI CETTE OPÉRATION EXISTE
-------------------------------
Un masque de premier plan retient ce qui passe DEVANT le projet. Il ne sert à
rien quand la végétation est DERRIÈRE la clôture : elle est dans l'emprise,
elle sera défrichée, et le montage de l'état projeté doit la faire disparaître.

Mesuré à Saint-Cyr, vue PM3 : la broussaille dépasse le haut du projet sur
1 602 colonnes sur 1 750, de 81 px en médiane. Composer le rendu sans rien
faire laisserait une ligne de ronces flottant au-dessus des panneaux, sur 92 %
de la largeur — une centrale derrière une haie qui n'existera plus.

CE QU'ON PEUT FAIRE, ET CE QU'ON NE PEUT PAS
---------------------------------------------
Effacer une masse, c'est restituer ce qu'il y a derrière. La photo ne le
contient pas : cette végétation est précisément ce qui le cache.

Au-dessus de la silhouette il y a du CIEL, et un ciel est un dégradé lisse
qu'on prolonge sans rien inventer — c'est de l'extrapolation, pas de la
création. C'est le seul cas où l'effacement est honnête, et c'est celui qu'on
traite ici.

LA LIMITE EST À DIRE, PAS À MASQUER : là où un boisement HORS emprise affleure
derrière la végétation à défricher, le prolonger en ciel l'efface aussi. Rien
dans l'image ne sépare les deux — le pied d'un arbre lointain et celui d'un
buisson proche se projettent dans la même bande. `prolonger_ciel` rapporte donc
la surface qu'il a réécrite, pour qu'on sache ce qu'on signe.

COMMENT
-------
Par colonne : on ajuste la couleur du ciel en fonction de la ligne sur la bande
qui précède la silhouette, et on prolonge cette droite vers le bas. Les
coefficients sont lissés en travers, sinon chaque colonne part pour son compte
et le ciel se met à vibrer.
"""
import numpy as np
from PIL import Image
from scipy import ndimage

#: Hauteur de ciel, en pixels, sur laquelle la pente verticale s'ajuste.
APPUI = 150

#: Lissage des coefficients en travers, en colonnes. Un ciel varie lentement
#: d'une colonne a l'autre ; sans ce lissage, chaque colonne extrapole pour son
#: compte et la bande reconstituee se met a vibrer.
LISSAGE = 41

#: Fondu, en pixels, au raccord avec le ciel existant.
FONDU = 6

#: Ecart au ciel estime, en niveaux, au-dela duquel un pixel est de la
#: vegetation. Un vrai ciel s'en ecarte de quelques niveaux ; une brindille
#: anticrenelee de plusieurs dizaines.
#:
#: LE SEUIL SE REGLE SUR L'ERREUR DE L'ESTIMATION, pas sur le contraste de la
#: branche. Il valait 14 du temps du modele global, dont l'erreur mediane sur
#: du vrai ciel etait de 8 niveaux : un pixel de ciel sur cinq depassait le
#: seuil et se faisait repeindre a la valeur du modele, plus claire de dix a
#: quinze niveaux sur la moitie droite de l'image. D'ou les arbres en fantome
#: pale releves sur PM4 — c'etait le ciel repeint, pas la branche survivante.
#:
#: Le fond local ramene cette erreur mediane a 1,5. A 8, il touche donc moins
#: de vrai ciel que le global n'en touchait a 14, tout en mordant plus bas sur
#: les brindilles.
SEUIL_ECART = 5.0


def enveloppe(sil, fenetre=81, lissage=41):
    """Le sommet LOCAL de la végétation, au-dessus de la plupart des brindilles.

    Le prolongement colonne par colonne depuis `sil` ne marche pas sur une
    végétation d'hiver : la silhouette y est celle de la brindille la plus
    externe, elle saute de cent pixels d'une colonne à l'autre, et remplir
    depuis cette ligne dessine un peigne de traits verticaux — constaté sur
    PM3 de Saint-Cyr.

    On prend donc le minimum local de la silhouette, c'est-à-dire le point le
    plus HAUT atteint par la végétation dans le voisinage, puis on lisse. La
    bande à réécrire part de là : toutes les brindilles sont dedans, et ce
    qu'on efface au-dessus n'est que du ciel, qu'on remplace par du ciel.
    """
    haut = ndimage.minimum_filter1d(np.asarray(sil, float), fenetre)
    return ndimage.uniform_filter1d(haut, lissage)


def _modele_ciel(a, sil, marge=8):
    """Couleur du ciel en fonction de (x, y), ajustée sur le ciel réel.

    Un degre en x, deux en y : un ciel s'assombrit vers le zenith et vire
    lentement d'un bord a l'autre. Au-dela, le modele se mettrait a suivre les
    nuages, et on ne veut pas les recopier la ou ils n'ont pas de raison d'etre.
    """
    H, W = a.shape[:2]
    ys, xs = np.nonzero(np.arange(H)[:, None] < (np.asarray(sil) - marge)[None, :])
    if len(ys) < 500:
        return None
    pas = max(1, len(ys) // 60000)          # un echantillon suffit
    ys, xs = ys[::pas], xs[::pas]
    A = np.column_stack([xs, ys, ys ** 2, np.ones_like(xs)]).astype(float)
    coef, *_ = np.linalg.lstsq(A, a[ys, xs, :].astype(float), rcond=None)
    return coef


#: Echelles du fond de ciel, en pixels a pleine resolution. La plus fine sert
#: entre deux brindilles, la plus grossiere derriere un houppier entier.
ECHELLES = (6, 12, 24, 48, 96, 192, 384)

#: Sous-echantillonnage du fond. Le fond est lisse par construction : le
#: calculer au quart coute seize fois moins cher et ne change rien de visible.
PAS_FOND = 4

#: Rapport entre la portee laterale et la portee verticale du fond.
ANISOTROPIE = 5.0

#: Part de support en dessous de laquelle une echelle ne repond pas, et part
#: au dela de laquelle elle repond seule.
APPUI_MIN = 0.06
APPUI_PLEIN = 0.20

#: Ecart de TEINTE (R-B) au fond, en niveaux, au dela duquel un pixel sort du
#: support : c'est du bois deguise en ciel.
PURETE = 12.0

#: Ecart de teinte, en niveaux, au dela de la teinte de ciel de la ligne.
MARGE_TEINTE = 15.0

#: Nombre de nettoyages du support. Au dela, le fond se met a suivre le seul
#: quantile haut et les nuages deviennent la norme.
PASSES = 3


def _assez_bleu(a, support, marge=None, lissage=61):
    """Retire du support ce qui est trop CHAUD pour etre le ciel de sa ligne.

    POURQUOI UNE REFERENCE EXTERIEURE. Nettoyer le support en le comparant au
    fond ne marche pas : dans un rideau d'arbres, le fond porte deja
    l'empreinte des arbres, l'ecart y est donc petit, et la passe de nettoyage
    ne retire rien. Il faut une reference qui ne vienne pas de ce qu'on nettoie.

    POURQUOI PAR LIGNE. Un ciel a une teinte tres stable — six niveaux de R-B
    d'un bout a l'autre du ciel franc — mais elle DERIVE avec la hauteur : le
    bleu du zenith vaut -95, la brume de l'horizon -37. Un seuil unique
    refuserait la brume, qui est du vrai ciel.

    On prend donc, ligne par ligne, le quart le plus bleu du support : les
    branches etant toujours plus chaudes que le ciel qu'elles masquent, ce
    quantile est du ciel des qu'une ligne n'est pas bouchee de bout en bout.
    """
    a = np.asarray(a, float)
    rb = a[..., 0] - a[..., 2]
    sup = np.asarray(support, bool)
    H = a.shape[0]
    ref = np.full(H, np.nan)
    for y in range(H):
        if sup[y].sum() >= 20:
            ref[y] = np.percentile(rb[y][sup[y]], 25)
    ok = np.isfinite(ref)
    if ok.sum() < 5:
        return sup
    ref = np.interp(np.arange(H), np.nonzero(ok)[0], ref[ok])
    ref = ndimage.uniform_filter1d(ref, lissage, mode="nearest")
    return sup & (rb < ref[:, None] + (MARGE_TEINTE if marge is None else marge))


def _fond_ciel(a, support, echelles=ECHELLES, pas=PAS_FOND):
    """Le ciel VOISIN, etale sur ce qu'on va effacer.

    POURQUOI PAS UN MODELE GLOBAL. `_modele_ciel` ajuste un polynome — degre 1
    en x, 2 en y — sur tout le ciel de la photo. C'est une bonne moyenne et une
    mauvaise valeur locale : mesure sur PM4 de Saint-Cyr, l'ecart-type du
    residu vaut 12 a 15 niveaux, et a mi-hauteur le ciel reel descend a 186 la
    ou le modele annonce 198. Tout pixel repeint sur la droite de l'image
    ressortait donc plus clair que ses voisins, dans la forme exacte de l'arbre
    efface. Un polynome ne peut pas suivre un ciel qui n'est pas monotone en x
    (206, 206, 201, 209, 176, 200 releves a hauteur constante).

    ON PREND DONC LE CIEL D'A COTE. Convolution normalisee : a chaque echelle,
    la moyenne du ciel disponible ponderee par une gaussienne, du plus fin au
    plus grossier, chaque echelle ne servant que la ou les plus fines n'avaient
    pas de quoi repondre. Entre deux brindilles, le ciel est a six pixels et
    c'est lui qu'on recopie ; derriere un houppier, on va chercher plus loin.

    Mesure : erreur mediane sur du vrai ciel 8,3 -> 1,5 (PM3), 7,8 -> 1,4 (PM4).

    `support` dit ou le ciel est lisible. Une deuxieme passe, qui en retire ce
    qui s'ecarte de la premiere, gagne 0,2 niveau — ca ne vaut pas son cout.
    """
    a = np.asarray(a, dtype=float)
    H, W = a.shape[:2]
    support = np.asarray(support, bool) & _assez_bleu(a, support)
    m = support.astype(float)

    # Reduction ponderee : une case ne compte que le ciel qu'elle contient.
    nH, nW = -(-H // pas), -(-W // pas)
    pad = ((0, nH * pas - H), (0, nW * pas - W))
    mp = np.pad(m, pad).reshape(nH, pas, nW, pas).sum(axis=(1, 3))
    ap = np.stack([np.pad(a[..., c] * m, pad).reshape(nH, pas, nW, pas).sum(axis=(1, 3))
                   for c in range(a.shape[2])], axis=-1)
    petit = np.where(mp[..., None] > 0, ap / np.maximum(mp[..., None], 1e-9), 0.0)
    poids = (mp > 0).astype(float)

    def pyramide(poids):
        fond = np.zeros_like(petit)
        reste = np.ones((nH, nW), float)
        for s in echelles:
            # ANISOTROPE, PARCE QU'UN CIEL EST UN DEGRADE VERTICAL. Sur PM4 il
            # passe de 129 a 210 niveaux entre le haut de l'image et l'horizon,
            # soit un quart de niveau par ligne ; une gaussienne isotrope assez
            # large pour traverser un houppier lisse aussi cette pente et rend
            # le fond trop sombre en bas. On va donc chercher loin EN LARGEUR,
            # ou il y a du ciel entre les arbres, et pres EN HAUTEUR.
            sy = max(1.0, s / pas / ANISOTROPIE)
            sx = max(1.0, s / pas)
            num = ndimage.gaussian_filter(petit * poids[..., None], (sy, sx, 0))
            den = ndimage.gaussian_filter(poids, (sy, sx))
            # IL FAUT UNE MAJORITE DE SUPPORT, PAS UNE TRACE. Le seuil valait
            # 1 % : dans un houppier dense, ou `_est_ciel` ne retient que les
            # quelques pixels de bois les plus clairs, cela suffisait a ce que
            # l'echelle fine reponde — et le fond y devenait brun. Les arbres
            # ressortaient alors en fantome chaud au lieu de disparaitre.
            part = np.minimum(np.clip((den - APPUI_MIN) / APPUI_PLEIN, 0.0, 1.0),
                              reste)
            fond += np.where(den[..., None] > 1e-9,
                             num / np.maximum(den[..., None], 1e-9), 0.0) * part[..., None]
            reste -= part
            if reste.max() < 1e-3:
                break
        # Ce qui n'a trouve de support a aucune echelle prend la moyenne.
        if reste.max() > 1e-3:
            moy = (petit * poids[..., None]).sum(axis=(0, 1)) / max(poids.sum(), 1e-9)
            fond += reste[..., None] * moy[None, None, :]
        return fond

    # LE SUPPORT EST SALE, ET ON LE NETTOIE PAR LA TEINTE. `_est_ciel` accepte
    # ce qui est clair et neutre, pour ne pas perdre les nuages ; un peuplier
    # d'hiver au soleil est clair et presque neutre, et passe avec eux. Dans un
    # rideau d'arbres nus, ces pixels FONT le support, et le fond finit par
    # porter l'empreinte des arbres — visible directement en regardant le fond.
    #
    # LA LUMINANCE NE LES SEPARE PAS : ces branches sont PLUS CLAIRES que le
    # ciel (lum mediane 190 contre 170 sur PM3), pas plus sombres. La teinte,
    # elle, les separe nettement. Mesure sur les deux photos de Saint-Cyr :
    #
    #     R-B    ciel franc          rideau d'arbres
    #     PM3    -104 / -101 / -98   -82 / -69 / -19   (p10 / med / p90)
    #     PM4     -98 /  -95 / -93   -82 / -58 / -28
    #
    # Un ciel tient dans six niveaux de R-B. On retire donc du support ce qui
    # s'ecarte de la teinte du fond, et un nuage — qui differe par la clarte et
    # non par la teinte — y reste. Trois passes, le fond se purifiant a chacune.
    fond = pyramide(poids)
    for _ in range(PASSES):
        chaud = np.abs((petit[..., 0] - petit[..., 2])
                       - (fond[..., 0] - fond[..., 2])) > PURETE
        p = poids * (~chaud)
        if p.sum() < 0.1 * poids.sum():
            break
        fond = pyramide(p)

    grand = ndimage.zoom(fond, (pas, pas, 1), order=1, mode="nearest")
    return grand[:H, :W]


def _est_ciel(a, seuil_bleu=6, seuil_nuage=140, seuil_chaud=25, seuil_vert=8):
    """Le meme critere que `masque_avant_plan.silhouette_ciel`, en 2D."""
    a = np.asarray(a, dtype=float)
    R, G, B = a[..., 0], a[..., 1], a[..., 2]
    lum = a.mean(axis=2)
    return (((B - R > seuil_bleu) | ((lum > seuil_nuage) & (R - B < seuil_chaud)))
            & (G - np.maximum(R, B) < seuil_vert))


#: Alpha au dela duquel un pixel de rendu compte comme « du projet ».
#:
#: 128 EST TROP HAUT. Le grillage est une nappe a texture ajouree : entre deux
#: poteaux, son alpha plafonne a 80. A 128, la colonne n'avait donc aucun pixel
#: de projet, `bas` y valait NaN, et rien n'y etait defriche — d'ou un peigne
#: de bandes verticales non traitees, une par entre-poteau, et la « ligne de
#: partage » que le chef de projet a relevee a gauche de la vue 3. A 32, la
#: ligne est continue : 765, 769, 757, 756, 754 sur les colonnes ou 128 donnait
#: 765, NaN, NaN, 756, 823.
SEUIL_PROJET = 32


def bord_projet(rendu, seuil_alpha=SEUIL_PROJET, lissage=9):
    """Haut du rendu, colonne par colonne, sans trou.

    C'est la limite BASSE du defrichement : au-dessous, le rendu couvre, et il
    n'y a rien a effacer. Les colonnes que le rendu ne touche pas du tout —
    au-dela de l'emprise laterale — restent a NaN : il n'y a la ni projet ni
    defrichement, et les combler reviendrait a effacer une vegetation que le
    projet ne touche pas.
    """
    r = np.asarray(Image.open(rendu).convert("RGBA"))
    op = r[..., 3] > seuil_alpha
    H, W = op.shape
    haut = np.full(W, np.nan)
    for x in range(W):
        o = np.nonzero(op[:, x])[0]
        if len(o):
            haut[x] = o[0]
    # Les trous INTERIEURS se comblent — ils viennent d'un materiau ajoure, pas
    # d'une absence de projet. Les bords, non.
    ok = np.isfinite(haut)
    if ok.any():
        i0, i1 = int(np.argmax(ok)), W - 1 - int(np.argmax(ok[::-1]))
        idx = np.arange(i0, i1 + 1)
        haut[i0:i1 + 1] = np.interp(idx, idx[ok[i0:i1 + 1]],
                                    haut[i0:i1 + 1][ok[i0:i1 + 1]])
        haut[i0:i1 + 1] = ndimage.uniform_filter1d(haut[i0:i1 + 1], lissage,
                                                   mode="nearest")
    return haut


def defricher_pixel(a, sil, bas, adouci=1.6, verbose=True):
    """Efface la vegetation PIXEL PAR PIXEL, en laissant le ciel intact.

    LA BONNE FORMULATION, TROUVEE APRES DEUX MAUVAISES. Les deux premieres
    remplissaient une BANDE — de la silhouette au projet, puis de l'enveloppe
    au projet. Toutes deux dessinaient un peigne de traits verticaux, parce
    qu'une bande a des bords, et que ces bords sont dechiquetes aux deux
    extremites : en haut la brindille la plus externe, en bas le sommet du
    projet qui alterne entre poteau de cloture et nappe.

    Or il n'y a pas de bande a remplir. Entre les branches nues, LE CIEL EST
    DEJA LA : il n'y a que les branches a remplacer. On ne touche donc que les
    pixels qui ne sont pas du ciel, un par un, et le probleme des bords
    disparait avec les bords.

    C'est aussi pourquoi l'operation reste honnete : on ne reconstitue rien,
    on prolonge le ciel de part et d'autre de ce qu'on efface.
    """
    a = np.asarray(a, dtype=float)
    H, W = a.shape[:2]
    sil = np.asarray(sil, float)
    bas = np.asarray(bas, float)

    lignes = np.arange(H)[:, None]
    dedans = lignes < np.where(np.isfinite(bas), bas, 0.0)[None, :]

    # LE SUPPORT S'ARRETE AU PROJET. `_est_ciel` appelle ciel tout ce qui est
    # clair et neutre, ce qui comprend la route et le beton ; une gaussienne
    # large les ferait remonter dans le ciel. On ne lit donc le ciel qu'au
    # dessus du rendu, ou a defaut au dessus de la silhouette.
    limite = np.where(np.isfinite(bas), bas, sil)
    support = _est_ciel(a) & (lignes < limite[None, :])
    if support.sum() < 500:
        if verbose:
            print("  defrichement : pas assez de ciel lisible")
        return a.astype(np.uint8), 0
    fond = _fond_ciel(a, support)

    # PAR ECART AU FOND, ET NON PAR UN TEST DE CIEL BINAIRE.
    #
    # Une branche nue contre un ciel clair est ANTICRENELEE : le pixel est un
    # melange de bois et de ciel, et le test de ciel le classe du cote du ciel.
    # Les brindilles survivaient donc a l'effacement — d'ou les arbres a moitie
    # gommes que le chef de projet a releves.
    #
    # On mesure plutot l'ECART au ciel attendu a cet endroit, et on remplace
    # d'autant. Un vrai ciel ne bouge pas, une brindille disparait, et le demi
    # pixel de bord se resorbe tout seul au prorata.
    ecart = np.abs(a - fond).max(axis=2)
    a_effacer = dedans & (ecart > SEUIL_ECART)
    if not a_effacer.any():
        return a.astype(np.uint8), 0

    # LA REGLE « UNE PLANTE N'EST PAS ENRACINEE A DEUX ENDROITS » A ETE
    # ESSAYEE ET RETIREE. Etendre l'effacement a toute la masse connexe devait
    # supprimer les houppiers flottants — les arbres dont on efface le pied.
    # Mais la masse est definie par « pas du ciel », ce qui englobe la route,
    # le beton et l'herbe : la composante connexe couvre alors tout le bas de
    # l'image. Mesure sur PM3 : 53,8 % de l'image effacee au lieu de 3,9 %.
    #
    # Pour que la regle tienne, il faudrait une definition de la VEGETATION
    # qui exclue le sol nu, et une limite laterale qui vienne de l'enceinte et
    # non de la presence du rendu. Les deux manquent.

    # Poids proportionnel a l'ecart, borne a 1 : un demi-pixel de branche est
    # remplace a moitie, ce qui est exactement ce qu'il est.
    poids = np.where(dedans, np.clip((ecart - SEUIL_ECART / 2) / SEUIL_ECART,
                                     0.0, 1.0), 0.0)
    poids = ndimage.gaussian_filter(poids, adouci)[..., None]
    out = np.clip(poids * fond + (1 - poids) * a, 0, 255)

    n = int((poids[..., 0] > 0.5).sum())
    if verbose:
        pur = ecart[support]
        print(f"  defrichement par ecart au fond local : {n} px remplaces a "
              f"plus de moitie ({n / (H * W):.1%} de l'image) ; sur du ciel "
              f"lisible l'ecart median vaut {np.median(pur):.1f} niveau(x), "
              f"soit {100 * (pur > SEUIL_ECART).mean():.0f} % au dessus du "
              f"seuil de {SEUIL_ECART:.0f}")
    return out.astype(np.uint8), n


def defricher_au_ciel(a, sil, bas, fondu=FONDU, verbose=True):
    """Remplace la vegetation a defricher par le ciel, sur toute son epaisseur.

    La bande va de l'ENVELOPPE de la vegetation au haut du projet : au-dessous,
    le rendu couvre. Le remplissage vient d'un modele de ciel ajuste sur le
    ciel reel de la photo — c'est de l'extrapolation, pas de la creation.
    """
    a = np.asarray(a, dtype=float)
    H, W = a.shape[:2]
    coef = _modele_ciel(a, sil)
    if coef is None:
        if verbose:
            print("  defrichement : pas assez de ciel pour ajuster un modele")
        return a.astype(np.uint8), 0
    haut = enveloppe(sil)
    out = a.copy()
    ecrits = 0
    for x in range(W):
        if not np.isfinite(bas[x]):
            continue
        h, b = int(max(0, haut[x])), int(min(H, bas[x]))
        if b <= h:
            continue
        lignes = np.arange(h, b, dtype=float)
        A = np.column_stack([np.full_like(lignes, x), lignes, lignes ** 2,
                             np.ones_like(lignes)])
        ciel = A @ coef
        poids = np.clip((lignes - h) / max(fondu, 1), 0.0, 1.0)[:, None]
        out[h:b, x, :] = poids * ciel + (1 - poids) * a[h:b, x, :]
        ecrits += b - h
    out = np.clip(out, 0, 255)
    if verbose:
        print(f"  defrichement : {ecrits} px reecrits "
              f"({ecrits / (H * W):.1%} de l'image)")
    return out.astype(np.uint8), ecrits


def prolonger_ciel(a, sil, bas, appui=APPUI, lissage=LISSAGE, fondu=FONDU,
                   verbose=True):
    """Réécrit la bande [sil[x], bas[x]] en prolongeant le ciel de la colonne.

    `sil` est la silhouette contre le ciel, `bas` la ligne jusqu'où descendre —
    en pratique le haut du projet, puisque au-dessous le rendu couvre tout.
    NaN dans `bas` : la colonne n'est pas concernée.
    """
    a = np.asarray(a, dtype=float)
    H, W = a.shape[:2]
    pente = np.zeros((W, 3))
    ordonnee = np.zeros((W, 3))
    utiles = np.zeros(W, bool)

    for x in range(W):
        s = int(sil[x])
        haut = max(0, s - appui)
        if s - haut < 12 or not np.isfinite(bas[x]) or bas[x] <= s:
            continue
        lignes = np.arange(haut, s - 3, dtype=float)
        bloc = a[haut:s - 3, x, :]
        if len(lignes) < 12:
            continue
        # moindres carres par canal, sur la seule variable verticale
        A = np.column_stack([lignes, np.ones_like(lignes)])
        coef, *_ = np.linalg.lstsq(A, bloc, rcond=None)
        pente[x], ordonnee[x] = coef[0], coef[1]
        utiles[x] = True

    if not utiles.any():
        if verbose:
            print("  prolongement du ciel : aucune colonne exploitable")
        return a.astype(np.uint8), 0

    # LISSAGE EN TRAVERS, sur les colonnes utiles seulement : une colonne sans
    # ajustement ne doit pas tirer ses voisines vers zero.
    for tab in (pente, ordonnee):
        for c in range(3):
            v = tab[:, c].copy()
            v[~utiles] = np.interp(np.flatnonzero(~utiles),
                                   np.flatnonzero(utiles), v[utiles])
            tab[:, c] = ndimage.uniform_filter1d(v, lissage)

    out = a.copy()
    ecrits = 0
    for x in np.flatnonzero(utiles):
        s, b = int(sil[x]), int(min(H, bas[x]))
        if b <= s:
            continue
        lignes = np.arange(s, b, dtype=float)[:, None]
        ciel = pente[x][None, :] * lignes + ordonnee[x][None, :]
        # fondu au raccord, pour que la reprise ne se lise pas comme un trait
        poids = np.clip((lignes - s) / max(fondu, 1), 0.0, 1.0)
        out[s:b, x, :] = poids * ciel + (1 - poids) * a[s:b, x, :]
        ecrits += b - s

    out = np.clip(out, 0, 255)
    if verbose:
        print(f"  prolongement du ciel : {int(utiles.sum())} colonnes, "
              f"{ecrits} px reecrits ({ecrits / (H * W):.1%} de l'image)")
    return out.astype(np.uint8), ecrits
