## Terraform — Déploiement du Tool PDR (Docker sur EC2)

Deux modes possibles :

| Mode | Quand l’utiliser |
|------|------------------|
| **Instance existante** | Tu as déjà lancé une EC2 (ex. g4dn.xlarge, IP publique) dans la console. Terraform **ne recrée pas** l’instance ; il copie le projet et lance `docker compose`. |
| **Nouvelle instance** | `existing_instance_id` vide → Terraform crée l’EC2 + Security Group + user_data (Docker). |

---

### Pré-requis
- Terraform ≥ 1.x, AWS CLI ou credentials configurés
- Une **key pair** EC2 (nom AWS + fichier `.pem` local)
- Chemin **absolu** local vers le dossier `projet_industriel_agi/`

---

### Mode A — Instance déjà créée (ex. `51.44.216.246`)

1. **Security Group**  
   - Par défaut **`manage_existing_instance_sg_ingress = false`** : Terraform ne modifie pas le SG (tu ouvres **8000 / 8001 / 8002** dans la console si besoin). Mets **`true`** seulement sur un SG vierge, sinon erreur **Duplicate**.
   - Si Terraform **crée** l’EC2, le SG inclut **22**, **8000**, **8001**, **8002**.

2. **Fichier de variables**  
   ```bash
   cd terraform
   cp terraform.tfvars.example terraform.tfvars
   # Éditer : existing_instance_id, key_name, chemins PEM et project_src_dir, CIDRs
   ```

3. **Déploiement**
   ```bash
   terraform init
   terraform plan
   terraform apply
   ```

4. **Vérification**  
   ```bash
   IP=<sortie de terraform output -raw public_ip>
   curl -s "http://$IP:8000/health"
   curl -s "http://$IP:8001/health"
   curl -s "http://$IP:8002/docs"
   ```
   (`terraform output tool_endpoints` liste les trois URLs.)

**Exemple sans fichier `tfvars` (tout en ligne de commande) :**

```bash
terraform apply \
  -var="region=eu-west-3" \
  -var="existing_instance_id=i-xxxxxxxxxxxxxxxx" \
  -var="key_name=TON_KEYPAIR" \
  -var="ssh_private_key_path=/chemin/absolu/vers/ta_cle.pem" \
  -var="project_src_dir=/chemin/absolu/vers/projet_industriel_agi" \
  -var="remote_deploy_dir=/home/ubuntu/projet_industriel_agi" \
  -var="allowed_ssh_cidr=TON_IP/32" \
  -var="open_ports_cidrs=[\"0.0.0.0/0\"]" \
  -var="deploy_train_agent_pdr=true" \
  -var="deploy_train_agent_pdr_async=true" \
  -var="deploy_start_agent_pdr=true"
```

*(Remplace par ton **Instance ID** EC2, onglet Détails.)*

---

### Mode B — Terraform crée l’EC2 + SG

Laisse `existing_instance_id` vide (ou absent du `tfvars`). Exemple :

```bash
terraform apply \
  -var="key_name=TON_KEYPAIR" \
  -var="ami_id=ami-0e8ab1e54968fc2c9" \
  -var="allowed_ssh_cidr=TON_IP/32" \
  -var="ssh_private_key_path=/chemin/absolu/vers/ta_cle.pem" \
  -var="project_src_dir=/chemin/absolu/vers/projet_industriel_agi" \
  -var="deploy_train_agent_pdr=true" \
  -var="deploy_start_agent_pdr=true"
```

`ami_id` optionnel : par défaut le module utilise l’AMI Ubuntu 20.04 Canonical.

---

### Variables utiles (train / API)

| Variable | Rôle |
|----------|------|
| `deploy_train_agent_pdr` | Lance `agent-pdr-train` au apply |
| `deploy_train_agent_pdr_async` | Si `true`, train en arrière-plan ; `apply` ne attend pas la fin du training |
| `deploy_start_agent_pdr` | Lance `agent-pdr` (API port 8000) |
| `deploy_start_agent_classification` | Lance `agent-classification` (port 8001, modèle XLM-R dans `models_saved/...`) |
| `deploy_start_agent_recette` | Lance `agent_recette` (port hôte 8002) |
| `manage_existing_instance_sg_ingress` | `false` par défaut. `true` = Terraform crée 8000–8002 (interdit si règles déjà présentes). |

Si train **async** + `deploy_start_agent_pdr=true`, **agent-pdr** n’est pas démarré tout de suite ; **agent-classification** et **agent_recette** le sont si leurs flags sont à `true`. Démarre **agent-pdr** après le train : `cd ~/projet_industriel_agi && docker compose up -d agent-pdr`.

---

### Erreur `chown: Operation not permitted` pendant le déploiement

Les répertoires montés par Docker (`local_models`, etc.) peuvent appartenir à **root**. Le script utilise maintenant **`sudo chown -R`** sur `${remote_deploy_dir}`. Sur une AMI sans sudo sans mot de passe pour `ubuntu`, il faudra adapter les droits.

Si tu vois un chemin dupliqué `.../projet_industriel_agi/projet_industriel_agi/`, supprime l’imbrication sur l’instance ou ajuste `remote_deploy_dir` pour n’avoir qu’**un** niveau de dossier projet.

---

### Erreur `InvalidPermission.Duplicate` (security group)

Cela arrive si les ports **8000 / 8001 / 8002** sont déjà autorisés dans le SG avec les mêmes CIDR que `open_ports_cidrs`.

1. Dans `terraform.tfvars`, mets **`manage_existing_instance_sg_ingress = false`** (c’est le défaut).
2. Si un apply a échoué à mi-chemin, nettoie l’état Terraform pour les règles partiellement créées (sans supprimer les règles dans AWS) :
   ```bash
   terraform state list | grep existing_tools_ingress
   # Pour chaque ligne affichée :
   terraform state rm 'aws_security_group_rule.existing_tools_ingress["sg-XXXXXXXX_8002"]'
   ```
3. Relance le déploiement seul (sans recréer le SG) — avec **rsync** (défaut) :
   ```bash
   terraform apply -target='null_resource.deploy_compose_rsync[0]'
   ```
   Si `deploy_use_rsync = false` : `-target='null_resource.deploy_compose_scp[0]'`.

---

### Upload : rsync (défaut)

- **`deploy_use_rsync = true`** : copie avec `rsync -az --partial` (delta, reprise, exclusions des gros dossiers : `local_models/`, `.git/`, `models_saved/xlm_...`, etc.). Nécessite **`rsync`** sur la machine qui lance Terraform (WSL / Linux / macOS : en général déjà présent).
- **`deploy_rsync_excludes`** : liste de motifs `--exclude=` (voir `variables.tf`).
- **`ssh_connection_timeout`** : défaut `45m` (uploads longs).
- **`deploy_use_rsync = false`** : ancien mode provisioner `file` (SCP intégré), tout le dossier — peut être très lent ou timeout si `local_models` est volumineux.

---

### Notes
- `project_src_dir` doit pointer vers le dossier qui contient **`docker-compose.yml`** à la racine.
- Après passage à rsync, un ancien état `null_resource.deploy_compose` est supprimé au prochain `apply` ; c’est normal.
- **Spot** : sauvegarde `./models` (S3 ou snapshot) — l’instance peut être interrompue.
- Profil AWS : `-var="aws_profile=..."` si besoin.
