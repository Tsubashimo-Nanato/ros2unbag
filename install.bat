@echo off
setlocal
cd /d "%~dp0"

set "EXTRA="
if /I "%~1"=="gui" set "EXTRA=[gui]"
if /I "%~1"=="--gui" set "EXTRA=[gui]"

echo Installing ROSBagel%EXTRA% from %CD%
py -m pip install -e ".%EXTRA%"
if errorlevel 1 exit /b %ERRORLEVEL%

for /f "delims=" %%I in ('py -c "import sysconfig; print(sysconfig.get_path('scripts'))"') do set "PY_SCRIPTS=%%I"
if not defined PY_SCRIPTS (
    echo Could not determine the Python Scripts directory.
    echo You can still run ROSBagel with: .\bagel.bat
    exit /b 0
)

echo Python Scripts directory: %PY_SCRIPTS%
powershell -NoProfile -ExecutionPolicy Bypass -Command "$scripts = '%PY_SCRIPTS%'; $userPath = [Environment]::GetEnvironmentVariable('Path', 'User'); if (-not $userPath) { $userPath = '' }; $parts = @($userPath -split ';' | Where-Object { $_ }); if ($parts -notcontains $scripts) { [Environment]::SetEnvironmentVariable('Path', (($parts + $scripts) -join ';'), 'User'); Write-Host 'Added to user PATH:' $scripts } else { Write-Host 'Already on user PATH:' $scripts }"
if errorlevel 1 (
    echo Could not update the user PATH automatically.
    echo You can add this directory manually: %PY_SCRIPTS%
)

echo.
echo Install complete.
echo Restart your terminal before using "bagel" directly.
echo In this repository, you can always run: .\bagel.bat
echo Optional GUI install: install.bat gui
