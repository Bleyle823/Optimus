"""Fixed: stand-in for the Unix pwd module so peaqos can import on Windows.

peaq uses this only to chown a rendered file to a local OS user. Solana
activation does not call it. A real owner lookup still fails closed.
"""

from __future__ import annotations


class struct_passwd:
    def __init__(self, name: str) -> None:
        self.pw_name = name
        self.pw_uid = -1
        self.pw_gid = -1


def getpwnam(name: str) -> struct_passwd:
    raise KeyError(name)
