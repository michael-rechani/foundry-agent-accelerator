import hashlib
import io
import stat
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


RUNTIME_FILES = ("main.py", "demo_tools.py", "requirements.txt")
RUNTIME_DIRECTORY = Path(__file__).with_name("agent_runtime")


def runtime_package(directory=RUNTIME_DIRECTORY):
    output = io.BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for name in RUNTIME_FILES:
            source = (directory / name).read_bytes()
            if len(source) > 65536:
                raise ValueError("A runtime source file exceeds 65536 bytes")
            info = ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            # Foundry's remote build requires the Unix regular-file type bit.
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, source)
    package = output.getvalue()
    return package, hashlib.sha256(package).hexdigest()
