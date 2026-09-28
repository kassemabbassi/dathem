# DATHEM Agent V1 — guide de transfert et d’installation

Ce guide explique comment préparer le paquet sur le PC de développement, le transférer sur le PC d’un ami, enregistrer le profil de cet ami, puis installer, démarrer et arrêter le service Windows.

> **Important :** l’installation et l’utilisation doivent se faire avec l’accord du propriétaire du PC. DATHEM utilise la caméra et enregistre localement des données biométriques. Son écran personnalisé est une fenêtre de verrouillage de l’application ; ce n’est pas l’écran de connexion sécurisé de Windows et il ne remplace pas le verrouillage natif de Windows.

## 1. Fichiers à transférer

Dans le dossier de sortie du PC de développement :

```text
face guard\dist\DathemAgentV1\
```

Le paquet destiné à l’ami doit contenir **ces trois éléments**, placés ensemble à la racine du dossier `DathemAgentV1` :

```text
DathemAgentV1Setup.exe
DathemAgentV1Agent\                 (copier le dossier entier, y compris _internal)
DathemAgentV1Service\               (copier le dossier entier, y compris _internal)
```

Ne transfère pas l’ancien `DathemAgentV1.exe` situé à la racine de `dist\DathemAgentV1` : c’est l’ancien exécutable de service compilé en `onefile`. La nouvelle version du service est `DathemAgentV1Service\DathemAgentV1Service.exe`. Ne transfère pas non plus `encodings.pkl`, `build`, `venv`, `service.log`, `DathemAgentV1-service.log` ou ton profil personnel.

### Créer une archive ZIP sur le PC de développement

Ouvre PowerShell sur ton PC et exécute :

```powershell
$packageSource = "$HOME\Desktop\face guard\dist\DathemAgentV1"
$packageStage = Join-Path $env:TEMP ("DathemAgentV1-Package-" + [guid]::NewGuid().ToString("N"))
$zipPath = "$HOME\Desktop\DathemAgentV1.zip"
New-Item -ItemType Directory -Path $packageStage | Out-Null
Copy-Item -LiteralPath "$packageSource\DathemAgentV1Setup.exe" -Destination $packageStage
Copy-Item -LiteralPath "$packageSource\DathemAgentV1Agent" -Destination $packageStage -Recurse
Copy-Item -LiteralPath "$packageSource\DathemAgentV1Service" -Destination $packageStage -Recurse
Compress-Archive -Path "$packageStage\*" -DestinationPath $zipPath -Force
```

La commande crée `DathemAgentV1.zip` sur le Bureau. Elle ne met dans l’archive que les trois éléments requis, sans l’ancien service `onefile` ni ton profil local. Transfère cette archive à ton ami par un moyen de confiance.

## 2. Conditions sur le PC de l’ami

- PC Windows 10 ou 11 64 bits.
- Une caméra fonctionnelle, autorisée dans **Paramètres Windows > Confidentialité et sécurité > Caméra** (sur certaines versions : **Confidentialité > Caméra**). Autoriser l’accès à la caméra et aux applications de bureau.
- Une session Windows de l’ami ouverte localement lorsqu’il veut démarrer DATHEM. Le service lance l’agent dans la session de bureau active.
- Un compte administrateur, nécessaire pour installer, démarrer, arrêter ou désinstaller un service Windows.
- La connexion Internet n’est pas nécessaire au fonctionnement une fois les fichiers transférés.

## 3. Extraire le paquet sur le PC de l’ami

Sur le PC de l’ami, place `DathemAgentV1.zip` dans le dossier Téléchargements. Ouvre PowerShell **normalement**, sans élévation, puis exécute :

```powershell
$zipPath = "$HOME\Downloads\DathemAgentV1.zip"
$installDir = "$HOME\Desktop\DathemAgentV1"
New-Item -ItemType Directory -Path $installDir -Force | Out-Null
Expand-Archive -LiteralPath $zipPath -DestinationPath $installDir -Force
Get-ChildItem $installDir
```

À la racine de `$installDir`, la liste doit montrer `DathemAgentV1Setup.exe`, `DathemAgentV1Agent` et `DathemAgentV1Service`. Si Windows a créé un dossier supplémentaire `DathemAgentV1` à l’intérieur, déplace le contenu de ce sous-dossier directement dans `Desktop\DathemAgentV1` avant de continuer : les trois éléments doivent être côte à côte comme à la section 1.

Si le ZIP est enregistré ailleurs, adapte uniquement la valeur de `$zipPath`. Garde le dossier d’installation à cet emplacement après l’installation : le service utilise les exécutables qui s’y trouvent.

## 4. Enregistrer le profil de l’ami

Cette étape doit être faite **dans la session Windows de l’ami**, avant de démarrer le service. Utilise PowerShell normal, non administrateur :

```powershell
Set-Location "$HOME\Desktop\DathemAgentV1"
& ".\DathemAgentV1Setup.exe"
```

Dans l’assistant :

1. Saisir le nom qui sera affiché par DATHEM.
2. Choisir un mot de passe d’au moins 8 caractères et le confirmer.
3. Se placer seul devant la caméra et attendre le cadre vert.
4. Faire les 8 captures demandées en changeant légèrement l’angle du visage.
5. Cliquer sur **Enregistrer le profil** et attendre le message de confirmation.

Vérifie ensuite que le profil a été créé pour le compte Windows actuellement connecté :

```powershell
Test-Path "$env:LOCALAPPDATA\DathemAgentV1\profile.json"
```

Le résultat attendu est `True`. Si c’est `False`, ne démarre pas encore le service : relance l’assistant et termine l’enregistrement.

### Données personnelles

