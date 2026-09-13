@echo off
echo ========================================
echo     Bot Discord EMS - Lancement
echo ========================================
echo.

REM Vérifier si config.json existe
if not exist "config.json" (
    echo [ERREUR] Le fichier config.json n'existe pas !
    echo Veuillez créer config.json avec votre TOKEN et les IDs des salons.
    pause
    exit /b 1
)

REM Vérifier si .venv existe
if not exist ".venv" (
    echo [INFO] Création de l'environnement virtuel...
    python -m venv .venv
)

REM Activer l'environnement virtuel
call .venv\Scripts\activate.bat

REM Installer les dépendances
echo [INFO] Installation des dépendances...
python -m pip install -q -r requirements.txt

REM Lancer le bot
echo.
echo [INFO] Lancement du bot EMS...
echo.
python main.py

pause
