#!/usr/bin/env python3
"""Garde-fou de prise de vue — étape 0 de la chaîne photomontage.

CE QUE CETTE PAGE FAIT, ET CE QU'ELLE NE FAIT PAS
--------------------------------------------------
Elle répond à une seule question : **cette photo peut-elle donner un
photomontage d'insertion paysagère ?** Elle ne cale rien, ne masque rien, ne
rend rien. C'est voulu.

Le rendu est la seule étape lente de la chaîne — deux à trois minutes — et c'est
la seule où il n'y a rien à juger. Toutes les décisions sont en amont et coûtent
des secondes. Une interface qui ferait itérer un chef de projet sur des rendus
déplacerait la lenteur sans la supprimer ; celle-ci trie avant, là où c'est
gratuit.

Le pilote de Saint-Cyr a coûté quatre allers-retours et n'a rien livré, pour une
raison qui tient en un nombre : le premier ouvrage visible était à 2,4 m et
9,4 m, contre 20 m sur les vues de Sarnois qui ont été livrées. Cette page
l'aurait dit en une seconde, sans photo, avant le déplacement.

Lancement :
    streamlit run app.py
"""
import tempfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                  # noqa: E402
import numpy as np                                               # noqa: E402
import streamlit as st                                           # noqa: E402

import camera                                                    # noqa: E402
import garde_prise_de_vue as G                                   # noqa: E402
import lecture_dxf                                               # noqa: E402

st.set_page_config(page_title="Prise de vue — photomontage",
                   page_icon="◎", layout="wide")

LIBELLES = {
    "distance_premier_ouvrage_visible_m":
        "Premier ouvrage visible",
    "distance_premiere_table_visible_m": "Première table visible",
    "distance_mediane_projet_visible_m": "Distance médiane du projet visible",
    "distance_max_projet_visible_m": "Point du projet le plus lointain",
    "flou_position_px": "Déplacement dû à l'incertitude de position",
    "flou_position_pct_hauteur": "  …en % de la hauteur d'image",
    "part_ouvrage_proche_pct": "Hauteur apparente d'une clôture de 2 m",
    "part_projet_pct": "Hauteur apparente d'une table de 3 m",
    "champ_horizontal_deg": "Champ horizontal",
    "emprise_projet_deg": "Emprise angulaire du projet",
    "part_projet_dans_le_cadre_pct": "Part du projet dans le cadre",
    "azimut_evalue_deg": "Azimut évalué",
    "sigma_position_m": "Incertitude de position retenue",
}
UNITES = {"_m": " m", "_px": " px", "_pct": " %", "_deg": "°",
          "_pct_hauteur": " %"}


@st.cache_data(show_spinner="Lecture du plan…")
def _lire_plan(octets, nom):
    """Lit un DXF téléversé. Mis en cache : un plan pèse plusieurs Mo."""
    with tempfile.NamedTemporaryFile(suffix=Path(nom).suffix, delete=False) as f:
        f.write(octets)
        chemin = f.name
    try:
        scn = lecture_dxf.lire(chemin)
    finally:
        Path(chemin).unlink(missing_ok=True)
    return scn


@st.cache_data(show_spinner=False)
def _lire_photo(octets, nom):
    with tempfile.NamedTemporaryFile(suffix=Path(nom).suffix, delete=False) as f:
        f.write(octets)
        chemin = f.name
    try:
        return G.depuis_photo(chemin)
    finally:
        Path(chemin).unlink(missing_ok=True)


def _unite(cle):
    for suffixe, u in UNITES.items():
        if cle.endswith(suffixe):
            return u
    return ""


