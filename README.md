# DATHEM Agent V1

DATHEM Agent V1 est un projet Windows en Python qui surveille la caméra et reconnaît les visages inscrits localement. Un service Windows supervise un agent graphique lancé dans la session de l’utilisateur connecté. Lorsqu’un visage inconnu ou une absence prolongée est détecté, l’agent peut afficher l’écran DATHEM et demander le mot de passe choisi lors de l’inscription.

Le service est en **démarrage manuel** : après le démarrage de Windows, l’utilisateur ouvre sa session puis lance DATHEM avec `sc.exe start DathemAgentV1`. L’interface est exécutée dans la session utilisateur, car un service Windows ne peut pas afficher directement sa fenêtre sur le bureau de connexion sécurisé.

> DATHEM utilise la caméra et traite localement des données biométriques. Installe-le uniquement avec l’accord du propriétaire du PC. Chaque utilisateur doit créer son propre profil. L’écran DATHEM est une fenêtre de l’application et ne remplace pas l’écran de verrouillage sécurisé de Windows.

## Sources du projet

Le `.gitignore` autorise uniquement les sources du service et leur documentation :

| Fichier | Fonction |
|---|---|
| `service.py` | Service Windows et supervision de l’agent dans la session utilisateur |
| `guard.py` | Lecture de la caméra, détection et reconnaissance des visages |
| `lock_screen.py` | Écran DATHEM, animations, jeu et vérification du mot de passe |
| `setup.py` | Assistant d’inscription avec caméra |
| `dathem_config.py` | Configuration et chemins des profils et journaux locaux |
| `eyes.jpg` | Image d’arrière-plan de l’interface |
| `requirements.txt` | Dépendances Python et outil de compilation |
| `guide.md` | Instructions de mise à jour et d’installation sur un autre PC |
| `linkedin.txt` | Brouillon de présentation du projet |

Les profils, journaux, données d’encodage facial, environnements virtuels, exécutables compilés et anciens fichiers ne doivent pas être ajoutés au dépôt.

## Construire et installer le service depuis le dépôt GitHub

Les étapes suivantes permettent de récupérer les sources sur un PC Windows 10/11 64 bits, de construire les trois composants, puis d’installer et lancer le service sur ce même PC. Elles ne créent pas de paquet de transfert.

### 1. Récupérer le code

Installe Git et Python 3.11 64 bits si nécessaire. Dans **PowerShell normal**, remplace l’URL par celle du dépôt GitHub :

```powershell
git clone https://github.com/UTILISATEUR/dathem.git "$HOME\Desktop\face guard"
Set-Location "$HOME\Desktop\face guard"
py -3.11 --version
```

La dernière commande doit afficher Python 3.11.x. Si le dépôt est déjà présent sur le PC, passe directement à `Set-Location` avec son chemin.

### 2. Installer les dépendances

Toujours dans PowerShell normal, à la racine du dépôt :

```powershell
py -3.11 -m venv .\venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r .\requirements.txt
```

Le dossier `venv` est local et ignoré par Git. `face_recognition` s’appuie notamment sur dlib; son installation peut prendre du temps ou nécessiter les outils Windows compatibles avec l’environnement Python.

### 3. Construire l’agent graphique

Dans la même fenêtre PowerShell, depuis la racine du dépôt :

```powershell
$projectDir = (Get-Location).Path
.\venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onedir --windowed --name DathemAgentV1Agent --distpath .\dist\DathemAgentV1 --workpath .\build\dathem-agent-v1 --specpath .\build --add-data "$projectDir\eyes.jpg;." --collect-all face_recognition_models .\guard.py
```

La sortie est `dist\DathemAgentV1\DathemAgentV1Agent`. Le dossier entier, dont `_internal`, est nécessaire à l’exécution.

### 4. Construire le service Windows

```powershell
.\venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onedir --name DathemAgentV1Service --distpath .\dist\DathemAgentV1 --workpath .\build\dathem-service-v1 --specpath .\build --hidden-import win32timezone .\service.py
```

