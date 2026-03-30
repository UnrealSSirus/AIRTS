"""Build script — creates AIRTS.exe via PyInstaller.

Usage::

    pip install pyinstaller
    python build_exe.py
"""
import PyInstaller.__main__
import glob
import shutil
import os

DIST_DIR = os.path.join("dist", "AIRTS")

# Auto-discover all AI modules for hidden imports
hidden_imports = [
    "--hidden-import=numpy",
    "--hidden-import=pygame",
    "--hidden-import=systems.ai.base",
]

# Built-in AIs (systems/ai/*.py)
for f in glob.glob(os.path.join("systems", "ai", "*.py")):
    name = os.path.splitext(os.path.basename(f))[0]
    if not name.startswith("_"):
        hidden_imports.append(f"--hidden-import=systems.ai.{name}")

# User AIs (ais/*.py)
for f in glob.glob(os.path.join("ais", "*.py")):
    name = os.path.splitext(os.path.basename(f))[0]
    if not name.startswith("_"):
        hidden_imports.append(f"--hidden-import=ais.{name}")

PyInstaller.__main__.run([
    "main.py",
    "--name=AIRTS",
    "--onedir",
    "--windowed",
    # Bundled read-only assets
    "--add-data=sounds;sounds",
    "--add-data=sprites;sprites",
    # Clean build
    "--noconfirm",
    *hidden_imports,
])

# Copy .env.example as .env next to the exe so players can edit it
env_dest = os.path.join(DIST_DIR, ".env")
if not os.path.exists(env_dest):
    shutil.copy(".env.example", env_dest)
    print(f"Copied .env.example -> {env_dest}")

print()
print("=" * 50)
print(f"Build complete!  ->  {DIST_DIR}/AIRTS.exe")
print()
print("To distribute:")
print(f"  1. Edit {env_dest} with your server's public IP")
print(f"  2. Zip the entire {DIST_DIR}/ folder")
print("  3. Send the zip to players")
print("=" * 50)