L’assistant enregistre les encodages faciaux et le nom dans le profil de l’utilisateur, sous `%LOCALAPPDATA%\DathemAgentV1\profile.json`. Il n’enregistre pas les images de la caméra. Le mot de passe est conservé sous forme d’empreinte dérivée avec PBKDF2, pas en texte clair. Les encodages faciaux restent des données biométriques sensibles ; ne partagez pas le profil et ne copiez pas celui du développeur vers le PC de l’ami. Chaque personne doit effectuer sa propre configuration sur son propre compte Windows.

## 5. Installer le service Windows

Ouvre **PowerShell en tant qu’administrateur**, avec le même compte Windows que celui qui vient d’effectuer l’inscription. Si la fenêtre a été ouverte sous un autre compte administrateur, le chemin `$HOME` peut être différent : remplace-le par le chemin réel du dossier `DathemAgentV1`.

Exécute :

```powershell
Set-Location "$HOME\Desktop\DathemAgentV1"
.\DathemAgentV1Service\DathemAgentV1Service.exe --startup manual install
```

Cette commande enregistre le service sous le nom `DathemAgentV1`, avec le démarrage manuel. Elle ne le démarre pas automatiquement à l’allumage de l’ordinateur.

Vérifie l’installation :

```powershell
sc.exe qc DathemAgentV1
```

Vérifie que `START_TYPE` indique `DEMAND_START` et que `BINARY_PATH_NAME` se termine par `DathemAgentV1Service\DathemAgentV1Service.exe`.

## 6. Démarrer DATHEM

Après avoir ouvert une session Windows sur le PC de l’ami, dans PowerShell administrateur :

```powershell
sc.exe start DathemAgentV1
Start-Sleep -Seconds 5
sc.exe query DathemAgentV1
```

L’état attendu est `RUNNING`. Pour vérifier que l’agent de bureau s’est lancé :

```powershell
Get-Process DathemAgentV1Agent -ErrorAction SilentlyContinue |
    Select-Object ProcessName, Id
```

Le service tourne en arrière-plan et surveille l’agent dans la session de bureau active. Si le PC redémarre, le service reste arrêté, car son démarrage est manuel : il faut refaire `sc.exe start DathemAgentV1` après ouverture de session.

## 7. Arrêter DATHEM

Dans PowerShell administrateur :

```powershell
sc.exe stop DathemAgentV1
Start-Sleep -Seconds 5
sc.exe query DathemAgentV1
```

L’état attendu est `STOPPED`. Le service doit aussi fermer l’agent de bureau qu’il a lancé. Une réponse `1062` signifie que le service était déjà arrêté ; vérifie alors `sc.exe query DathemAgentV1` et l’absence de processus :

```powershell
Get-Process DathemAgentV1Agent -ErrorAction SilentlyContinue
```

## 8. Désinstaller le service

Dans PowerShell administrateur, depuis le dossier d’installation :

```powershell
Set-Location "$HOME\Desktop\DathemAgentV1"
sc.exe stop DathemAgentV1
.\DathemAgentV1Service\DathemAgentV1Service.exe remove
sc.exe query DathemAgentV1
```

Si `sc.exe stop` répond `1062`, le service est déjà arrêté ; continue avec la commande `remove`. La désinstallation du service ne supprime pas le profil. Pour supprimer aussi le profil et les journaux locaux, arrête d’abord le service, puis ouvre PowerShell dans la session de l’utilisateur concerné et exécute cette commande seulement si tu veux effacer ses données DATHEM :

```powershell
Remove-Item -LiteralPath "$env:LOCALAPPDATA\DathemAgentV1" -Recurse -Force
```

## 9. Journaux et dépannage

Depuis le dossier d’installation, dans PowerShell :

```powershell
Get-Content .\DathemAgentV1-service.log -Tail 80 -ErrorAction SilentlyContinue
Get-Content "$env:LOCALAPPDATA\DathemAgentV1\agent.log" -Tail 80 -ErrorAction SilentlyContinue
```

- **Le service ne démarre pas** : `sc.exe query DathemAgentV1`, puis lire `DathemAgentV1-service.log` et les événements Windows.
- **Le service est `RUNNING`, mais aucune fenêtre ou caméra n’apparaît** : vérifier que l’utilisateur a ouvert une session locale, que la caméra est autorisée, que `profile.json` existe dans le compte de cet utilisateur et que le dossier `DathemAgentV1Agent` se trouve à côté du dossier `DathemAgentV1Service`.
- **Erreur SCM 7039** : vérifier que le service installé pointe sur `DathemAgentV1Service\DathemAgentV1Service.exe` (version `onedir`), et non sur l’ancien `DathemAgentV1.exe` (`onefile`). Contrôler avec `sc.exe qc DathemAgentV1`.
- **Erreur 1067 ou arrêt inattendu** : consulter les événements System et Application ainsi que le journal du service. `1067` indique que le processus de service s’est terminé de façon inattendue ; ce n’est pas une commande d’arrêt normale.
- **Assistant sans caméra** : fermer les applications qui utilisent la caméra et vérifier les autorisations Windows. L’assistant doit être lancé dans la session de l’utilisateur, pas depuis le service.
- **DLL d’exécution Visual C++ manquante** : installer le redistribuable Microsoft Visual C++ x64 depuis le site officiel de Microsoft, puis réessayer.

## Résumé des commandes quotidiennes

Dans PowerShell administrateur, après connexion au PC :

```powershell
sc.exe start DathemAgentV1   # démarrer
sc.exe query DathemAgentV1   # vérifier l’état
sc.exe stop DathemAgentV1    # arrêter
```

Le nom de service à utiliser dans toutes les commandes est `DathemAgentV1` (sans espace). Le nom affiché dans la console des services est `DATHEM Agent V1`.
