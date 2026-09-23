#!/usr/bin/env python3
"""Ingere des dossiers de permis de construire et en tire des paires avant/apres.

Sert a alimenter `charte_rendu.py` a partir de dossiers reels plutot que de
fichiers ranges a la main. Le script :

  1. parcourt un dossier, ouvre les PDF et recupere les images assez grandes
     pour etre des planches de photomontage ;
  2. reconnait les paires avant / apres : meme dimensions, et surtout une image
     identique PARTOUT sauf dans une bande — c'est la signature d'un montage,
     par opposition a deux photos differentes ;
  3. mesure chaque paire avec `charte_rendu.mesurer` ;
  4. ecrit un tableau et une charte, si possible CONDITIONNEE par les metadonnees
     (lumiere, distance, angle aux rangees), car une valeur moyenne unique cache
     des ecarts du simple au double entre situations.

Usage :
    python ingerer_references.py <dossier> [--sortie charte_dossiers.json]
"""
import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

import charte_rendu as ch

MIN_PIXELS = 700_000          # une planche de photomontage, pas un logo
MIN_COTE = 700


_COMPTEUR = [0]


def images_du_pdf(chemin, dossier_sortie, journal=None):
    """Extrait les images assez grandes d'un PDF. Renvoie les chemins ecrits.

    Les fichiers sont nommes court : sous Windows, un nom derive du PDF fait
    depasser la limite de 260 caracteres des que le dossier est profond, et
    l'ecriture echoue sans que la cause soit evidente.
    """
    try:
        import fitz
    except ImportError:
        print("  PyMuPDF absent : pip install pymupdf", file=sys.stderr)
        return []
    out = []
    doc = fitz.open(chemin)
    for ip in range(len(doc)):
        for k, info in enumerate(doc[ip].get_images(full=True)):
            xref = info[0]
            try:
                px = fitz.Pixmap(doc, xref)
            except Exception:
                continue
            if px.width * px.height < MIN_PIXELS or min(px.width, px.height) < MIN_COTE:
                continue
            if px.n - px.alpha >= 4:
                px = fitz.Pixmap(fitz.csRGB, px)
            _COMPTEUR[0] += 1
            f = dossier_sortie / f"im{_COMPTEUR[0]:04d}.png"
            px.save(str(f))
            if journal is not None:
                journal[f.name] = f"{Path(chemin).name} p.{ip + 1}"
            out.append(f)
    doc.close()
    return out


def _vignette(f, cote=320):
    im = Image.open(f).convert("RGB")
    return np.array(im.resize((cote, int(cote * im.height / im.width)), Image.LANCZOS)).astype(float)


def apparier(fichiers, part_max=0.35, part_min=0.004, seuil=14):
    """Retient les couples identiques partout sauf sur une bande : avant / apres.

    Deux photos differentes du meme site diffèrent partout ; un montage ne diffère
    que la ou le projet a ete peint. C'est ce contraste qui sert de critere.
    """
    vign = {}
    for f in fichiers:
        try:
            vign[f] = _vignette(f)
        except Exception:
            pass
    paires = []
    cles = list(vign)
    for i in range(len(cles)):
        for j in range(i + 1, len(cles)):
            a, b = vign[cles[i]], vign[cles[j]]
            if a.shape != b.shape:
                continue
            diff = np.abs(a - b).max(axis=2)
            part = float((diff > seuil).mean())
            if not (part_min < part < part_max):
                continue
            # l'avant est celui dont la bande modifiee est la plus claire
            m = diff > seuil
            la, lb = a[m].mean(), b[m].mean()
            avant, apres = (cles[i], cles[j]) if la > lb else (cles[j], cles[i])
            paires.append({"avant": avant, "apres": apres, "part_modifiee": round(part, 4)})
    # une image ne sert que dans une paire : on garde les plus franches
    paires.sort(key=lambda p: p["part_modifiee"])
    vus, gardees = set(), []
    for p in paires:
        if p["avant"] in vus or p["apres"] in vus:
            continue
        vus.add(p["avant"]); vus.add(p["apres"])
        gardees.append(p)
    return gardees


def conditionner(mesures, conditions):
    """Charte par condition (lumiere, distance...) plutot qu'une moyenne unique."""
    groupes = {}
    for nom, m in mesures.items():
        groupes.setdefault(conditions.get(nom, "non renseigne"), {})[nom] = m
    return {c: ch.resumer(g) for c, g in groupes.items() if g}



# --------------------------------------------------------------- metadonnees

MOIS = ("janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet", "aout",
        "septembre", "octobre", "novembre", "decembre")
