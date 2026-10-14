import sys,tarfile
from pathlib import Path
archive=Path(sys.argv[1]);destination=Path(sys.argv[2]).resolve()
with tarfile.open(archive) as data:
    for member in data.getmembers():
        target=(destination/member.name).resolve()
        if not target.is_relative_to(destination) or member.issym() or member.islnk():
            raise ValueError('Unsafe runtime archive member')
    data.extractall(destination,filter='data')
