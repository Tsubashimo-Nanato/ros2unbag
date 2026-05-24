@echo off
setlocal
cd /d "%~dp0"

echo Uninstalling ros2unbag and declared runtime dependencies...
py -m ros2unbag.cli.main uninstall --yes
if errorlevel 1 (
    echo ros2unbag module uninstall command failed; trying pip fallback.
    py -m pip uninstall -y ros2unbag rosbag-inspector rosbags numpy pandas pyarrow opencv-python pillow typer rich prompt-toolkit PySide6 PySide6-Addons PySide6-Essentials shiboken6 vispy PyOpenGL apsw lz4 ruamel.yaml zstandard typing-extensions click shellingham annotated-doc markdown-it-py mdurl pygments colorama wcwidth
)

echo.
echo Uninstall command finished.
echo The Python Scripts directory is not removed from PATH because it may be shared by other Python tools.
