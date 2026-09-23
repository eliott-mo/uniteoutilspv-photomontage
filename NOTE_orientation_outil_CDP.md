# Note d'orientation : outil de photomontage PV pour les CDP

*Rédigée le 14/09/2026 à partir d'un panel de trois conceptions indépendantes, deux juges, deux protocoles de validation et une critique adversariale. Relue et corrigée par Claude (pas entre rangées mesuré, versions de bibliothèques, correction du point bas appliquée).*

## 1. Réponse courte

Forme recommandée : une page Streamlit locale « Préparer » (DXF BE + photo + carte IGN) qui génère, par point de vue, un fichier HTML autonome « Caler et rendre » dérivé du prototype Sarnois. Le CDP ne voit qu'un raccourci .bat, une page web et un fichier HTML qu'il peut envoyer par mail. Aucun GPU, aucune clé d'API, aucune installation au-delà du venv existant.

Pourquoi : c'est la seule forme livrable en 2 à 3 mois de travail de manager, elle réutilise le code validé, et l'équipe manipule déjà des HTML autonomes. Les deux juges la classent première (7/10 et 8/10).

Ce qu'on ne fait pas en V1 : pas de rendu Blender, pas de masquage IA, pas de finition générative, pas de calage automatique par détection. HOCH reste le prestataire des vues sensibles d'étude d'impact. Et surtout : rien n'est mis entre les mains des CDP avant la validation géométrique du chapitre 6, car le cœur n'est aujourd'hui que plausible, pas validé.

## 2. Ce que vit le CDP

| Étape | Où | Durée | Ce qu'il saisit ou vérifie |
|---|---|---|---|
| 0. Préparer la sortie | Streamlit | 10 min | Charge le DXF, clique les points de vue sur l'ortho IGN, imprime la fiche terrain (azimut, repères à chercher) |
| 1. Photographier | Terrain | 15 min/vue | Appareil natif, 1x, 4:3, paysage, bulle centrée, hauteur d'œil mesurée, pieds sur un point identifiable, 2 à 3 repères dans le champ, photo des pieds |
| 2. Transférer | Câble ou OneDrive | 2 min | Jamais WhatsApp/Teams (EXIF perdu). L'app refuse une photo sans EXIF, en 9:16 ou en zoom |
| 3. Préparer la vue | Streamlit | 5 min | Corrige la position caméra sur l'ortho, confirme hauteur d'œil, point bas/haut, clôture ; coche les repères ; clic « Générer » |
| 4. Caler | HTML | 5 min | Clique 3 repères minimum dans la photo (loupe 4x). Le solveur affiche les résidus : vert < 5 px, rouge > 15 px |
| 5. Habiller | HTML | 5 à 15 min | Variante sans / avec mesures, ombres, brume, polygones de masquage de la végétation existante |
| 6. Exporter | HTML | 1 min | PNG avant / après sans / après avec mesures, filaire de contrôle, calage.json, journal.json |
| 7. Planche | Streamlit | 2 min | Planche A3 avec carte, cartouche (L93, focale, résidus, méthode), PNG et PDF |

Total hors terrain : 20 à 40 min par vue. Quand le BE sort un nouvel indice, le calage.json se recharge et on régénère sans recaler.

## 3. Architecture retenue

Tout tourne sur le portable Windows 11 (Core Ultra 5, 32 Go, sans GPU). Internet uniquement pour le fond IGN Géoplateforme (WMTS, sans clé) et Overpass OSM (repères). À installer : PyYAML seulement ; le reste est déjà présent.

| Composant | Technologies exactes | Jours |
|---|---|---|
| C1 Extraction DXF générique, scene.json en coordonnées locales | ezdxf 1.4 (virtual_entities), numpy, scipy (TIN), shapely, PyYAML | 3 |
| C2 Lecture photo, caméra initiale | Pillow (EXIF, exif_transpose), pyproj EPSG:2154, pvlib | 1 |
| C3 Streamlit Préparer + fiche terrain | streamlit, streamlit-folium, WMTS IGN Géoplateforme, requests vers Overpass | 4 |
| C4 HTML : calage par repères, solveur | JS vanilla, canvas 2D, moindres carrés 4 paramètres ; contrôle croisé Python cv2.solvePnP + scipy.optimize.least_squares | 4 |
| C5 Rendu schématique propre, haies en sprites photographiés | JS canvas 2D, tri du peintre | 5 |
| C6 Masquage végétation (polygones + GrabCut) | JS clip, cv2.grabCut CPU | 2 |
| C7 Exports, planche, journal.json, cartouche | canvas.toBlob, Pillow, hashlib | 3 |
| C8 Validation géométrique (chapitre 6) | pytest, cv2, terrain | 10 |
| C9 Packaging, guide, formation 1 h | venv, .bat, PDF | 2 |
| **Total** | | **34** |

