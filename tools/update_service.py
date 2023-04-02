#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
import json
from pathlib import Path
import re
from subprocess import CalledProcessError, CompletedProcess, PIPE, run
import sys
import tempfile
from typing import Any, cast

from awesomeversion import AwesomeVersion
from yaml import safe_load

DEF_TAG = "latest"
COMPOSE_FILES = ["compose.yml", "docker-compose.yml"]


class ExitError(Exception):
    """Exit exception."""


def run_cmd(
    *cmd: tuple[str, ...],
    capture_stdout: bool = True,
    capture_stderr: bool = False,
) -> CompletedProcess:
    """Run a shell command.
    
    Raises CalledProcessError if command returns non-zero exit code.
    """
    kwargs = {}
    if capture_stdout and capture_stderr:
        kwargs["capture_output"] = True
    elif capture_stdout:
        kwargs["stdout"] = PIPE
    elif capture_stderr:
        kwargs["stderr"] = PIPE
    return run([*cmd], **kwargs, text=True, check=True)


def docker(
    *cmd: tuple[str, ...],
    capture_stdout: bool = True,
    capture_stderr: bool = False,
) -> CompletedProcess:
    """Run a docker command.
    
    Raises CalledProcessError if command returns non-zero exit code.
    """
    return run_cmd(
        *["docker", *cmd],
        capture_stdout=capture_stdout,
        capture_stderr=capture_stderr,
    )


def log(verbose: bool, title: str, *s: str) -> None:
    """Print out a log message."""
    if not verbose:
        return
    print(f"{title + ':':12}", *s)


def pull_image(repo_tag: str, verbose: bool) -> bool:
    """Pull docker image."""
    cmd = ["pull"]
    if verbose:
        print("Pulling", repo_tag, "...")
        print("-" * 80)
    else:
        cmd.append("--quiet")
    try:
        docker(*cmd, repo_tag, capture_stdout=not verbose)
    except CalledProcessError as exc:
        if verbose:
            print("-" * 10)
        print("docker pull:", cast(str, exc.stderr).strip(), file=sys.stderr)
        return False
    if verbose:
        print("-" * 80)
    return True


def image_version(repo_tag: str, verbose: bool) -> str | None:
    """Retrieve version of docker image."""
    try:
        result = docker("inspect", repo_tag, capture_stderr=True)
    except CalledProcessError as exc:
        print("docker inspect:", cast(str, exc.stderr).strip(), file=sys.stderr)
        return None

    result = json.loads(result.stdout)
    if not result:
        return None
    return result[0]["Config"]["Labels"]["org.opencontainers.image.version"]


def update(
    compose_path: Path,
    docker_repo: str,
    current_tag: str,
    target_tag: str,
    restart: bool,
    verbose: bool,
) -> str | None:
    """Update compose configuraiton file and optionally restart services."""
    if verbose:
        print("Changing to", target_tag, "...")

    compose_fullpath = compose_path.expanduser().resolve()
    compose_backup = compose_fullpath.with_suffix(".bak" + compose_fullpath.suffix)
    compose_log = compose_fullpath.with_suffix(compose_fullpath.suffix + ".log")

    with tempfile.NamedTemporaryFile(
        mode="x", dir=compose_fullpath.parent, delete=False
    ) as tmp:
        with compose_fullpath.open() as old:
            image_pat = re.compile(
                rf'(\s+image:\s+"*{docker_repo}:){current_tag}("*\s*)'
            )
            sub_string = rf"\g<1>{target_tag}\g<2>"
            for line in old.readlines():
                new_line = image_pat.sub(sub_string, line)
                tmp.write(new_line)
    compose_fullpath.replace(compose_backup)
    Path(tmp.name).replace(compose_fullpath)
    with compose_log.open("a") as f:
        print("=" * 50, file=f)
        print(datetime.now().replace(microsecond=0), file=f)
        print(f"{current_tag} -> {target_tag}", file=f)

    if restart:
        docker("compose", "-f", compose_fullpath, "pull", capture_stdout=not verbose)
        docker("compose", "-f", compose_fullpath, "up", "-d", capture_stdout=not verbose)
        with compose_log.open("a") as f:
            print("Restarted", file=f)


def find_compose_path(args: ArgsNamespace, verbose: bool) -> Path | None:
    """Find docker compose file."""
    if args.file:
        compose_paths = [Path(args.file)]
    else:
        compose_paths = [Path(args.dir, file) for file in COMPOSE_FILES]
    for compose_path in compose_paths:
        if compose_path.expanduser().resolve().is_file():
            log(verbose, "Config file", compose_path)
            return compose_path
    return None


def image_params(
    compose_path: Path, service: str | None, service_idx: int, verbose: bool
) -> tuple[str, str, str]:
    """Extract image repository & tag from compose config file.
    
    Returns (service, docker_repo, current_tag)
    """
    try:
        with compose_path.expanduser().resolve().open() as f:
            compose_config = safe_load(f)
    except FileNotFoundError:
        raise ExitError(f"Could not open {compose_path}")
    try:
        services: dict[str, dict[str, Any]] = compose_config["services"]
    except KeyError:
        raise ExitError(f"Could not find services in {compose_path}")
    if service:
        try:
            service_cfg = services[service]
        except KeyError:
            raise ExitError(f"Could not find service {service} in {compose_path}")
    else:
        try:
            service, service_cfg = list(services.items())[service_idx - 1]
        except IndexError:
            raise ExitError(f"Service index {service_idx} too big for {compose_path}")
        log(verbose, "Service", service)
    try:
        image:str = service_cfg["image"]
    except KeyError:
        raise ExitError(f"Could not find image for service {service} in {compose_path}")
    image_parts = image.strip().split(":")
    try:
        docker_repo = image_parts[0]
        current_tag = image_parts[1]
    except IndexError:
        raise ExitError(f"Malformed image in {compose_path}: {image}")
    return service, docker_repo, current_tag


