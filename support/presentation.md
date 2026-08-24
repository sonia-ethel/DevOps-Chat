# Soutenance - DAC Code Camp ETNA 2026

## 1. Sujet

DAC signifie DevOps-as-a-Chat. Le projet permet de piloter des actions DevOps via une interface conversationnelle.

## 2. Challenge choisi

Challenge 3: preview et confirmation avant execution.

Objectif de l'equipe: rendre un deploiement AWS reel plus comprehensible, plus sur et plus demonstrable.

## 3. Probleme initial

- Les actions cloud peuvent etre sensibles.
- Les erreurs AWS sont difficiles a comprendre.
- Une cle AWS expiree faisait echouer Terraform tardivement.
- Un debutant ne sait pas toujours quoi corriger.

## 4. Solution

- Validation AWS via STS avant sauvegarde.
- Validation AWS avant lancement CREATE.
- Mode ecole limite a AWS et a un petit nombre de VM.
- Messages d'erreur plus explicites.
- Procedure de lancement documentee.

## 5. Architecture modifiee

Frontend React -> FastAPI -> detection intention -> generation Terraform -> validation credentials -> execution Terraform -> retour chat.

## 6. Demo nominale

Prompt:

```text
cree une instance EC2 Ubuntu
```

Parametres:

```text
AWS Ubuntu 22.04 t2.micro eu-west-1
```

Confirmation:

```text
ok
```

Resultat attendu: Terraform genere et lance la creation AWS.

## 7. Demo erreur

Utiliser une cle AWS invalide.

Resultat attendu: DAC indique que les credentials sont invalides ou expires et renvoie vers l'onboarding AWS.

## 8. Difficultes

- Comprendre l'architecture existante.
- Garder un changement limite dans un projet alpha.
- Rendre les erreurs cloud lisibles.
- Eviter les couts ou actions dangereuses.

## 9. Limites

- AWS uniquement pour le parcours ecole.
- Les droits IAM doivent etre prepares.
- Le destroy doit etre verifie manuellement si le workflow n'est pas utilise.

## 10. Perspectives

- Dashboard d'executions.
- Estimation de cout.
- Meilleur destroy guide.
- IA pour expliquer les erreurs Terraform.
- Support EtnaCloud plus specifique.
