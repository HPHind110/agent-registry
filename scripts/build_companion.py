"""Build the portable zipapp with stable bytes on Windows and Linux."""
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]


def build(target):
    source = (ROOT / "companion/cli.py").read_text(encoding="utf-8").encode("utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    entry = ZipInfo("__main__.py", date_time=(1980, 1, 1, 0, 0, 0))
    entry.create_system = 3
    entry.external_attr = 0o100644 << 16
    with ZipFile(target, "w") as archive:
        archive.writestr(entry, source)
    return sha256(target.read_bytes()).hexdigest()


def build_kit(target, artifact):
    """Bundle the current standalone CLI and launchers for direct extraction."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(target, "w") as archive:
        for name in ("registry-companion.pyz", "registry-companion-start.cmd",
                     "registry-companion-start.sh", "registry_companion_launcher.py"):
            if name.endswith(".pyz"):
                content = artifact.read_bytes()
            else:
                source = (ROOT / "downloads" / name).read_text(encoding="utf-8")
                content = (source.replace("\n", "\r\n") if name.endswith(".cmd") else source).encode()
            entry = ZipInfo(name)
            entry.create_system = 3
            entry.external_attr = (0o100755 if name.endswith(".sh") else 0o100644) << 16
            archive.writestr(entry, content)
    return sha256(target.read_bytes()).hexdigest()


if __name__ == "__main__":
    target = ROOT / "downloads/registry-companion.pyz"
    print(build(target), target.name)
    kit = target.with_name("registry-companion-kit.zip")
    print(build_kit(kit, target), kit.name)
