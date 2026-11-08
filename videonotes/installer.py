"""Build a *private* offline Windows setup EXE from an already verified bundle.

No downloads, no private media in source control. Requires the user's own
Inno Setup compiler, verified local FFmpeg/Whisper executable and model. An
INTERNAL setup is not a signed/reviewed product release.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from .bundle import BUNDLE_FILES, verify_internal_bundle
from .errors import VideoNotesError

INSTALLER_NAME = "VideoNotes-INTERNAL-Setup.exe"
APP_ID = "{{A6AF95B7-7B59-4ACD-A254-A1C2A8ED4F17}"


def _iss_path(path: Path) -> str:
    """Inno Setup Source directive: prevent newline/control and quote breakout."""
    value = str(path.resolve())
    if any(ord(c) < 32 or c in '"{}' for c in value):
        raise VideoNotesError("Ścieżka pakietu zawiera znaki niedozwolone w skrypcie instalatora.")
    return value


def installer_script(bundle: Path, destination: Path) -> str:
    """Inno script includes exactly bundle-verified, local dependency bytes."""
    root = Path(bundle).expanduser().resolve()
    staging = Path(destination).expanduser().resolve()
    manifest_files = sorted(BUNDLE_FILES)
    helper_files = ["START-VIDEO-NOTES.cmd", "INTERNAL-ONLY.txt",
                    "bundle-manifest.json"]
    lines = [
        "; LOCAL PRIVATE TEST INSTALLER - do not distribute",
        "[Setup]",
        f"AppId={APP_ID}",
        "AppName=Video Notes INTERNAL TEST",
        "AppVersion=0.0-dev",
        "AppPublisher=Video Notes (private testing only)",
        r"DefaultDirName={localappdata}\Programs\VideoNotes-Internal",
        "DefaultGroupName=Video Notes INTERNAL",
        "PrivilegesRequired=lowest",
        "Uninstallable=yes",
        "DisableProgramGroupPage=yes",
        "DisableWelcomePage=no",
        "WizardStyle=modern",
        "CloseApplications=no",
        "RestartApplications=no",
        "OutputDir=" + _iss_path(staging),
        "OutputBaseFilename=VideoNotes-INTERNAL-Setup",
        "Compression=lzma2",
        "SolidCompression=yes",
        "SetupLogging=yes",
        "",
        "[Files]",
    ]
    for relative in manifest_files + helper_files:
        source = _iss_path(root / relative)
        folder = r"{app}\bin" if relative.startswith("bin/") else "{app}"
        lines.append(f'Source: "{source}"; DestDir: "{folder}"; Flags: ignoreversion')
    lines.extend([
        "",
        "[Icons]",
        r'Name: "{userprograms}\Video Notes INTERNAL TEST"; Filename: "{app}\START-VIDEO-NOTES.cmd"',
        "",
        "[Run]",
        "; Deliberately no automatic execution after installation",
    ])
    return "\r\n".join(lines) + "\r\n"


def build_internal_installer(*, bundle: Path, iscc: Path, output: Path,
                             internal_only: bool = False,
                             process_runner=subprocess.run) -> dict:
    """Compile a full offline setup EXE without replacing previous artifacts.

    Fail closed on compiler errors, missing model, malformed bundle or races.
    Never interpret arbitrary compiler output as proof of licensing/safety.
    """
    if internal_only is not True:
        raise VideoNotesError("Wymagane jawne --internal-only; to nie jest wydanie publiczne.")
    if sys.platform != "win32":
        raise VideoNotesError("Kompilacja instalatora lokalnego wymaga Windows.")
    root = Path(bundle).expanduser()
    verify_internal_bundle(root)
    compiler = Path(iscc).expanduser()
    if compiler.is_symlink() or not compiler.is_file() or compiler.suffix.lower() != ".exe":
        raise VideoNotesError("Wymagany jest lokalny plik ISCC.exe Inno Setup.")
    output = Path(output).expanduser().absolute()
    if output.suffix.lower() != ".exe" or output.exists() or output.is_symlink():
        raise VideoNotesError("Wybierz nowy, nieistniejący plik wynikowy instalatora .exe.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix=".vn-installer-") as scratch:
        staging = Path(scratch)
        script = staging / "install.iss"
        script.write_text(installer_script(root, staging), encoding="utf-8-sig")
        try:
            result = process_runner(
                [str(compiler.resolve()), "/Q", str(script)],
                cwd=staging, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                shell=False, timeout=900, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise VideoNotesError(
                "Kompilator Inno Setup nie uruchomił się lub przekroczył limit. "
                "Oryginalny pakiet pozostaje bez zmian."
            ) from error
        artifact = staging / INSTALLER_NAME
        if result.returncode != 0 or artifact.is_symlink() or not artifact.is_file() or artifact.stat().st_size < 1024:
            raise VideoNotesError("Kompilacja Inno Setup nie utworzyła poprawnego prywatnego instalatora.")
        with artifact.open("rb") as reader:
            if reader.read(2) != b"MZ":
                raise VideoNotesError("Wynik kompilacji nie ma nagłówka Windows PE.")
        # The compiler only read source bundle. Verify it AGAIN before publish
        # to catch concurrent source modification after initial verification.
        verify_internal_bundle(root)
        try:
            os.link(artifact, output)
        except FileExistsError as error:
            raise VideoNotesError("Instalator powstał równolegle; nie nadpisuję pliku.") from error
        except OSError as error:
            raise VideoNotesError("Dysk nie obsługuje bezpiecznej publikacji instalatora bez nadpisania.") from error
    checksum = hashlib.sha256()
    with output.open("rb") as reader:
        for block in iter(lambda: reader.read(2 * 1024 * 1024), b""):
            checksum.update(block)
    return {
        "output": str(output),
        "sha256": checksum.hexdigest(),
        "distribution": "internal-only",
        "offline_payload_included": True,
        "license_verified": False,
        "signed": False,
        "physical_windows_tested": False,
        "release_ready": False,
    }