def carte(scn, est, nord, azimut, champ_h, bande):
    """Vue de dessus : le site, l'oeil, son cadre, et la bande recommandee."""
    pts = G.points_projet(scn, pas=3.0)
    fig, ax = plt.subplots(figsize=(6.2, 6.2))
    ax.set_aspect("equal")

    # La bande de distance recommandee, en couronne autour de l'oeil.
    for r, style in ((bande[0], "-"), (bande[1], "--")):
        t = np.linspace(0, 2 * np.pi, 361)
        ax.plot(r * np.sin(t), r * np.cos(t), style, lw=1.0,
                color="#2e7d32", alpha=0.7)

    ax.scatter(pts[:, 0] - est, pts[:, 1] - nord, s=1.2, c="#90a4ae",
               label="projet")
    # Le cadre, en secteur.
    for signe in (-1, 1):
        a = np.radians(azimut + signe * champ_h / 2)
        L = max(bande[1], 1.0)
        ax.plot([0, L * np.sin(a)], [0, L * np.cos(a)], "-", lw=1.2,
                color="#1565c0")
    ax.scatter([0], [0], s=90, marker="o", c="#c62828", zorder=5,
               label="point de vue")

    d = np.hypot(pts[:, 0] - est, pts[:, 1] - nord)
    lim = float(min(max(d.max() * 1.05, bande[1] * 1.1), 3 * bande[1]))
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.set_xlabel("est (m)")
    ax.set_ylabel("nord (m)")
    ax.grid(alpha=0.25)
    ax.legend(loc="upper right", fontsize=8, framealpha=0.9)
    ax.set_title(f"cercles verts : {bande[0]:.0f} et {bande[1]:.0f} m,\n"
                 "la bande où le point de vue est exploitable", fontsize=9)
    fig.tight_layout()
    return fig


st.title("Le point de vue est-il exploitable ?")
st.caption(
    "Aucun rendu, aucun calage : cette page trie les prises de vue **avant** "
    "qu'on y passe du temps. Elle répond en une seconde, et sans la photo si "
    "l'on connaît la position.")

with st.sidebar:
    st.header("Le plan")
    f_plan = st.file_uploader("Plan DXF du projet", type=["dxf"])

    st.header("Le point de vue")
    mode = st.radio("Origine de la position", ["Photo géolocalisée",
                                               "Coordonnées saisies"])
    st.divider()
    origine = st.radio(
        "Comment la position est-elle connue ?",
        ["GPS de téléphone (± 7 m)", "Point relevé (± 0,5 m)"],
        help="L'incertitude décide si la pose est déterminée : l'erreur au "
             "sol se traduit en pixels en carré inverse de la distance.")
    sigma = (G.SIGMA_TELEPHONE if origine.startswith("GPS")
             else G.SIGMA_RELEVE)
    oeil = st.number_input("Hauteur de l'œil (m)", 1.0, 3.0, 1.60, 0.05)

if f_plan is None:
    st.info("Téléversez le plan DXF du projet pour commencer.")
    st.stop()

try:
    scn = _lire_plan(f_plan.getvalue(), f_plan.name)
except Exception as e:                                    # noqa: BLE001
    st.error(f"Le plan n'a pas pu être lu : {e}")
    st.stop()

st.success(f"Plan lu : {len(scn.tables)} tables, "
           + ", ".join(f"{len(v)} {k}" for k, v in sorted(scn.lignes.items())))

donnees, azimut = None, None
if mode == "Photo géolocalisée":
    f_photo = st.file_uploader("Photo (EXIF avec GPS et focale)",
                               type=["jpg", "jpeg", "png", "tif", "tiff"])
    if f_photo is None:
        st.info("Téléversez la photo, ou passez en saisie de coordonnées.")
        st.stop()
    try:
        donnees = _lire_photo(f_photo.getvalue(), f_photo.name)
    except ValueError as e:
        st.error(f"{e}\n\nPassez en « Coordonnées saisies » pour poursuivre.")
        st.stop()
    c1, c2, c3 = st.columns(3)
    c1.metric("Position", f"{donnees['est']:.0f} / {donnees['nord']:.0f}")
    c2.metric("Image", f"{donnees['largeur']} × {donnees['hauteur']}")
    c3.metric("Focale", f"{donnees['f_px']:.0f} px")
    azimut = st.number_input(
        "Azimut de visée (°), si connu", -1.0, 360.0, -1.0, 1.0,
        help="Laissez -1 si le cap n'est pas connu : le verdict portera "
             "alors sur la meilleure visée possible depuis ce point.")
    azimut = None if azimut < 0 else azimut
