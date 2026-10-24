"""Verify wheel identity against isolated installed metadata before excluding it."""

from email.parser import BytesParser
from importlib.metadata import distributions
from pathlib import Path
import re
from zipfile import ZipFile


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def inventory(site_packages: Path, wheel: Path) -> tuple[tuple[str, str], dict[str, str]]:
    with ZipFile(wheel) as archive:
        names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
        if len(names) != 1:
            raise ValueError("Ambiguous wheel metadata")
        metadata = BytesParser().parsebytes(archive.read(names[0]))
    name, version = metadata.get("Name", ""), metadata.get("Version", "")
    if not name or not version:
        raise ValueError("Missing candidate identity")
    candidate = (normalize(name), version)
    installed: dict[str, str] = {}
    for dist in distributions(path=[str(site_packages)]):
        package = normalize(dist.metadata["Name"] or "")
        release = dist.version
        if (
            not re.fullmatch(r"[a-z0-9][a-z0-9-]*", package)
            or not release
            or not re.fullmatch(r"[a-zA-Z0-9.!+_-]+", release)
        ):
            raise ValueError("Invalid installed identity")
        if package in installed:
            raise ValueError("Duplicate installed identity")
        installed[package] = release
    if installed.pop(candidate[0], None) != candidate[1] or not installed:
        raise ValueError("Candidate mismatch or empty third-party inventory")
    return candidate, installed
