"""Command-line entry points; credentials and note text are never logged."""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path

from . import __version__
from .api import MubuClient
from .errors import ExportError
from .exporter import export_cache
from .images import plan_images
from .paths import plan_paths
from .schema import validate_payload
from .storage import load_cache
from .sync import sync_cache


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description="Back up Mubu notes and convert a local cache to Markdown.")
    command.add_argument("--version", action="version", version=__version__)
    sub = command.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("fetch", help="Create a new, complete backup using your login token")
    fetch.add_argument("--cache", type=Path, required=True)
    fetch.add_argument("--prompt-token", action="store_true", help="Read the token without echoing it")
    fetch.add_argument("--no-daily", action="store_true", help="Explicitly exclude daily notes")
    convert = sub.add_parser("export", help="Convert a local backup to a new Markdown directory")
    convert.add_argument("--cache", type=Path, required=True)
    convert.add_argument("--out", type=Path, required=True)
    convert.add_argument("--images", choices=("remote", "local", "skip"), default="remote")
    convert.add_argument("--style", choices=("adaptive", "bullets"), default="adaptive")
    convert.add_argument("--no-color", action="store_true")
    convert.add_argument("--source-metadata", action="store_true", help="Include source document IDs and URLs")
    convert.add_argument("--trusted-input", action="store_true", help="Allow unsafe link schemes and color values")
    convert.add_argument("--allow-private-images", action="store_true", help="Allow HTTP/private-network image sources")
    inspect = sub.add_parser("inspect", help="Validate cache schema and paths; print aggregate counts")
    inspect.add_argument("--cache", type=Path, required=True)
    return command


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "fetch":
            token = getpass.getpass("Mubu token: ") if args.prompt_token else os.environ.get("MUBU_TOKEN", "")
            with MubuClient(token, os.environ.get("MUBU_UNIQUE_ID", "")) as api:
                summary = sync_cache(api, args.cache, include_daily=not args.no_daily)
        elif args.command == "export":
            summary = export_cache(
                args.cache, args.out, image_mode=args.images, style=args.style,
                keep_color=not args.no_color, source_metadata=args.source_metadata,
                preserve_unsafe=args.trusted_input, allow_private_images=args.allow_private_images,
            )
        else:
            tree, docs = load_cache(args.cache)
            folders, _ = plan_paths(tree, docs)
            nodes = {doc_id: validate_payload(payload) for doc_id, payload in docs.items()}
            summary = {"documents": len(docs), "folders": len(folders),
                       "unique_images": len(plan_images(nodes))}
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 0
    except ExportError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"error: local file operation failed (errno={error.errno})", file=sys.stderr)
        return 2
    except (EOFError, KeyboardInterrupt):
        print("error: operation cancelled", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