Désaccord entre juges sur l'effort : 25 jours annoncés par la conception, 30 à 35 jours jugés réalistes par le second juge (la carte interactive et le style de rendu débordent toujours). Je retiens 34 jours, validation comprise. Deux fichiers pivots sont conçus dès le départ (scene.json en coordonnées locales, calage.json) pour qu'un moteur Blender se branche en phase 2 sans toucher au parcours CDP.

## 4. Où l'IA intervient, où elle n'intervient pas

Dans le produit V1 : aucune IA dans le chemin critique. Le calage est un solveur déterministe, le rendu est vectoriel, le masquage est manuel avec une aide GrabCut (vision classique, CPU). C'est volontaire : un commissaire enquêteur peut vérifier un résidu en pixels, pas une inférence.

Dans le développement : Claude Code écrit et teste le code ; les efforts ci-dessus supposent ce mode de travail.

Garde-fous réglementaires écrits dans l'outil :
- aucun export « réglementaire » sans 3 repères minimum, RMS ≤ 5 px, résidus et écarts-types imprimés dans le cartouche ;
- journal.json par vue (SHA-256 photo/DXF, pose, repères, soleil, masque, version, validateur nommé), résumé dans les métadonnées PNG ;
- variante « sans masquage » toujours livrée à côté de la variante masquée, règle écrite : dans le doute, on montre la centrale ;
- interdiction des fonds Google Earth / Street View dans les productions internes (pratique HOCH sur les vues A et B, droits incertains).

Pour plus tard, sous conditions : masquage par Depth Anything V2 Small et MobileSAM (Apache-2.0, ONNX CPU, ~150 Mo, torch non requis) branché sur le même format de masque PNG ; finition générative uniquement avec une clé d'API (aujourd'hui absente), une politique interne, un étiquetage « rendu assisté par IA » et jamais dans les pièces réglementaires.

## 5. La banque de références

Elle ne fournit aucune géométrie. Elle sert à trois choses : référence de style pour calibrer le rendu schématique (teinte des modules, brume, ombres), critère d'acceptation visuel pour le CDP et Eliott, et banc de test si on obtient le DXF d'un projet où HOCH a livré une vue (comparaison côte à côte, condition d'entrée de la phase 2).

Le references.csv actuel a les bonnes colonnes mais neuf lignes « à compléter ». Métadonnées minimales à remplir automatiquement à chaque export : projet, vue, état, source image, hauteur caméra, distance centrale, config (1V/2V/3V), inclinaison, point bas/haut, pas, focale équivalente, résidu RMS, prestataire ou outil, licence de l'image. Point à vérifier : le contrat HOCH avant tout usage de ses vues au-delà d'un test interne.

## 6. Validation du cœur géométrique

Validé aujourd'hui : l'extraction DXF (85 tables, largeur 4,784 m, tilt 25,0°), la conversion GPS vers L93 (0,2 m), la cohérence interne du sténopé (relu à la main, aucun test automatisé), et l'orientation de la caméra vers deux éoliennes à 1,5 km.

Non validé : tout ce qui concerne la centrale elle-même. Le calage sur des repères à l'infini ne voit ni la position GPS (5 m = 53 px à 300 m, 158 px à 100 m), ni la hauteur des tables, ni le roulis (fixé à 0). Le tangage est calé sur le pied d'une haie pris pour l'horizon ; sur Sarnois le profil topo borne ce biais à 0,2°, soit 11 px, mais rien ne garantit cela sur un autre site. La focale 3 166 px ne correspond à aucune règle EXIF. Et un défaut a été confirmé puis corrigé le 14/09 : PVcase exporte déjà les coins bas à 1,50 m du sol (résidu 1,500 ± 0,006 m par rapport au TIN topo, 1,501 ± 0,012 m par pondération inverse des distances), alors que le brief demandait d'ajouter encore 1,50 m. Les tables de Sarnois étaient donc dessinées 1,5 m trop haut (16 à 24 px). Le script mesure désormais l'écart coins bas / sol et n'ajoute que le complément nécessaire. Cela illustre le point : une instruction plausible du brief était fausse et rien ne l'avait détectée.

| Test | Critère chiffré | Données | Jours |
|---|---|---|---|
| V1 Corriger le point bas, assertions DXF, TIN | Résidu = point bas bilan ± 0,05 m ; 85 tables ; 15 rangées au pas de 10,33 m (± 0,02) mesuré sur le DXF, à confirmer par le BE | Confirmation écrite BE du paramétrage PVcase | 0,5 |
| V2 Tests unitaires sténopé, référence indépendante, 6 mutants | Écart JS / Python / cv2 < 0,01 px ; chaque mutant fait échouer un test | Aucune | 1 |
| V3 Ré-audit IMG_6941 (mâts, nacelles, haie) | Roulis ± 0,3° ; tangage nacelles vs haie < 0,2° sinon calage invalidé | Hauteur de moyeu (arrêté préfectoral), RGE ALTI | 0,5 |
| V4 Solveur avec résidus et covariance | Pose synthétique retrouvée à 0,01° ; export marqué non valide si < 3 repères | Aucune | 2 |
| V5 Rognage, orientation EXIF, damier par modèle de téléphone | cx à ± 10 px du centre ; f_px ± 0,5 % ; 0,5x et zoom refusés | Damier A3, 3 à 4 modèles | 1 |
| V6 Centrale UNITe construite, 6 à 8 stations à 50 à 400 m | RMS ≤ 5 px à 200 m, ≤ 10 px à 50 m ; hauteur apparente ± 3 % | DXF as-built + ortho post-construction (QGIS), 1 jour terrain à 2 | 2,75 |
| V7 Panorama ≥ 5 repères bien répartis | Ordre gauche-droite reproduit ; RMS < 3 px ; f ± 1 % de V5 | BD TOPO, couplé à V6 | 1 |
| V8 Répétabilité 3 CDP | Dispersion ≤ 10 px ; calage < 15 min | Fiche terrain | 1 |
| **Total** | | | **~10** |

V6 est le seul test qui valide position, focale, topo et extraction ensemble. Les deux métrologues sont d'accord sur ce point ; ils divergent sur le damier (un par CDP contre un par modèle : je retiens par modèle) et sur les jalons de 2 m plantés sur site (abandonnés, remplacés par des repères proches relevés sur l'ortho 20 cm).

