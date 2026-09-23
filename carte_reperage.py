#!/usr/bin/env python3
"""Lit une carte de reperage d'etude d'impact : georeferencement et prises de vue.

Toutes les etudes d'impact portent la meme figure — une copie d'ecran
d'orthophoto, l'emprise du projet en rouge, et une fleche rouge numerotee par
point de vue. C'est souvent la SEULE source de position des prises de vue : les
photos de reportage arrivent sans GPS (a Sarnois, les quatre cliches qui
portent un bloc GPS l'ont vide), et le bureau d'etudes ne livre pas de tableau
de coordonnees.

GEOREFERENCEMENT. On ne peut pas caler la carte sur l'emprise du plan : entre
l'etude d'impact et l'implantation retenue, le projet a bouge — a Sarnois
IND10b n'occupe que le lobe sud du polygone dessine. On cale donc sur le FOND,
qui n'a pas bouge, par correlation avec l'orthophoto IGN. L'echelle vient de la
barre graphique, l'orientation est le nord ; il ne reste qu'une translation.

Le meme calage sert a poser un fond d'export Helioscope, qui vient en repere
local avec son echelle exacte : il suffit alors de passer `surcharge=False`,
puisqu'il n'y a rien de dessine dessus. Attention, le pic est plus bas quand
les deux images viennent de capteurs differents — 8,7 fois le fond a Gannay
(Google/Maxar contre IGN) contre 16 a Sarnois (IGN contre IGN).

CE QUI MARCHE ET CE QUI NE MARCHE PAS. Les POSITIONS sortent bonnes — a
Sarnois la nappe du DXF se projette exactement dans son ilot parcellaire. Les
DIRECTIONS, non : sur ces chevrons les deux coins de la base sont plus loin du
centre que la pointe, et meme en jugeant le sens sur la largeur des extremites,
la moitie des fleches sort a 180 degres — l'ecart median a la direction du
projet valait 99 degres. On ne rend donc PAS de direction : l'audit
d'occultation n'en a pas besoin, puisque ce qui s'interpose entre un point de
vue et le projet ne depend pas du cadrage.
"""
import io
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

HERE = Path(__file__).resolve().parent


def _gradient(a, masque=None):
    """Module du gradient, centre reduit ; les zones masquees sont mises a zero."""
    g = np.array(Image.fromarray(a.astype(np.uint8)).convert("L")).astype(float)
    gy, gx = np.gradient(ndimage.gaussian_filter(g, 1.0))
    m = np.hypot(gx, gy)
    if masque is not None:
        m = np.where(masque, 0.0, m)
    m = m - m.mean()
    s = m.std()
    return m / s if s > 1e-9 else m


def barre_echelle(carte, longueur_m, fraction=(0.88, 0.0, 1.0, 0.30)):
    """Metres par pixel, lus sur la barre graphique.

    `longueur_m` est la valeur imprimee au bout de la barre. `fraction` delimite
    la zone ou la chercher, en (y0, x0, y1, x1) relatifs.
    """
    a = np.array(Image.open(carte).convert("RGB")).astype(int)
    H, W = a.shape[:2]
    y0, x0, y1, x1 = fraction
    zone = a[int(H * y0):int(H * y1), int(W * x0):int(W * x1)]
    noir = zone.max(axis=2) < 60
    lab, n = ndimage.label(noir)
    if not n:
        raise RuntimeError("barre d'echelle introuvable")
    i = int(np.argmax(ndimage.sum(noir, lab, range(1, n + 1)))) + 1
    xs = np.nonzero(lab == i)[1]
    return longueur_m / float(xs.max() - xs.min())


def _surcharge(carte_rgb):
    """Masque des elements DESSINES sur la carte, a exclure de la correlation."""
    R, G, B = carte_rgb[..., 0], carte_rgb[..., 1], carte_rgb[..., 2]
    m = (((R > 140) & (G < 100) & (B < 100))
         | ((B > 140) & (R < 110) & (G < 140))
         | (carte_rgb.min(axis=2) > 225)
         | (carte_rgb.max(axis=2) < 55))
    return ndimage.binary_dilation(m, np.ones((7, 7)))


