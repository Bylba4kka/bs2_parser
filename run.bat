@echo off

:: Убедимся, что текущая директория правильная
cd /d "%~dp0"

:: Устанавливаем кодировку UTF-8
chcp 65001 >nul

:: Проверяем, установлен ли Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python не установлен или не добавлен в PATH. Установите Python и повторите попытку.
    pause
    exit /b
)

:: Проверяем наличие виртуальной среды
if not exist "venv" (
    echo Виртуальная среда не найдена. Создаем виртуальную среду...
    python -m venv venv
)

    :: Активируем виртуальную среду
    call venv\Scripts\activate

    :: Устанавливаем зависимости, если есть requirements.txt
    if exist "requirements.txt" (
        echo Устанавливаем зависимости из requirements.txt...
        pip install -r requirements.txt
    )

call venv\Scripts\activate

:: Запускаем Python-скрипт
python main.py

:: Завершаем работу
echo Завершено!
pause
