# Annexe — superviseur dans un fil séparé

À lire seulement si le mandat ou le runtime impose un superviseur distinct du pilote. Par défaut, le pilote supervise dans son propre fil et `owner` désigne ce fil.

- Titulaires : le lanceur reste titulaire de l'index de programme ; le superviseur devient titulaire du seul registre de sa vague. Aucun des deux n'écrit le fichier de l'autre.
- Le lanceur lance seulement ce superviseur, jamais ses champions. Après le reçu réel, il consigne le transfert dans l'index (référence du superviseur sur le résultat concerné). Le superviseur prend alors le registre avec sa propre référence : `rc_state.py claim … --takeover --evidence <transfert consigné dans l'index>` (ou `claim` simple si le registre n'a pas de titulaire). Jusque-là le superviseur n'écrit pas et ne crée aucun acteur.
- Les signaux d'un acteur reviennent à son lanceur : aucune parenté runtime n'est supposée transférable. Si des champions existent déjà et que leurs signaux ne peuvent pas suivre le relais, leur lanceur reste l'unique superviseur ; aucun relais fictif.
- Le lanceur reste destinataire des signaux du superviseur sans redevenir titulaire du registre : il remet la remise finale au demandeur et, sur quota, reprend ce même superviseur selon le mécanisme réellement disponible.
- Si le quota du superviseur a empêché sa persistance, le lanceur constate son absence d'activité puis inscrit l'attente dans l'index, dont il est titulaire : `waiting_on` du résultat (quota, détail, déclencheur), `next_action` de reprise et, si plus rien n'avance, statut du programme. Il n'écrit pas le registre de vague et ne change pas son titulaire. À la reprise, le superviseur rapproche son registre de cette attente ; le lanceur retire ensuite `waiting_on`.
- Transmettre registre, contrat, droits, sources et chemin de retour avec le mandat. Rendre la main n'est pas clôturer ; aucun réveil n'est garanti.
- Nouvelle conversation, préparation close et aucun titulaire ni acteur actif réconcilié : la demande applicable vaut transfert consigné, sans confirmation répétée. Un fil momentanément inactif ne prouve pas ce préalable ; un mandat en quota conserve son titulaire.