MOTIF_DATE = re.compile(
    r"(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4})"
    r"|(\d{1,2}\s+(?:" + "|".join(MOIS) + r")\s+\d{4})", re.I)
MOTIF_HEURE = re.compile(r"([01]?\d|2[0-3])\s*[h:]\s*([0-5]\d)")


def metadonnees_image(f):
    """Date, heure et GPS d'une image, s'ils ont survecu.

    Une planche exportee par un outil de rendu n'a en general plus rien : le
    re-encodage efface l'EXIF. L'etat initial, lui, peut l'avoir garde s'il
    vient directement de l'appareil et n'est pas passe par une mise en page.
    """
    out = {"date": None, "gps": None, "appareil": None}
    try:
        from PIL import ExifTags
        im = Image.open(f)
        ex = im.getexif()
        if not ex:
            return out
        noms = {ExifTags.TAGS.get(k, k): v for k, v in ex.items()}
        out["appareil"] = " ".join(str(noms[k]) for k in ("Make", "Model") if k in noms) or None
        ifd = ex.get_ifd(0x8769) or {}
        d = {ExifTags.TAGS.get(k, k): v for k, v in ifd.items()}
        out["date"] = d.get("DateTimeOriginal") or noms.get("DateTime")
        gps = ex.get_ifd(0x8825) or {}
        if gps and 2 in gps and 4 in gps:
            def dd(v, ref):
                x = float(v[0]) + float(v[1]) / 60 + float(v[2]) / 3600
                return -x if str(ref) in ("S", "W") else x
            out["gps"] = (round(dd(gps[2], gps.get(1, "N")), 6),
                          round(dd(gps[4], gps.get(3, "E")), 6))
    except Exception:
        pass
    return out


def dates_du_pdf(chemin, max_pages=None):
    """Dates et heures citees dans le texte du PDF, avec leur page.

    Dans un dossier de PC, la date de prise de vue est souvent ecrite dans la
    legende ou dans le chapitre paysage, meme quand l'EXIF a disparu. C'est
    exploitable : la date suffit a calculer la position du soleil.
    """
    try:
        import fitz
    except ImportError:
        return []
    out = []
    doc = fitz.open(chemin)
    for ip in range(len(doc) if max_pages is None else min(len(doc), max_pages)):
        t = doc[ip].get_text()
        for m in MOTIF_DATE.finditer(t):
            deb = max(0, m.start() - 60)
            ctx = " ".join(t[deb:m.end() + 40].split())
            h = MOTIF_HEURE.search(t[max(0, m.start() - 120):m.end() + 120])
            out.append({"page": ip + 1, "date": m.group(0),
                        "heure": f"{h.group(1)}h{h.group(2)}" if h else None,
                        "contexte": ctx[:110]})
    doc.close()
    return out


def rapport_metadonnees(racine, max_pdf_pages=None):
    """Tableau : ce que chaque fichier conserve comme date, heure et position."""
    lignes = []
    for f in sorted(Path(racine).rglob("*")):
        if f.is_dir() or "_images_extraites" in f.parts:
            continue
        if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".tif", ".tiff"):
            m = metadonnees_image(f)
            lignes.append({"fichier": str(f.relative_to(racine)), "type": "image", **m})
        elif f.suffix.lower() == ".pdf":
            d = dates_du_pdf(f, max_pdf_pages)
            lignes.append({"fichier": str(f.relative_to(racine)), "type": "pdf",
                           "date": d[0]["date"] if d else None,
                           "heure": next((x["heure"] for x in d if x["heure"]), None),
                           "gps": None, "appareil": None,
                           "dates_trouvees": len(d),
                           "exemples": [f"p.{x['page']} {x['date']}" for x in d[:4]]})
    return lignes



