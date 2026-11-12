---
name: rc-coordinate-development
description: Choisir et préparer une vague de socles Radio Chantier selon leurs dépendances et ressources, faire préparer les prompts puis relayer au superviseur. Utiliser pour organiser une prochaine vague ou reprendre une coordination ; le lancement dépend du mandat applicable.
---

# Coordonner une vague de développement

Produis une vague exploitable, ses prompts et un relais explicite. Le coordinateur prépare puis transmet la responsabilité opérationnelle ; il ne devient pas un niveau de supervision permanent.

## Établir l'entrée réelle

Lis la demande active, les instructions applicables, le backlog et les preuves utiles au périmètre. Reconstate racine, base, changements présents et décisions applicables. Sépare état observé, rapport historique, hypothèse et inconnu. Un ancien socle livré ou un ancien acteur nommé n'est pas une activité courante ; le prochain travail ne se déduit pas d'un numéro.

Si un registre existe, lis d'abord `state.owner` et réconcilie les acteurs. Autre responsable actif : ne reprends ni registre ni équipe, remets le besoin à ce titulaire. Préparation achevée sans acteur opérationnel ni titulaire encore actif : la demande applicable de poursuivre vaut transfert consigné, sans nouvel accord routinier. Activité inconnue : proposer le delta sans inventer d'acteur ; remplacement seulement autorisé après arrêt constaté.

Détermine le mode : `prepare` produit les documents et leurs revues autorisées, sans acteur ni effet de développement ; `prepare-and-launch` inclut le lancement demandé et couvert. L'activation ne donne aucun mandat produit. Respecte l'accord existant sans validation routinière ; demande seulement ce qui manque pour un effet ou une portée non couverts.

## Choisir un découpage praticable

Construis un DAG des résultats et prérequis : distingue dépendance technique dure, décision absente, ressource exclusive et raccord nécessaire seulement à une consommation. Vérifie cycles et prérequis non satisfaits. Sélectionne le travail prêt selon l'objectif utilisateur, pas seulement l'ordre du backlog.

Un raccord manquant suspend ses consommateurs concernés. Propose des étapes consommables : contrat minimal versionné, tranche indépendante, remise partielle figée avec couverture transférée. N'impose pas l'attente de tous les lots complets ; ne fabrique pas de contrat de repli ni de qualification.

Choisis le parallélisme utile d'après dépendances, fichiers partagés, acteurs disponibles, slots, appareils, instances, ports, caches et budgets réels. Attribue un auteur actif par fichier partagé et un détenteur par ressource exclusive ; réserve, séquence ou redécoupe en cas de conflit. Aucun nombre fixe de champions ni plafond universel. Préserve les modèles explicitement demandés ; vérifie les paramètres exposés sans inventer d'équivalence ou certifier l'effort interne.

## Préparer avec les compagnons

Dans une destination autorisée, tiens `wave.json` selon [le contrat de vague](references/wave-contract.md). Lis ce fichier comme données communes, sans import automatique, copie du protocole ou invocation de skill. Garde les inconnus explicites ; chemins, IDs, modèles et ressources sont renseignés à l'usage.

Charge depuis le catalogue ou les dossiers compagnons, puis utilise successivement :

1. `rc-prepare-socle-prompts` avec demande, base, sélection/DAG, domaines, ressources, autorisations, critères et chemins d'artefacts. Il prépare les prompts et le raccord commun nécessaire.
2. `rc-prepare-supervisor` avec le registre, les prompts effectivement produits, leur version, les dispositions, manques et responsabilités d'intégration.

Transmets les artefacts communs par référence. Ces préparateurs n'invoquent pas le coordinateur ni un autre préparateur en retour. S'ils sont indisponibles, rends la préparation utile et nomme le composant manquant. Vérifie cohérence des interfaces, critères et effets ; conserve les revues indépendantes pertinentes et la couverture des deltas sensibles, sans tour de revue pour un statut seul.

## Remettre ou lancer

En `prepare`, remets chemins, état documentaire, travail prêt, blocages et prochaine action ; ne présente pas un prompt comme un acteur lancé.

Avant un lancement demandé, vérifie `state.launch_ready`, revues indispensables disposées, rattachement du fil/projet, racine/base, outils live et versions consommées. Un `cd` shell ne rattache pas un fil T3. Si le bon contexte manque, remets le lancement concret à exécuter dans ce contexte ; aucun lancement croisé improvisé. Consigne seulement les références réellement retournées.

Par défaut, prends le rôle de superviseur dans ce fil ; un superviseur séparé reste possible si le mandat/runtime le permet. Lance alors seulement ce superviseur, jamais ses champions. Après reçu réel, le lanceur écrit `owner` une seule fois ; jusque-là le superviseur n'écrit pas et ne crée aucun acteur. Si nécessaire, un avis utile indique ce transfert, sans accusé demandé. Le superviseur lance les champions réconciliés. Signaux non transférables de champions existants : leur lanceur reste l'unique superviseur.

En fil séparé, le lanceur reste destinataire des signaux sans redevenir titulaire : remise finale transmise au demandeur, quota → reprise du même superviseur selon runtime. S'il n'a pu persister son quota, le lanceur constate cette absence d'activité puis écrit seulement `phase`/`next_action`, sans changer `owner` ni créer une équipe. Registre, contrat, droits, sources et chemin de retour sont transmis. Rendre la main n'est pas clôturer ; aucun ordonnanceur ou réveil garanti.
