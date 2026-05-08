## Données d'entraînement `agent-pdr`

### Fichier attendu
Créer `pdr_train.csv` dans ce dossier.

Format recommandé : CSV `;` UTF-8-SIG avec colonnes:
- `text` : texte concaténé (Item + descriptions)
- `Category` : `matière première` ou `autre PDR`

Optionnel (pour audit) :
- `Item_No_`, `Description_1`, `Description_2`

### Exemple minimal
```csv
text;Category
amidon cationique;matière première
roulement skf 6205;autre PDR
```