class VersionCmp(IntEnum):
    """Version Comparison Result."""

    SAME = 2
    NEWER = 4
    OLDER = 6


@dataclass(init=False)
class ArgsNamespace:
    """Namespace for arguments."""

    command: str
    file: str | None
    dir: str
    service_idx: int
    service: str | None
    quiet: bool
    yes: bool
    tag_version: str
    tag: str | None
    keep: bool


def main(args: ArgsNamespace) -> str | int | None:
    """Update docker service"""
    command = args.command
    verbose = not args.quiet
    no_prompt = args.yes

    if not (compose_path := find_compose_path(args, verbose)):
        return "Could not find compose configuration file"

    try:
        service, docker_repo, current_tag = image_params(
            compose_path, args.service, args.service_idx, verbose
        )
    except ExitError as exc:
        return str(exc)

    current_repo_tag = f"{docker_repo}:{current_tag}"
    current_version = image_version(current_repo_tag, verbose)
    if not current_version:
        if pull_image(current_repo_tag, verbose):
            current_version = image_version(current_repo_tag, verbose)
        if not current_version:
            return f"Could not get version of {current_repo_tag}"
    log(verbose, "Current", current_repo_tag, "->", current_version)

    target_tag: str | None
    if args.tag:
        target_tag = tag_version = args.tag
    elif args.keep:
        target_tag = tag_version = current_tag
    else:
        target_tag = None
        tag_version = args.tag_version
    target_repo_tag = f"{docker_repo}:{tag_version}"

    if not pull_image(target_repo_tag, verbose):
        return f"Could not pull {target_repo_tag}"
    target_version = image_version(target_repo_tag, verbose)
    if not target_version:
        return f"Could not get version of {target_repo_tag}"
    log(verbose, "Tag", tag_version, "->", target_version)
    target_tag = target_tag or target_version

    current_av = AwesomeVersion(current_version)
    target_av = AwesomeVersion(target_version)

    if target_av == current_av:
        version_cmp = VersionCmp.SAME
    elif target_av > current_av:
        version_cmp = VersionCmp.NEWER
    else:
        version_cmp = VersionCmp.OLDER
    version_msg = {
        VersionCmp.SAME: "the same as",
        VersionCmp.NEWER: "newer than",
        VersionCmp.OLDER: "older than",
    }[version_cmp]

    if same_tags := target_tag == current_tag:
        tags_msg = f"the same ({current_tag})"
    else:
        tags_msg = f"different ({current_tag} -> {target_tag})"

    if verbose:
        print(f"Target version is {version_msg} current version")
        print(f"Tags are {tags_msg}")

    if version_cmp is VersionCmp.SAME and same_tags:
        return

    if command == "check":
        return version_cmp.value + int(not same_tags)

    if not no_prompt:
        try:
            answer = input(f"Change {compose_path} to {target_version}? [y/N] ")
        except EOFError:
            print()
            return

        if answer.strip().lower() not in ("y", "yes"):
            return

    return update(
        compose_path, docker_repo, current_tag, target_tag, command == "restart", verbose
    )


help_epilog = """
command:
  check    Check if update available (default)
  config   Update compose file
  restart  Update compose file and restart container

check exit code:
  0  target version same as current, no tag change
  3  target version same as current, tag would change
  4  target version newer than current, no tag change
  5  target version newer than current, tag would change
  6  target version older than current, no tag change
  7  target version older than current, tag would change
"""

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Update Docker Service",
        epilog=help_epilog,
    )

    parser.add_argument(
        "command",
        nargs="?",
        choices=["check", "config", "restart"],
        metavar="command",
        default="check",
        help="check | config | restart"
    )

    file_group = parser.add_mutually_exclusive_group()
    file_group.add_argument("-f", "--file", help="Compose configuration file")
    file_group.add_argument(
        "-d", "--dir", default=".", help="Compose configuration file directory"
    )

    service_group = parser.add_mutually_exclusive_group()
    service_group.add_argument(
        "-S",
        "--service-idx",
        type=int,
        default=1,
        metavar="INDEX",
        help="service index (default: 1)",
    )
    service_group.add_argument("-s", "--service")

    parser.add_argument(
        "-q", "--quiet", action="store_true", help="suppress verbose output"
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="do not prompt for confirmation; not valid with check",
    )

    tag_group = parser.add_mutually_exclusive_group()
    tag_group.add_argument(
        "-t",
        "--tag-version",
        default=DEF_TAG,
        metavar="TAG",
        help=f"use version of TAG (default: {DEF_TAG})",
    )
    tag_group.add_argument(
        "-T", "--tag", metavar="TAG", help="use TAG"
    )
    tag_group.add_argument(
        "-k", "--keep", action="store_true", help="keep tag from compose file"
    )

    args = parser.parse_args(namespace=ArgsNamespace())

    if args.command == "check" and args.yes:
        print("-y/--yes not valid with check", file=sys.stderr)
        parser.print_usage(file=sys.stderr)
        sys.exit(2)
    if args.service_idx < 1:
        print("service INDEX must be >= 1", file=sys.stderr)
        parser.print_usage(file=sys.stderr)
        sys.exit(2)

    sys.exit(main(args))
