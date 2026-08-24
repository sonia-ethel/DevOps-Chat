# DAC Code Camp ETNA 2026 - Choix techniques

Ce document explique les choix retenus pour la branche `codecamp-etna-2026`.

Pour lancer le projet, voir [installation.md](installation.md).
Pour les commandes rapides, voir [commandes-linux.md](commandes-linux.md).
Pour les variables `.env`, voir [variables-environnement.md](variables-environnement.md).

## 1. Challenge choisi

Challenge principal: mode simulation / preview avant execution.

Variante retenue pour le Code Camp: preview et confirmation avant un deploiement AWS reel, avec garde-fous pedagogiques.

## 2. Probleme identifie

DAC sait generer et executer des actions DevOps, mais le parcours etudiant devait etre plus fiable et plus comprehensible.

Problemes principaux:

- les credentials AWS pouvaient etre invalides ou expires;
- Terraform pouvait echouer tardivement avec une erreur difficile a lire;
- les actions cloud peuvent generer des couts;
- un debutant doit comprendre ce qui va etre execute avant de confirmer;
- le perimetre de demo devait rester limite.

## 3. Solution proposee

La branche `codecamp-etna-2026` garde un deploiement AWS reel, mais l'encadre.

Choix retenus:

- AWS est le provider cible du parcours ecole;
- le mode ecole est active avec `DAC_SCHOOL_MODE=true`;
- le nombre de VM est limite avec `DAC_SCHOOL_MAX_INSTANCES`;
- les credentials AWS sont valides via STS avant sauvegarde;
- une validation AWS est faite avant Terraform;
- les erreurs AWS renvoient l'utilisateur vers l'onboarding;
- la creation passe par une confirmation utilisateur;
- le projet fonctionne sans cle OpenAI grace au mode IA `mock`.

## 4. Composants impactes

Backend:

- `devops_api/app/routes/chat_creation_routes.py`: workflow DAC principal et preflight CREATE.
- `devops_api/app/routes/user_credentials_routes.py`: enregistrement et statut des credentials AWS.
- `devops_api/app/services/aws_credentials_service.py`: validation STS des credentials.
- `devops_api/app/services/terraform_service.py`: garde-fou avant plan/apply Terraform.
- `devops_api/app/routes/generate_terraform.py`: generation Terraform et limites CodeCamp.
- `devops_api/app/services/gpt_service.py`: mode IA mock ou OpenAI.
- `devops_api/app/env.py`: chargement du `.env` racine pour simplifier l'installation.

Frontend:

- onboarding AWS;
- chat DAC;
- pages dashboard et resources;
- indicateur AWS utilisable pour revenir vers l'onboarding.

Configuration:

- `.env.example`: modele officiel de configuration;
- `docker-compose.yml`: PostgreSQL, backend FastAPI et frontend Nginx;
- `documentation/`: guides et support pedagogique.

## 5. Choix IA

Par defaut, le projet utilise:

DAC_AI_PROVIDER=mock

Ce choix permet de lancer DAC sans cle OpenAI.

En mode mock:

- le backend demarre sans cle OpenAI;
- le chat libre renvoie une reponse pedagogique;
- les workflows DAC continuent d'utiliser les regles et fallbacks applicatifs;
- les generations IA avancees necessitent OpenAI.

Pour activer OpenAI:

DAC_AI_PROVIDER=openai
OPENAI_API_KEY=sk-...
DAC_AI_MODEL=gpt-4o-mini

Le modele conseille est `gpt-4o-mini`, car il est plus economique que `gpt-4o` et suffisant pour l'aide DevOps, la reformulation et l'explication d'erreurs.

## 6. Scenario de demonstration

1. Se connecter a DAC.
2. Ouvrir l'onboarding AWS.
3. Enregistrer des credentials AWS valides.
4. Passer en mode DAC.
5. Demander: `cree une instance EC2 Ubuntu`.
6. Donner les parametres: `AWS Ubuntu 22.04 t3.micro eu-west-1`.
7. Confirmer avec `ok`.
8. Observer la generation Terraform et le resultat.
9. Lister les ressources.
10. Supprimer la ressource creee pour eviter les couts.

## 7. Limites connues

- Le projet reste une version alpha pedagogique.
- Le parcours ecole cible AWS uniquement.
- Les credentials AWS doivent etre valides et non expires.
- Les droits IAM doivent autoriser STS et les actions EC2 necessaires.
- Docker doit etre recent: Docker API 1.44+.
- Le frontend local demande Node.js 20.19+ ou 22.12+.
- La suppression des ressources doit etre verifiee en fin de demo.

## 8. Pistes d'amelioration pour les etudiants

- Ajouter un bouton destroy plus visible.
- Ajouter une estimation de cout AWS.
- Ajouter un dashboard d'executions plus complet.
- Ameliorer la detection d'intention.
- Ajouter un resume IA des erreurs Terraform.
- Ajouter une preview Terraform plus lisible.
- Ajouter des tests end-to-end reproductibles.
