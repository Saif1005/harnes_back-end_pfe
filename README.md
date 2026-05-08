# Sotipapier — Frontend usine

Interface **React + Vite + TypeScript + Tailwind** pour le centre de contrôle et l’assistant IA, connectée au backend FastAPI du cerveau orchestrateur.

## Prérequis

- Node.js 18+
- Backend **accessible depuis ton navigateur** (souvent une EC2 sur AWS avec le port **8010** ouvert)

## Backend sur AWS (recommandé)

1. Récupère l’**IP publique** (ou le DNS) de l’instance où tourne le cerveau (ex. sortie Terraform `public_ip` pour l’orchestrateur).
2. Dans le **Security Group** de cette instance, autorise au minimum le **TCP 8010** depuis ton IP (`x.x.x.x/32`) ou temporairement `0.0.0.0/0` pour un test.
3. Crée un fichier **`.env`** à la racine de `frontend/` :

```bash
cp .env.example .env
```

4. Édite **`.env`** et remplace `REPLACE_WITH_EC2_PUBLIC_IP` par la vraie valeur, par exemple :

```env
VITE_API_URL=http://13.38.81.152:8010/api/v1
```

5. **CORS** : le backend FastAPI doit autoriser l’origine du frontend (ex. `http://localhost:5173` en dev, ou l’URL du site une fois déployé). Sinon le navigateur bloquera les requêtes vers AWS.

```bash
npm install
npm run dev
```

Ouvre `http://localhost:5173` : le frontend tourne en local mais appelle l’API sur **AWS**.

## Installation (backend local)

Si le cerveau tourne sur ta machine :

```env
VITE_API_URL=http://localhost:8010/api/v1
```

## Scripts

| Commande      | Description        |
|---------------|--------------------|
| `npm run dev` | Serveur de dev Vite |
| `npm run build` | Build production dans `dist/` |
| `npm run preview` | Prévisualise le build |
| `npm run lint` | ESLint |

## Variable d’environnement

- **`VITE_API_URL`** : URL de base des routes API (sans slash final). Les appels utilisent `${VITE_API_URL}/ask_agent`.  
  Elle est **injectée au build** (`vite build`) : après modification, relance `npm run dev` ou refais un build Docker.

## Docker (nginx)

Remplace l’URL par celle de ton EC2 :

```bash
docker build -t sotipapier-frontend:latest \
  --build-arg VITE_API_URL=http://VOTRE_IP_PUBLIQUE_EC2:8010/api/v1 \
  .

docker run -p 8080:80 sotipapier-frontend:latest
```

## Auth

Mode **démo** : connexion / inscription simulées avec jeton JWT factice en `localStorage`. Remplacer par un vrai endpoint d’auth quand le backend l’exposera.
