"""Interactive, local profile selection for the standalone Companion zipapp."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import runpy
import sys
from tempfile import NamedTemporaryFile
from urllib.parse import urlsplit

GENERIC = "registry-companion-start"
PROFILE_SUFFIX = ".profile.json"


class SetupError(Exception):
    """An operator-facing message that omits untrusted configuration values."""


def read_file(path):
    try:
        return path.read_bytes()
    except OSError:
        raise SetupError("Cannot read the selected file. Check its location and permissions; use New setup if it moved.") from None


def choose_config():
    answer = input("Dashboard JSON path (press Enter to browse): ").strip()
    if not answer:
        try:
            import tkinter
            from tkinter.filedialog import askopenfilename
            root = tkinter.Tk()
            try:
                root.withdraw()
                answer = askopenfilename(parent=root, title="Select Dashboard JSON",
                                         filetypes=[("Dashboard JSON", "*.json")])
            finally:
                root.destroy()
        except (ImportError, RuntimeError):
            answer = ""
        except tkinter.TclError:
            answer = ""
        if not answer:
            answer = input("Type or paste the Dashboard JSON path: ").strip()
    if len(answer) >= 2 and answer[0] == answer[-1] and answer[0] in "\"'":
        answer = answer[1:-1]
    if not answer:
        raise SetupError("No JSON selected. Open the launcher again to set up a profile.")
    return Path(answer).expanduser().resolve()


def health_url(value):
    try:
        u = urlsplit(value)
        if (u.scheme not in {"http", "https"} or not u.hostname or u.username is not None
                or u.password is not None or "?" in value or "#" in value):
            raise ValueError
        _ = u.port
    except (ValueError, TypeError):
        raise SetupError("Use a public, credential-free HTTP(S) health URL without query or fragment.") from None
    return value


def save(path, content, mode):
    # Publish complete files even if setup is interrupted.
    with NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        tmp = Path(handle.name)
    try:
        tmp.write_bytes(content)
        tmp.chmod(mode)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def choose_profile(directory):
    profiles = sorted(directory.glob("start-*" + PROFILE_SUFFIX))
    if not profiles:
        return None
    for index, profile in enumerate(profiles, 1):
        print(f"  {index}. {profile.name.removesuffix(PROFILE_SUFFIX)}")
    answer = input("Choose a profile [1], or N for New setup: ").strip().lower()
    if answer == "n":
        return None
    if not answer:
        return profiles[0]
    if answer.isascii() and answer.isdecimal() and len(answer) < 9 and 1 <= int(answer) <= len(profiles):
        return profiles[int(answer) - 1]
    raise SetupError("Choose a listed profile number or N for New setup.")


def desktop_entry(shortcut):
    # Desktop Entry Exec has its own quoting and % field codes, separate from sh.
    argument = str(shortcut)
    for char in ('\\', '"', '$', chr(96)):
        argument = argument.replace(char, '\\' + char)
    argument = argument.replace('\\', '\\\\').replace('%', '%%')
    return (f"[Desktop Entry]\nType=Application\nName={shortcut.stem}\n"
            f'Exec=/bin/sh "{argument}"\nTerminal=true\n')


def setup(directory, suffix, companion):
    config = choose_config()
    snapshot = read_file(config)
    health = health_url(input("Agent health URL (HTTP GET returning 2xx): ").strip())
    code = companion["main"](["check", "--config", str(config), "--health-url", health])
    if code:
        print("Check failed. Fix the issue above and run New setup again.", file=sys.stderr)
        return code, None
    if snapshot != read_file(config):
        raise SetupError("The JSON changed during check. Run New setup again.")
    card = json.loads(snapshot.decode("utf-8-sig"))
    agent = card["AGENT_ID"]
    origin = companion["validate_url"](card["REGISTRY_URL"], registry=True)
    identity = hashlib.sha256(f"{origin}/{agent}".encode()).hexdigest()[:12]
    stem = f"start-{agent}-{identity}"
    shortcut = directory / (stem + suffix)
    profile = directory / (stem + PROFILE_SUFFIX)
    settings = {"config": str(config), "health_url": health, "sha256": hashlib.sha256(snapshot).hexdigest()}
    save(shortcut, read_file(directory / (GENERIC + suffix)), 0o700)
    save(profile, (json.dumps(settings, indent=2) + "\n").encode(), 0o600)
    if suffix == ".sh" and not any(ord(c) < 32 for c in str(shortcut)):
        save(shortcut.with_suffix(".desktop"), desktop_entry(shortcut).encode(), 0o700)
    print(f"Profile saved. Next time open {shortcut.name}", flush=True)
    return 0, profile


def launch(wrapper, new_setup):
    directory = Path(__file__).resolve().parent
    artifact = directory / "registry-companion.pyz"
    if not artifact.is_file():
        raise SetupError("Missing registry-companion.pyz. Extract the entire kit and try again.")
    # Run the release CLI in this foreground process so it owns the console signals.
    companion = runpy.run_path(str(artifact))
    if wrapper.stem == GENERIC:
        profile = None if new_setup else choose_profile(directory)
    elif re.fullmatch(r"start-[A-Za-z0-9_.-]+-[a-f0-9]{12}", wrapper.stem):
        profile = directory / (wrapper.stem + PROFILE_SUFFIX)
    else:
        raise SetupError("Open the original launcher or the per-Agent file created by setup.")
    if profile is None:
        code, profile = setup(directory, wrapper.suffix, companion)
        if code:
            return code
    try:
        settings = json.loads(read_file(profile))
        config = Path(settings["config"])
        health = health_url(settings["health_url"])
        expected = settings["sha256"]
    except (KeyError, ValueError, TypeError):
        raise SetupError("Invalid profile. Open the generic launcher and choose New setup.") from None
    if not config.is_absolute() or hashlib.sha256(read_file(config)).hexdigest() != expected:
        raise SetupError("Dashboard JSON changed. Review its Registry URL, then run New setup to validate it again.")
    return companion["main"](["start", "--config", str(config), "--health-url", health])


def main():
    parser = argparse.ArgumentParser(description="Launch Registry Companion with a local profile.")
    parser.add_argument("wrapper", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--setup", action="store_true", help="Open New setup on the generic launcher")
    args = parser.parse_args()
    try:
        code = launch(args.wrapper, args.setup)
    except (EOFError, KeyboardInterrupt):
        return 130
    except SetupError as exc:
        print(exc, file=sys.stderr)
        code = 2
    except OSError:
        print("Check file permissions. Extract the complete kit to a writable folder owned by your user.", file=sys.stderr)
        code = 2
    if code and sys.stdin.isatty():
        try:
            input("Press Enter to close.")
        except (EOFError, KeyboardInterrupt):
            pass
    return code


if __name__ == "__main__":
    sys.exit(main())