def correler(grand, petit, verbose=True):
    """Decalage (dy, dx) de `petit` dans `grand`, par correlation FFT normalisee.

    DEUX PRECAUTIONS, apprises sur le fond Helioscope de Gannay. La premiere :
    ne chercher le pic que parmi les decalages OU LA PETITE IMAGE TIENT
    ENTIEREMENT dans la grande. Sans cela le maximum tombe dans le repli de la
    FFT — a Gannay il sortait a dx = -500, soit la moitie de la carte hors
    champ. Tant que les deux images viennent de la meme orthophoto le vrai pic
    domine malgre tout ; des que ce sont deux capteurs et deux dates
    differents, l'artefact gagne.

    La seconde : diviser par la norme locale de la grande image. Une
    correlation brute prefere les zones de forte energie — un village, une
    lisiere — a la zone qui ressemble vraiment.
    """
    H, W = grand.shape
    h, w = petit.shape
    if h > H or w > W:
        raise RuntimeError(f"la carte ({w}x{h}) deborde l'orthophoto ({W}x{H})")
    p = np.zeros_like(grand)
    p[:h, :w] = petit
    num = np.fft.irfft2(np.fft.rfft2(grand) * np.conj(np.fft.rfft2(p)), s=(H, W))
    # energie de la grande image sous la fenetre, par le meme chemin
    fen = np.zeros_like(grand)
    fen[:h, :w] = 1.0
    e = np.fft.irfft2(np.fft.rfft2(grand ** 2) * np.conj(np.fft.rfft2(fen)), s=(H, W))
    C = num / np.sqrt(np.maximum(e, 1e-9))
    valide = np.zeros_like(C, bool)
    valide[:H - h + 1, :W - w + 1] = True
    C = np.where(valide, C, -np.inf)
    dy, dx = divmod(int(np.argmax(C)), W)
    fini = C[valide]
    net = float(C[dy, dx]) / max(float(np.median(np.abs(fini))), 1e-9)
    if verbose:
        print(f"  correlation : dy={dy} dx={dx} sur {W - w + 1}x{H - h + 1} "
              f"decalages possibles, pic a {net:.1f}x le fond")
    return dy, dx, net


def georeferencer(carte, echelle, centre, cartouche=(0.78, 0.74),
                  marge=0.85, seuil=6.0, surcharge=True, verbose=True):
    """Cale la carte sur l'orthophoto IGN. Rend le coin haut-gauche en L93.

    `centre` : un point (E, N) quelconque du secteur, pour aller chercher la
    bonne dalle — typiquement le barycentre du plan.
    """
    import terrain
    a = np.array(Image.open(carte).convert("RGB")).astype(int)
    Hc, Wc = a.shape[:2]
    # `surcharge` n'a de sens que pour une carte DESSINEE. Sur un simple fond
    # d'orthophoto — celui qu'exporte Helioscope, par exemple — le masque
    # mange de la vegetation et des toits, et le pic tombe : mesure a Gannay,
    # 4,0 fois le fond avec, 8,7 sans.
    if surcharge:
        sur = _surcharge(a)
        fy, fx = cartouche
        sur[int(Hc * fy):, int(Wc * fx):] = True         # legende
        sur[int(Hc * 0.90):, :int(Wc * 0.30)] = True     # barre d'echelle
        sur[:int(Hc * 0.10), :int(Wc * 0.08)] = True     # fleche nord
    else:
        sur = None

    bbox = (centre[0] - Wc * echelle * marge, centre[1] - Hc * echelle * marge,
            centre[0] + Wc * echelle * marge, centre[1] + Hc * echelle * marge)
    brut, bb, _, _ = terrain.charger_ortho(bbox, resolution=echelle,
                                           max_px=4000, verbose=verbose)
    ortho = np.array(Image.open(io.BytesIO(brut)).convert("RGB")).astype(int)
    res_E = (bb[2] - bb[0]) / ortho.shape[1]
    res_N = (bb[3] - bb[1]) / ortho.shape[0]

    dy, dx, net = correler(_gradient(ortho), _gradient(a, sur), verbose=verbose)
    if net < seuil:
        raise RuntimeError(f"calage douteux (pic a {net:.1f}x le fond, "
                           f"seuil {seuil}) — verifier l'echelle et le secteur")
    return dict(E0=bb[0] + dx * res_E, N0=bb[3] - dy * res_N,
                res_E=res_E, res_N=res_N, nettete=net, taille=(Wc, Hc))