def par_projet(racine, min_pixels=None):
    """Apparie et mesure PROJET PAR PROJET.

    Un dossier par site : on n'apparie jamais deux sites differents. Le critere
    de bande modifiee les ecarterait sans doute, mais rien ne le garantit, et une
    fausse paire fausserait la charte sans se signaler.
    """
    seuil = min_pixels or MIN_PIXELS
    res = {}
    for d in sorted(x for x in Path(racine).iterdir() if x.is_dir()):
        gros = []
        for f in d.rglob("*"):
            if not f.is_file() or f.suffix.lower() not in (".jpg", ".jpeg", ".png"):
                continue
            try:
                im = Image.open(f)
                if im.width * im.height >= seuil:
                    gros.append(f)
            except Exception:
                pass
        if len(gros) < 2:
            print(f"  {d.name:32s} {len(gros):3d} images  -> rien a apparier", flush=True)
            continue
        paires = apparier(gros)
        mes = {}
        for q in paires:
            nom = f"{d.name}/{Path(q['apres']).name}"
            try:
                m, *_ = ch.mesurer(q["avant"], q["apres"])
            except Exception as e:
                print(f"     echec {nom} : {e}", flush=True)
                continue
            if "panneau_luminance_sur_ciel" in m:
                m["avant"] = str(Path(q["avant"]).name)
                mes[nom] = m
        res[d.name] = {"images": len(gros), "paires": len(paires), "mesures": mes}
        print(f"  {d.name:32s} {len(gros):3d} images  {len(paires):2d} paires  "
              f"{len(mes):2d} mesurees", flush=True)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dossier", help="dossier contenant les PC (PDF ou images)")
    ap.add_argument("--sortie", default="charte_dossiers.json")
    ap.add_argument("--par-projet", action="store_true",
                    help="un sous-dossier par site : apparie a l'interieur de chacun")
    ap.add_argument("--metadonnees", action="store_true",
                    help="n'affiche que le releve des dates, heures et GPS")
    ap.add_argument("--conditions", default=None,
                    help="CSV a deux colonnes : nom_de_fichier;condition")
    a = ap.parse_args()
    racine = Path(a.dossier)
    if a.metadonnees:
        lignes = rapport_metadonnees(racine)
        avec_date = [l for l in lignes if l.get("date")]
        avec_gps = [l for l in lignes if l.get("gps")]
        print(f"{len(lignes)} fichiers | date trouvee : {len(avec_date)} | GPS : {len(avec_gps)}")
        print()
        for l in lignes:
            print(f"  {l['fichier'][:56]:56s} {l['type']:5s} "
                  f"date={str(l.get('date'))[:19]:19s} heure={str(l.get('heure')):6s} "
                  f"gps={l.get('gps')}"
                  + (f"  ({l.get('dates_trouvees')} dates dans le texte : "
                     f"{', '.join(l.get('exemples', []))})" if l["type"] == "pdf" else ""))
        return
    if getattr(a, "par_projet", False):
        res = par_projet(racine)
        toutes = {k: v for pr in res.values() for k, v in pr["mesures"].items()}
        out = {"projets": res, "n_paires": len(toutes), "charte": ch.resumer(toutes)}
        Path(a.sortie).write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
        print()
        print(f"{len(toutes)} paires mesurees, charte ecrite dans {a.sortie}")
        for k, v in out["charte"].items():
            print(f"  {k:28s} {v}")
        return
    extrait = racine / "_images_extraites"
    extrait.mkdir(exist_ok=True)

    fichiers = []
    journal = {}
    for f in sorted(racine.rglob("*")):
        if f.is_dir() or "_images_extraites" in f.parts:
            continue
        if f.suffix.lower() == ".pdf":
            n = images_du_pdf(f, extrait, journal)
            print(f"  {f.name} : {len(n)} image(s) exploitable(s)")
            fichiers += n
        elif f.suffix.lower() in (".jpg", ".jpeg", ".png"):
            try:
                im = Image.open(f)
                if im.width * im.height >= MIN_PIXELS:
                    fichiers.append(f)
            except Exception:
                pass
    print(f"\n{len(fichiers)} images candidates")
    paires = apparier(fichiers)
    print(f"{len(paires)} paire(s) avant/apres reconnue(s)\n")

    conditions = {}
    if a.conditions and Path(a.conditions).exists():
        for ligne in Path(a.conditions).read_text(encoding="utf-8").splitlines()[1:]:
            if ";" in ligne:
                k, v = ligne.split(";")[:2]
                conditions[k.strip()] = v.strip()

    mesures = {}
    for p in paires:
        nom = Path(p["apres"]).name
        try:
            m, *_ = ch.mesurer(p["avant"], p["apres"])
        except Exception as e:
            print(f"  {nom} : echec ({e})")
            continue
        mesures[nom] = m
        print(f"  {nom[:52]:52s} lum/ciel {m.get('panneau_luminance_sur_ciel')}  "
              f"ombre {m.get('ombre_rapport')}  aeration {m.get('aeration_dans_la_bande')}")
    res = {"provenance": journal, "paires": [{k: str(v) for k, v in p.items()} for p in paires],
           "vues": mesures, "charte": ch.resumer(mesures),
           "charte_par_condition": conditionner(mesures, conditions)}
    Path(a.sortie).write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(f"\ncharte ecrite dans {a.sortie}")
    for k, v in res["charte"].items():
        print(f"  {k:28s} {v}")


if __name__ == "__main__":
    main()
