@echo off
REM Double-click this to start the app. Keep the window open during the demo.
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
    echo [!] Virtual environment missing. Run scripts\setup.bat first.
    pause
    exit /b 1
)

if not exist "backend\models\plant_disease_model.pt" (
    echo [!] No trained model found in backend\models\
    echo     The app will start but diagnosis will not work.
    echo     Train training\train_plantvillage.ipynb on Colab first.
    echo.
)

echo Starting server...
echo Open on this PC:   http://localhost:8000
echo Open on a phone:   see the "lan_url" printed below (same Wi-Fi)
echo Press Ctrl+C to stop.
echo.

.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
pause
