"""Apply OS limits in a fresh process before exec; no preexec_fn in threads."""
from __future__ import annotations

import os
import resource
import sys


def main():
    memory, cpu, output, descriptors = map(int, sys.argv[1:5])
    for limit, value in ((resource.RLIMIT_AS, memory), (resource.RLIMIT_CPU, cpu),
                         (resource.RLIMIT_FSIZE, output), (resource.RLIMIT_NOFILE, descriptors),
                         (resource.RLIMIT_CORE, 0)):
        resource.setrlimit(limit, (value, value))
    command = sys.argv[5:]
    os.execve(command[0], command, {})


if __name__ == '__main__':
    main()
