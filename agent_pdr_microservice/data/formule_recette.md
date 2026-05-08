# 📑 Fiche Technique de Production : Formules et Recettes (Sotipapier)

Ce document répertorie les spécifications de production pour les articles : **Cannelure (Fluting)**, **Kraft pour sacs**, **TestLiner** et **TestLiner Coloré**.

---

## ⚗️ 1. Formule Générale de Calcul

Pour déterminer la quantité exacte de chaque ingrédient nécessaire à une commande, appliquez l'équation suivante :

$$Q_{ingrédient} = Q_{cible} \times Ratio_{ingrédient}$$

* **$Q_{ingrédient}$** : Masse de l'additif ou de la fibre à introduire (en kg ou tonnes).
* **$Q_{cible}$** : Volume de production final souhaité (en tonnes).
* **$Ratio_{ingrédient}$** : Valeur spécifique définie dans les tableaux ci-dessous (en kg/t).

---

## 🧬 2. Définitions et Rôles Techniques des Ingrédients

| Ingrédient | Rôle Technique | Impact Qualité |
| :--- | :--- | :--- |
| **Fiber/Waste Paper Ratio** | Rendement de transformation de la matière première. | Définit la perte process (fines, impuretés). |
| **Pâte (Pulp)** | Apport de fibres vierges (Standard/Flocon). | Augmente la résistance à la déchirure et traction. |
| **Amidon Cationique** | Agent de liaison interne chargé positivement. | Améliore le Burst (Indice d'éclatement). |
| **Amidon Oxydé / Size Press** | Traitement de surface appliqué à sec. | Augmente la rigidité (Stiffness) et l'imprimabilité. |
| **Sizing (ASA / PPO)** | Agent chimique rendant la fibre hydrophobe. | Contrôle l'absorption d'eau (Test Cobb). |
| **PAC (Coagulant)** | Fixateur de charges et de résidus anioniques. | Améliore l'efficacité du collage et la clarté de l'eau. |
| **Dye (Colorant)** | Pigmentation de la masse fibreuse. | Assure la conformité visuelle de l'article. |
| **Antimousse (Afranil/Erol)** | Rupture de la tension superficielle de l'air. | Élimine les trous dans la feuille et améliore le drainage. |
| **Agent de Rétention** | Floculation des fines sur la toile de formation. | Maximise le rendement et réduit la charge du Krofta. |
| **Polymère Krofta** | Agent de clarification par flottation. | Récupère les fibres perdues dans les eaux blanches. |
| **Biocide** | Contrôle de la prolifération bactérienne. | Évite les taches (slime) et les mauvaises odeurs. |

---

## 📋 3. Ratios de Production par Article (kg par tonne produite)

### A. Cannelure (Fluting)
*Priorité : Rigidité mécanique pour le carton ondulé.*

* **Ratio Fibre (Waste Paper) :** 1.204
* **Amidon Cationique :** 33.0
* **Amidon Oxydé (Surface) :** 50.0
* **Antimousse (Afranil) :** 0.5
* **Antimousse 2 (Erol) :** 1.5
* **Agent de Rétention :** 0.37
* **Polymère Krofta :** 0.37
* **Prestige (Nettoyage) :** 0.5
* **Biocide :** 0.15

### B. Kraft pour sacs
*Priorité : Résistance à la déchirure et étanchéité.*

* **Standard Pulp :** 0.5494
* **Flocon Pulp :** 0.2706
* **Waste Paper :** 0.28
* **Fiber Ratio (Global) :** 1.1
* **Amidon Cationique :** 26.0
* **Agent de collage (ASA) :** 3.2
* **Antimousse (Afranil) :** 1.5
* **Agent de Rétention :** 0.27
* **Polymère Krofta :** 0.25
* **Prestige (Nettoyage) :** 0.4
* **Biocide :** 0.15

### C. TestLiner
*Priorité : Résistance à la compression et imperméabilité.*

* **Ratio Fibre (Waste Paper) :** 1.204
* **Amidon Cationique :** 33.0
* **Sizing PPO (Collage) :** 3.5
* **PAC (Coagulant) :** 3.5
* **Defoamer 1 (Afranil) :** 0.5
* **Defoamer 2 (Erol) :** 1.5
* **Agent de Rétention :** 0.37
* **Polymère Krofta :** 0.37
* **Biocide :** 0.15

### D. TestLiner Coloré
*Priorité : Esthétique et finition de surface.*

* **Ratio Fibre (Waste Paper) :** 1.204
* **Dye (Colorant Wet End) :** 5.5
* **PAC :** 3.5
* **Size Press (Traitement) :** 14.0
* **Amidon Cationique :** 33.0
* **Sizing PPO (Collage) :** 3.5
* **Defoamer 1 (Afranil) :** 0.5
* **Defoamer 2 (Erol) :** 1.5
* **Agent de Rétention :** 0.37
* **Polymère Krofta :** 0.37
* **Biocide :** 0.15

---

## ✅ 5. Cohérence des valeurs

Les ratios ci-dessus sont alignés sur les médianes du fichier de référence
`correlation_qualite_ingredients_recette.csv` (unité: **kg/t**).
En cas d'écart lors d'un calcul, cette base CSV doit rester la source de vérité.

---

## 📌 6. Notes de Processus Critique

1.  **Synergie PAC/Sizing :** Le dosage du PAC (3.5) doit impérativement être maintenu pour garantir la fixation du PPO ou du colorant.
2.  **Gestion de la Mousse :** Pour les TestLiners, le système double (Afranil + Erol) est nécessaire pour éviter les défauts d'aspect liés à l'air occlus.
3.  **Rendement Krofta :** Toute augmentation du ratio fibre au-delà de 1.204 indique un dysfonctionnement du polymère Krofta ou de l'agent de rétention.