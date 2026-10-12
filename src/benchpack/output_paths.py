"""Filesystem containment checks for generated output and protected inputs."""

from pathlib import Path


def paths_overlap(output: Path, source: Path) -> bool:
    """Check containment, including existing case, symlink, and hardlink aliases."""
    output = output.resolve()
    source = source.resolve()
    if source.is_relative_to(output) or output.is_relative_to(source):
        return True
    for path, ancestors in (
        (output, (source, *source.parents)),
        (source, (output, *output.parents)),
    ):
        for ancestor in ancestors:
            try:
                if path.samefile(ancestor):
                    return True
            except (FileNotFoundError, NotADirectoryError):
                continue
    return False
