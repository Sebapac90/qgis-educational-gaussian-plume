"""Build a QGIS-installable ZIP, resolving development symlinks to real files."""
from pathlib import Path
import hashlib
import json
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "qgis_plugin/gaussian_educativo"
DIST = ROOT / "dist"
VERSION = "0.14.0"


def main():
    DIST.mkdir(exist_ok=True)
    archive = DIST / "gaussian_educativo-{}.zip".format(VERSION)
    files = [path for path in SOURCE.rglob("*")
             if path.is_file() and "__pycache__" not in path.parts]
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(files):
            relative = path.relative_to(SOURCE)
            bundle.writestr(str(Path("gaussian_educativo") / relative),
                            path.read_bytes())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    manifest = {"plugin": "gaussian_educativo", "version": VERSION,
                "archive": str(archive), "sha256": digest,
                "files": len(files)}
    (DIST / "gaussian_educativo-{}.json".format(VERSION)).write_text(
        json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))
    return archive


if __name__ == "__main__":
    main()
