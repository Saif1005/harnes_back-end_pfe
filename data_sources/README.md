## Data sources (vrais fichiers)

Ce dossier sert à déposer (ou synchroniser) le contenu de ton dossier projet `Data/` (racine du workspace)
sur l’instance AWS, afin que `agent-pdr-train` puisse auto-générer le dataset d’entraînement.

### Structure attendue (exemple)
```text
data_sources/
├── Data_Produc_Qual/
│   └── RATIOS STANDARDS.csv.xlsx
└── piece_de_rechange_data/
    └── ECA_PDR_31122023_Raw(AutoRecovered).csv.xlsx
```

### Note
Si tu préfères utiliser un CSV déjà préparé, place `data/pdr_train.csv` et le training prendra ce CSV en priorité.

