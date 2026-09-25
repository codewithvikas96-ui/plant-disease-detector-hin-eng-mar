@echo off
REM One-time setup: creates a project-local virtual environment and installs
REM everything into it. Nothing is installed system-wide.
cd /d "%~dp0.."

echo Creating virtual environment in .venv ...
py -3 -m venv .venv || (echo [!] Python 3 not found on PATH & pause & exit /b 1)

echo Installing dependencies ^(this downloads ~250 MB, takes a few minutes^) ...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt

if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo Created .env - paste your Groq API key into it to enable the AI assistant.
)

echo.
echo Setup complete. Next:
echo   1. Train the model on Colab  ^(training\train_plantvillage.ipynb^)
echo   2. Put plant_disease_model.pt into backend\models\
echo   3. Optional: put your Groq key in .env  ^(https://console.groq.com/keys^)
echo   4. Run scripts\start.bat
pause
