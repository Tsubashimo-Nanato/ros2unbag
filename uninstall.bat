@echo off
setlocal
cd /d "%~dp0"

echo Starting the ROSBagel uninstaller...
py -m rosbagel.cli.main uninstall
if errorlevel 1 (
    echo ROSBagel uninstaller failed.
    echo Fallback: py -m pip uninstall ROSBagel
    exit /b 1
)

echo.
echo Uninstall command finished.
echo The bagel command is removed by pip. The shared Python Scripts PATH entry is preserved.
