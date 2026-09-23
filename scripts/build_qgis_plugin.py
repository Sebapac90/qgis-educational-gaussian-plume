"""Build a QGIS-installable ZIP, resolving development symlinks to real files."""
from pathlib import Path
import hashlib
import json
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "qgis_plugin/gaussian_educativo"
DIST = ROOT / "dist"
VERSION = "0.15.0"
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def main():
    DIST.mkdir(exist_ok=True)
    archive = DIST / "gaussian_educativo-{}.zip".format(VERSION)
    files = []
    for path in SOURCE.rglob("*"):
        relative = path.relative_to(SOURCE)
        if (not path.is_file() or "__pycache__" in relative.parts or
                any(part.startswith(".") for part in relative.parts) or
                path.suffix in (".pyc", ".pyo")):
            continue
        files.append(path)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(files):
            relative = path.relative_to(SOURCE)
            name = (Path("gaussian_educativo") / relative).as_posix()
            info = zipfile.ZipInfo(name, date_time=ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, path.read_bytes())
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