La sortie est `dist\DathemAgentV1\DathemAgentV1Service`. Garde le dossier entier, y compris `_internal`.

### 5. Construire l’assistant d’inscription

```powershell
.\venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --name DathemAgentV1Setup --distpath .\dist\DathemAgentV1 --workpath .\build\dathem-setup-v1 --specpath .\build --collect-all face_recognition_models .\setup.py
```

Vérifie que les trois exécutables attendus existent :

```powershell
Test-Path .\dist\DathemAgentV1\DathemAgentV1Agent\DathemAgentV1Agent.exe
Test-Path .\dist\DathemAgentV1\DathemAgentV1Service\DathemAgentV1Service.exe
Test-Path .\dist\DathemAgentV1\DathemAgentV1Setup.exe
```

Les trois résultats doivent être `True`. N’utilise pas un ancien `DathemAgentV1.exe` qui pourrait rester à la racine après une compilation précédente.

### 6. Inscrire l’utilisateur du PC

L’inscription doit être faite dans la session Windows de la personne qui utilisera DATHEM. Ouvre **PowerShell normal**, puis :

```powershell
Set-Location "$HOME\Desktop\face guard\dist\DathemAgentV1"
& .\DathemAgentV1Setup.exe
```

Suis l’assistant pour saisir le nom, choisir le mot de passe et prendre les captures avec la caméra. Le profil est créé dans `%LOCALAPPDATA%\DathemAgentV1` pour cet utilisateur. Vérifie sa présence sans afficher son contenu :

```powershell
Test-Path "$env:LOCALAPPDATA\DathemAgentV1\profile.json"
```

Le résultat attendu est `True`. Ne copie pas le profil d’un autre utilisateur.

## Fluidité de l’assistant d’inscription

L’assistant sépare maintenant la caméra, la détection et l’interface pour éviter de figer l’aperçu pendant les calculs :

- La caméra conserve la dernière image disponible et demande une résolution de 640×480 avec une mémoire tampon courte.
- L’interface actualise l’aperçu à un intervalle cible de 33 ms. La détection de guidage travaille sur une image réduite à 50 % et attend 120 ms après chaque analyse avant de recommencer; la durée de calcul s’ajoute à cet intervalle.
- Au clic sur **Capturer**, l’assistant réutilise l’image pleine résolution correspondant à la dernière détection. Il encode le visage en arrière-plan et évite une deuxième détection complète, pendant que l’aperçu continue de s’actualiser.
- Le temps affiché à côté du numéro de capture mesure le délai du clic jusqu’à la fin de l’encodage. Les images de caméra ne sont pas enregistrées dans le profil.

Les intervalles de 33 ms et 120 ms sont des objectifs de rafraîchissement, pas une garantie de fréquence d’images. Le résultat dépend du processeur, de la caméra, du pilote, de l’éclairage et de la distance du visage.

Pour transférer cette version sur un autre PC, mettre à jour une installation existante ou faire une première installation, suis le [guide d’installation pour les amis](guide.md).

### 7. Installer et lancer le service

Ouvre **PowerShell en tant qu’administrateur**, sur le même PC :

```powershell
Set-Location "$HOME\Desktop\face guard\dist\DathemAgentV1"
.\DathemAgentV1Service\DathemAgentV1Service.exe --startup manual install
sc.exe qc DathemAgentV1
sc.exe start DathemAgentV1
Start-Sleep -Seconds 5
sc.exe query DathemAgentV1
```

Dans `sc.exe qc`, vérifie `START_TYPE : 3 DEMAND_START`. L’état attendu après le démarrage est `RUNNING`. Pour confirmer que l’agent graphique a été lancé :

```powershell
Get-Process DathemAgentV1Agent -ErrorAction SilentlyContinue |
    Select-Object ProcessName, Id
```

Après chaque redémarrage de Windows, ouvre la session utilisateur puis exécute `sc.exe start DathemAgentV1` dans PowerShell administrateur. Pour arrêter et vérifier :

```powershell
sc.exe stop DathemAgentV1
sc.exe query DathemAgentV1
```

Attends l’état `STOPPED`.
