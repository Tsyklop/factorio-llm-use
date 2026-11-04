"""Build a normal Factorio mod ZIP from this repository's source."""

import zipfile
from pathlib import Path


def package(destination: Path | None = None) -> Path:
    root = Path(__file__).resolve().parents[1]
    source = root / "mod/factorio_llm_use_0.1.0"
    destination = destination or root / "dist"
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / f"{source.name}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                output.write(path, path.relative_to(source.parent).as_posix())
        output.write(root / "LICENSE", source.name + "/LICENSE")
    with zipfile.ZipFile(archive) as check:
        if check.testzip() is not None:
            raise RuntimeError("Archive integrity check failed")
    return archive


if __name__ == "__main__":
    print(package())