else:
    c1, c2 = st.columns(2)
    est = c1.number_input("Est (Lambert 93)", value=622879.0, format="%.2f")
    nord = c2.number_input("Nord (Lambert 93)", value=6750697.0, format="%.2f")
    c1, c2, c3 = st.columns(3)
    largeur = c1.number_input("Largeur d'image (px)", 320, 12000, 2040)
    hauteur = c2.number_input("Hauteur d'image (px)", 240, 12000, 1530)
    f35 = c3.number_input("Focale équivalent 35 mm", 8.0, 200.0, 26.0, 0.5)
    az = st.number_input("Azimut de visée (°), si connu", -1.0, 360.0, -1.0, 1.0)
    azimut = None if az < 0 else az
    donnees = dict(est=est, nord=nord, largeur=int(largeur),
                   hauteur=int(hauteur),
                   f_px=camera.focale_px_depuis_exif(int(largeur), int(hauteur),
                                                     f35)[0])

try:
    v = G.evaluer(scn, azimut=azimut, hauteur_oeil=oeil, sigma=sigma, **donnees)
except ValueError as e:
    st.error(str(e))
    st.stop()

st.divider()
if v.exploitable:
    st.success("### Point de vue exploitable")
else:
    st.error("### Point de vue à reprendre")
    for m in v.motifs:
        st.markdown(f"- {m}")

for r in v.reserves:
    st.warning(r, icon="!")

st.markdown(
    f"**Distance recommandée au premier ouvrage visible : "
    f"{v.bande[0]:.0f} à {v.bande[1]:.0f} m.** "
    f"En deçà, la clôture fait le premier plan et l'incertitude de position "
    f"({sigma:.1f} m) n'est plus rattrapable ; au-delà, le projet n'est plus "
    f"lisible.")

gauche, droite = st.columns([1, 1])
with gauche:
    st.pyplot(carte(scn, donnees["est"], donnees["nord"],
                    v.mesures.get("azimut_evalue_deg", 0.0),
                    v.mesures["champ_horizontal_deg"], v.bande))
with droite:
    st.subheader("Ce qui a été mesuré")
    lignes = [{"mesure": LIBELLES.get(k, k),
               "valeur": f"{x:,.1f}{_unite(k)}".replace(",", " ")}
              for k, x in v.mesures.items()]
    st.dataframe(lignes, hide_index=True, use_container_width=True)

with st.expander("Pourquoi ces seuils"):
    st.markdown(f"""
Ils ne sont pas choisis a priori : ils sont calés sur quatre vues réelles,
**deux livrées** et **deux abandonnées**.

| vue | premier ouvrage visible | clôture de 2 m | déplacement GPS |
|---|---|---|---|
| Sarnois PV9 — livré | 21,4 m | 8,6 % | 2,3 % |
| Sarnois PV10 — livré | 20,0 m | 9,2 % | 2,6 % |
| Saint-Cyr PV3 — abandonné | 9,4 m | 18,8 % | 13,6 % |
| Saint-Cyr PV4 — abandonné | 2,4 m | 75,3 % | 191,7 % |

Les seuils sont posés là où l'écart est le plus large :
**{100 * G.PART_PROCHE_MAX:.0f} %** pour la hauteur apparente de la clôture,
**{100 * G.FLOU_MAX:.0f} %** pour le déplacement dû à l'incertitude de position.

Le déplacement varie en **carré inverse de la distance** : c'est pour cela
qu'il explose de 2 % à 192 % entre 20 m et 2,4 m, et c'est la vraie raison pour
laquelle les mêmes outils marchent à Sarnois et échouent à Saint-Cyr.

**Ce qui n'est pas un défaut :** que le projet ne tienne pas entier dans le
cadre. Sarnois PV10 n'en montre que 26 % et a été livré — une centrale de
quatre hectares vue de son bord couvre 359°, et c'est bien pour cela qu'un
dossier porte plusieurs vues.
""")
