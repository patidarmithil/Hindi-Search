"""Package the assignment submission into submission/.

Usage:  python scripts/make_submission.py [--roll S20240010143]

Creates:
    submission/<roll>-src.zip                      engine, cli, scripts, tests (no website code)
    submission/README.txt                          copy of README.md
    submission/output.txt                          copy of output/test_cases.txt
    submission/<roll>-A1-PostIndex-IR-M2026.zip    the three files above
"""
import argparse
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "submission"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--roll", default="S20240010143")
    roll = ap.parse_args().roll

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()

    files = ["cli.py", "requirements.txt", "README.md"]
    for d in ("engine", "scripts", "tests"):
        for p in sorted((ROOT / d).rglob("*.py")):
            if "__pycache__" in p.parts or p.name == "test_api.py":  # test_api needs the website backend
                continue
            files.append(p.relative_to(ROOT).as_posix())

    src_zip = OUT / f"{roll}-src.zip"
    with zipfile.ZipFile(src_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(ROOT / f, f"{roll}-src/{f}")
        for d in ("output", "index", "corpus", "wiki_raw"):  # empty folders the programs write into
            z.writestr(f"{roll}-src/{d}/.gitkeep", "")

    shutil.copy(ROOT / "README.md", OUT / "README.txt")
    shutil.copy(ROOT / "output" / "test_cases.txt", OUT / "output.txt")

    final = OUT / f"{roll}-A1-PostIndex-IR-M2026.zip"
    with zipfile.ZipFile(final, "w", zipfile.ZIP_DEFLATED) as z:
        for name in ("README.txt", src_zip.name, "output.txt"):
            z.write(OUT / name, name)

    for f in (src_zip, final):
        print(f"{f.relative_to(ROOT)}  ({f.stat().st_size / 1024:.0f} KB)")
        with zipfile.ZipFile(f) as z:
            for n in z.namelist():
                print("   ", n)


if __name__ == "__main__":
    main()
