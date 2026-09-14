from pathlib import Path
import shutil

Path("dist").mkdir()
shutil.copyfile("app.html", "dist/index.html")
