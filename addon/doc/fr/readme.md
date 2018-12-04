
# Web Access pour NVDA - Documentation utilisateur

Version 2018.12.04

Copyright (C) 2015-2018 [Accessolutions](http://accessolutions.fr)


## Les modules web

Les modules web permettent, de manière interactive, de créer des scripts NVDA pour simplifier et personnaliser la navigation sur des sites web ou des applications métier.


### Création d’un module web

Placez le focus sur une des pages du site web pour lequel vous voulez créer un module.  

Appuyez sur NVDA+W.  

Choisissez « Nouveau module web » dans le menu.

La boîte de dialogue « Nouveau module web » s’ouvre.  

Dans la zone « Nom du module web », entrez un nom qui identifie au mieux le nom général du site. (Ce nom doit respecter la syntaxe des noms de fichier de Windows.)  

Dans la liste déroulante « URL », choisissez la partie de l’URL qui sera commune à l’ensemble des pages du site. Appuyez sur la flèche vers le bas pour obtenir les différentes sous-parties de l’URL en cours.  
Il est généralement suffisant de sélectionner le premier choix proposé qui ne contient que la première partie de l’URL avant le premier caractère « / ».

Dans la liste déroulante « Titre de la fenêtre », vous pouvez entrer une chaîne de caractères qui se trouve dans le nom de la fenêtre du navigateur.
N’utilisez ce paramètre que si la recherche par URL ne permet pas d’identifier le site web. Il faut généralement laisser ce champ vide.

Cliquez sur le bouton « OK » pour créer le module.

Un fichier ayant l’extension « .json » est créé dans le dossier « webModules » du dossier utilisateur de NVDA.


### Modification d’un module web

Placez le focus sur une des pages du site web pour lequel vous voulez modifier le module.  

Appuyez sur NVDA+W.  

Choisissez « Gérer les modules web » dans le menu.

La boîte de dialogue « Gestion des modules web » s’ouvre.  

Sélectionnez le module que vous voulez modifier.


## Les règles de module

Un module web est constitué d’une liste de règles.
Chaque règle permet d’identifier un élément précis d’une page web et de lui associer des raccourcis clavier et des actions.


### Création d’une règle

Pour créer une règle, placez tout d’abord le curseur de navigation dans la page web sur l’élément pour lequel vous voulez créer la règle.

Appuyez sur NVDA+W.

Dans le menu, choisissez « Nouvelle règle ».

Dans la zone « Nom de la règle », entrez le nom de cette règle.  
Ce nom sera automatiquement lu par la synthèse vocale lorsque vous appuyez sur le raccourcis clavier qui lui est associé.


#### Les critères de filtrage.

Les champs suivants permettent de définir des critères afin d’identifier l’élément auquel s’applique la règle. Un ou plusieurs critères peuvent être spécifiés.  

Pour chaque liste déroulante, en appuyant sur la flèche vers le bas vous obtiendrez des propositions, qui seront de moins en moins spécifiques à l’élément en cours. Il est donc généralement préférable de choisir parmi les premiers choix proposés. Techniquement, ces choix sont les attributs HTML de tous les parents de l’élément HTML en cours.


##### Texte

Dans le champ « Texte », entrez la chaîne de caractères à rechercher.  
Si la chaîne de caractères commence par un caractère « < » (Inférieur à), c’est alors le texte de l’élément précédent qui sera recherché. Cela est utile par exemple pour rechercher une zone d’édition dont le label est situé juste avant cette zone.


##### Rôle

Dans la liste déroulante « Rôle », choisissez un des rôles proposés pour cet élément.


##### Tag

Dans la liste déroulante « Tag », choisissez le tag HTML utilisé pour cet élément.  

Il est généralement suffisant de choisir uniquement soit un rôle, soit un tag HTML.


##### ID

Dans la liste déroulante « ID », choisissez une des chaînes de caractères qui identifie le mieux l’élément, s’il en existe une.


##### Classe

Dans la liste déroulante « Classe », choisissez une des chaînes de caractères qui identifie le mieux l’élément, s’il en existe une.

Comme pour des noms de fichier, les chaînes ID et Classe peuvent contenir des caractères « * » (étoile), afin de ne spécifier qu’une partie de la chaîne recherchée.


##### SRC

La zone « SRC » est utile uniquement pour les éléments de type graphiques contenant le nom d’un fichier image.


##### Contexte

Choisissez dans la liste déroulante une des règle qui est définie comme étant une règle de contexte.
La règle en cours sera alors active uniquement si la règle de contexte est elle-même active.

Vous pouvez inverser la condition en placeant un point d'exclamation "!" devant le nom de la règle de contexte.


##### Index

Si plusieurs éléments correspondent aux critères de la règle, ce champ indique le numéro de l’élément qui sera pris comme premier résultat.


##### Résultats multiples

Par défaut, si plusieurs éléments de la page correspondent aux critères de la règle, seul le premier élément trouvé sera utilisé, les autres sont ignorés.

Si cette case est cochée, alors tous les éléments répondant aux critères de la règle seront pris en compte.
Cela signifie que l’appui sur les touches « page suivante » et « page précédente » permettra de passer sur tous les éléments trouvés par la règle.
Cependant, cela ne change pas le comportement des raccourcis clavier associés à la règle, qui s’appliqueront toujours uniquement au premier élément trouvé.
Il sera par exemple judicieux de cocher la case « Résultats multiples » pour une règle permettant de se déplacer sur tous les résultats d’une recherche.  
Si la case n’était pas cochée, seul le premier résultat de la recherche serait identifié.


#### Raccourcis clavier

Cliquez sur le bouton « Ajouter un raccourci clavier ».

Appuyez sur le raccourci clavier que vous voulez créer.

Dans le menu déroulant qui s’ouvre, choisissez l’action que vous voulez associer à ce raccourci clavier.

Les actions possibles sont :

* « Aller à » : Déplace le curseur de navigation sur l’élément et le lit.
* « Annoncer » : Lit le texte de l’élément mais ne déplace pas le curseur.
* « Lancer la lecture » : Déplace le curseur de navigation sur l’élément et lance la lecture automatique de tout le texte à partir de cette position.
* « Cliquer » : Effectue un click de la souris sur l’élément.
* « Déplacer la souris » : Déplace le pointeur de la souris sur cet élément mais n’effectue pas de click.

Il est possible de créer plusieurs raccourcis clavier pour une même règle.


##### Cas particulier de l’action « Annoncer » :

Lorsque l’on associe l’action « Annoncer » à un raccourci clavier, il sera alors possible d’exécuter l’action « Aller à » en appuyant deux fois rapidement sur le raccourcis clavier.

Cela est utile par exemple lorsque l’on crée un raccourci pour faire lire un message d’erreur sans vouloir y déplacer le curseur. La double tape sur ce même raccourci permettra cependant de s’y déplacer pour, par exemple, lire plus précisément le message en braille ou en vocal.


#### Actions automatiques

L’action automatique n’est pas liée à un raccourci clavier. Elle s’exécute automatiquement dès que l’élément correspondant aux critères de la règle est détecté dans la page. Cela est utile pour, par exemple, placer le curseur automatiquement à une position précise lorsqu’une page vient de se charger. Ou encore, annoncer automatiquement un message d’erreur lorsqu’il apparaît.

Attention : Bien qu’elles soient très utiles, les actions automatiques peuvent créer des comportements imprévisibles avec le navigateur, si elles ne sont pas utilisées à bon escient et parfaitement maîtrisées.  
L’action « Annoncer » ne pose pas de problème particulier.  
Les actions « Aller à » et « Lancer la lecture » peuvent générer certains blocages.  
L’action « Cliquer » doit être évitée si elle n’est pas indispensable.


#### Activer le mode formulaire

Cette case à cocher indique si le mode formulaire doit être automatiquement activé lorsque l’on se déplace sur l’élément.
Par défaut, cette case est automatiquement cochée lorsque l’on crée une règle sur une zone d’édition.


#### Lire le nom de la règle

Cette case à cocher indique si le nom de la règle doit être lu par la synthèse vocale lorsque l’on se déplace sur l’élément.
Elle est cochée par défaut. Vous pouvez la décocher pour éviter la lecture de ce nom, pour les cas où, par exemple, il y a lecture en double du texte de l’élément.

#### Ignorer avec Page Down

Cette case à cocher indique si le curseur s'arrête sur cette règle lors de l'appui des touches Page Down ou Page Up.

#### Titre de page

Cette case à cocher indique si cette règle est utilisée comme titre de la page lorsque l'on appui sur NVDA+T.

#### Is a context

Cette case à cocher indique si cette règle est utilisée comme contexte pour les autres règles.


## Bonnes pratiques

Afin de faciliter l’apprentissage, la compréhension, la mémorisation des raccourcis clavier et la structuration des pages d’un site à l’utilisateur final d’un module, il est conseillé aux développeurs de respecter, dans la mesure du possible, certaines recommandations d’implémentation.


### Être cohérent dans le choix des raccourcis clavier

Il faut utiliser des raccourcis clavier similaires pour des actions similaires dans les différentes pages du site.
Par exemple, Control+Maj+B pour se placer sur la barre de boutons principale quelle que soit la page.

Toutes les combinaisons de raccourcis clavier sont autorisées, mais il faut privilégier en premier les combinaisons avec Control+Maj.


### Définir les différentes zones structurant les pages

La plupart des sites ont une structuration identique pour l’ensemble des pages.
Cette structuration est conçue pour être rapidement compréhensible visuellement, mais elle est très difficile à appréhender en braille ou en vocal.

La création de raccourcis clavier est utile pour permettre à l’utilisateur de se déplacer rapidement, mais elle permet également de mieux faire comprendre comment sont organisées les pages.

Pour cela, il est conseillé d’affecter toujours les mêmes raccourcis clavier pour les zones principales structurant le site.

Exemple : 

Control+Maj+L : Se placer en lecture au début du contenu de la page.  
Control+Maj+E : Se placer en mode formulaire sur le premier champ d’édition du formulaire principal.
Control+Maj+H : Se placer sur le menu principal (celui du site, pas celui du navigateur).  
Control+Maj+O : Se placer sur les onglets (les onglets internes au site, pas les onglets du navigateur).  
Control+Maj+B : Se placer sur la barre de boutons principale (généralement les boutons en bas du formulaire).  
Control+Maj+A : Se placer sur l’arborescence (généralement affichée sur la partie gauche de la page).  
Control+Maj+F : Se placer en mode formulaire sur la zone d’édition de recherche du site, s’il y en a une.  
Control+Maj+M : Annoncer un message d’erreur ou d’information.  
Control+Enter : Cliquer sur le bouton principal de validation du formulaire.  

Cette liste n’est pas obligatoire ni exhaustive, mais il est recommandé de conserver ce type de logique pour aider l’utilisateur à mieux comprendre comment naviguer dans le site.


### Gestion des messages d’erreur et d’information

Les messages d’erreur ou d’information sont des éléments très difficiles à détecter et à localiser avec un lecteur d’écran.
Qu'ils soient affichés durant l'édition d'un champ ou à la validation d'un formulaire, on emploiera typiquement une action automatique afin de les annoncer dès qu'ils sont détectés.