def fleches(carte, rayon=13, aire_min=60, cartouche=(0.78, 0.74)):
    """Positions des fleches rouges, en pixels de la carte.

    Les fleches sont des chevrons PLEINS ; les numeros, des glyphes fins. Une
    erosion separe donc les deux sans seuil d'aire a regler, y compris quand un
    numero touche sa fleche. Elle FRAGMENTE en revanche les chevrons la ou ils
    s'amincissent : on regroupe les noyaux voisins, faute de quoi une meme
    fleche est comptee six fois.
    """
    a = np.array(Image.open(carte).convert("RGB")).astype(int)
    R, G, B = a[..., 0], a[..., 1], a[..., 2]
    rouge = (R > 150) & (G < 90) & (B < 90)
    H, W = rouge.shape
    fy, fx = cartouche
    rouge[int(H * fy):, int(W * fx):] = False
    # l'emprise du projet est un trait FIN et long : l'erosion l'efface, alors
    # qu'elle laisse un noyau a chaque chevron.
    coeur = ndimage.binary_erosion(rouge, np.ones((5, 5)))
    lab, n = ndimage.label(coeur)
    grappes = []
    for cy, cx in (ndimage.center_of_mass(coeur, lab, i) for i in range(1, n + 1)):
        for g in grappes:
            if any(abs(cy - y) < rayon and abs(cx - x) < rayon for y, x in g):
                g.append((cy, cx))
                break
        else:
            grappes.append([(cy, cx)])
    ys, xs = np.nonzero(rouge)
    out = []
    for g in grappes:
        cy = float(np.mean([y for y, _ in g]))
        cx = float(np.mean([x for _, x in g]))
        pres = (np.abs(ys - cy) <= rayon) & (np.abs(xs - cx) <= rayon)
        if pres.sum() < aire_min:
            continue
        out.append(dict(x=float(xs[pres].mean()), y=float(ys[pres].mean()),
                        aire=int(pres.sum())))
    return sorted(out, key=lambda f: (f["y"], f["x"]))


def points_de_vue(carte, longueur_barre, centre, numeros=None, verbose=True):
    """Prises de vue d'une carte de reperage, en Lambert 93.

    Les fleches sortent rangees du NORD au SUD. `numeros` donne, dans cet
    ordre, le numero imprime sur la carte en face de chacune.

    POURQUOI A LA MAIN. Les numeros sont des glyphes de douze pixels de haut :
    aucun OCR n'y est fiable, et une erreur de numerotation fausserait
    silencieusement tout l'audit. On les releve donc une fois a l'oeil, et
    `apercu()` reprojette le resultat sur la carte pour verifier d'un coup
    d'oeil que la correspondance tient.
    """
    ech = barre_echelle(carte, longueur_barre)
    if verbose:
        print(f"  echelle : {ech:.3f} m/px (barre de {longueur_barre:.0f} m)")
    g = georeferencer(carte, ech, centre, verbose=verbose)
    out = []
    for k, f in enumerate(fleches(carte)):
        out.append(dict(num=int(numeros[k]) if numeros else k + 1,
                        E=g["E0"] + f["x"] * g["res_E"],
                        N=g["N0"] - f["y"] * g["res_N"],
                        x=f["x"], y=f["y"]))
    if verbose:
        print(f"  {len(out)} prises de vue")
        if numeros and len(numeros) != len(out):
            print(f"  ATTENTION : {len(numeros)} numeros pour {len(out)} fleches")
    return out, g


def apercu(carte, vues, sortie, extras=()):
    """Reprojette les vues numerotees sur la carte, pour verification a l'oeil.

    C'est le garde-fou du releve manuel des numeros : si une pastille ne tombe
    pas sur sa fleche, la correspondance est fausse et cela se voit aussitot.
    """
    from PIL import ImageDraw
    im = Image.open(carte).convert("RGB")
    d = ImageDraw.Draw(im)
    for v in vues:
        x, y = v["x"], v["y"]
        d.ellipse([x - 9, y - 9, x + 9, y + 9], outline=(0, 255, 255), width=2)
        d.text((x + 11, y - 6), str(v["num"]), fill=(0, 255, 255))
    for x0, y0, x1, y1, coul in extras:
        d.line([x0, y0, x1, y1], fill=coul, width=1)
    im.save(sortie)
    return sortie


if __name__ == "__main__":
    import lecture_dxf
    import montage as M
    scn = lecture_dxf.lire(M.DXF)
    q = np.array([t.q for t in scn.tables]).reshape(-1, 3)
    carte = sys.argv[1] if len(sys.argv) > 1 else str(
        HERE / "exemples/sarnois-B/reportage-BE/carte_localisation_BE.png")
    vues, _ = points_de_vue(carte, 500.0, (q[:, 0].mean(), q[:, 1].mean()))
    for v in vues:
        print(f"{v['num']:3d}  E={v['E']:.0f}  N={v['N']:.0f}")