## 7. Plan par étapes

| Jalon | Contenu | Décision go / no go | Bloqué sur Eliott |
|---|---|---|---|
| J0, semaine 1 | V1 à V4 (bureau, 4 j) | Go si V2 et V4 passent ; sinon on ne code pas d'interface | Écrire au BE (paramétrage PVcase, origine de -TopoNiveau) |
| J1, semaines 2 à 4 | V5, V6, V7 (terrain) | Go si RMS ≤ 5 px à 200 m et aucun biais d'échelle ; no go = retour sur le modèle | Choisir la centrale construite, obtenir le DXF as-built, libérer un CDP 1 jour |
| J2, mois 2 à 3 | C1 à C7, C9, sur deux nouveaux projets réels | Go diffusion si 3 vues produites par un CDP en < 40 min et relues par le paysagiste | Désigner un CDP référent, valider la fiche terrain plastifiée |
| J3, mois 4 | Retour d'usage, V8, avis paysagiste sur le rendu schématique | Décision phase 2 Blender uniquement si le schématique est refusé ET si le banc d'essai Blender (2 j, portable cible) mesure < 10 min par variante en 1080p | Arbitrer le budget phase 2 (+20 à 25 j selon un juge, +40 à 50 j selon l'autre) |

## 8. Options écartées

PVue (Blender, 60 j annoncés, 80 à 100 j réalistes) : la bonne cible à terme pour la traçabilité et le niveau HOCH, mais 4 à 9 mois avant la première vue CDP, des rendus Cycles CPU non mesurés (5 à 15 min par variante selon un juge, 20 à 45 min selon l'autre), Blender portable et dalles MNT sur chaque poste, composant Streamlit bidirectionnel fragile. On en garde le journal, scene.json, le verrouillage tangage/roulis sur trépied et le banc d'essai.

PhotoPV Assist (IA à chaque étape, 55 j annoncés, 100 à 130 j réalistes) : le calage automatique échoue là où il serait utile (repères de 10 px, plaine boisée sans horizon), la finition générative exige une clé absente et expose UNITe en enquête publique pour un gain de quelques minutes. On en garde le monopode gradué, l'API altimétrie IGN, la machine d'état par vue et la règle : le modèle ne dessine jamais la centrale.