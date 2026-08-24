"""Setuptools compatibility hook for reproducible source distributions."""

from __future__ import annotations

import gzip
import os
import tarfile
from pathlib import Path

from setuptools import setup
from setuptools.command.sdist import sdist as SetuptoolsSdist


class ReproducibleSdist(SetuptoolsSdist):
    """Normalize archive metadata when SOURCE_DATE_EPOCH is explicitly set."""

    def make_release_tree(self, base_dir: str, files: list[str]) -> None:
        super().make_release_tree(base_dir, files)
        epoch = os.environ.get("SOURCE_DATE_EPOCH")
        if epoch is None:
            return
        timestamp = int(epoch)
        for path in sorted(Path(base_dir).rglob("*")):
            os.utime(path, (timestamp, timestamp))

    def make_archive(
        self,
        base_name: str | os.PathLike[str],
        format: str,
        root_dir: str | os.PathLike[str] | bytes | os.PathLike[bytes] | None = None,
        base_dir: str | None = None,
        owner: str | None = None,
        group: str | None = None,
    ) -> str:
        epoch = os.environ.get("SOURCE_DATE_EPOCH")
        if epoch is None or format != "gztar":
            return super().make_archive(base_name, format, root_dir, base_dir, owner, group)
        timestamp = int(epoch)
        archive = Path(os.fspath(base_name) + ".tar.gz")
        archive.parent.mkdir(parents=True, exist_ok=True)
        root = Path(os.fsdecode(root_dir)) if root_dir is not None else Path.cwd()
        source = root / (base_dir or ".")

        def normalize(info: tarfile.TarInfo) -> tarfile.TarInfo:
            info.mtime = timestamp
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            return info

        with (
            archive.open("wb") as raw,
            gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=timestamp) as compressed,
            tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as tar,
        ):
            tar.add(source, arcname=base_dir or source.name, filter=normalize)
        return str(archive)


setup(cmdclass={"sdist": ReproducibleSdist})
