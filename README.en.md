# Mubu Exporter

[简体中文](README.md) · **English** · [Español](README.es.md) · [日本語](README.ja.md)

Convert Mubu outlines into portable Markdown. Keep folders, rich text, task states, tables, equations and links between documents, with the option to download images locally.

Python 3.10+ · Windows / Linux · [MIT](LICENSE)

## Try the example

Convert the included, handcrafted synthetic example without a Mubu account, token or network access for the conversion. Run these commands from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install .
mubu-export inspect --cache examples/cache
mubu-export export --cache examples/cache --out exports/demo --images skip
```

On Linux or macOS, activate the environment with `source .venv/bin/activate`. Open `exports/demo/index.md` to browse the output. The output directory must be new; use a different name for each run.

See the [example cache](examples/cache) and the [export preview](examples/preview/index.md) for the input and the actual conversion result. Both contain only fictional material.

## What the exporter preserves

| Content | Markdown representation |
| --- | --- |
| Folders and documents with the same name | Stable, unique paths based on IDs, avoiding Windows reserved names and case collisions |
| Outlines | Adaptive headings or fully nested lists |
| Bold, italics, strikethrough and inline code | Markdown syntax; backticks and spaces in code are preserved |
| Highlights and cloze deletions | `==highlight==` and `{{cloze}}`; display depends on the reader |
| Underlines and colors | A small amount of HTML; use `--no-color` to omit colors |
| Equations | `$LaTeX$`, which requires math support in the reader |
| Tasks and notes | `- [ ]` / `- [x]` and block quotes |
| Simple tables | GFM tables with escaped text and line breaks preserved in cells |
| Document references | Relative links and node anchors for exported documents; Mubu links for documents outside the export |
| Images | Keep remote URLs, download images locally, or explicitly skip images |

Merged cells, nested tables and known incomplete data produce explicit errors to prevent incomplete exports from appearing successful. The outline layout does not recreate Mubu's interactive interface.

## Back up your own Mubu documents

`fetch` uses Mubu's web interface API. This is an unofficial tool and the API may change. Use it only for content you are authorized to access.

1. Sign in to Mubu in your browser and open the Network panel in developer tools.
2. Select a document request to `api2.mubu.com` and find the `Jwt-Token` request header.
3. Run the command with a hidden prompt and paste the value. The token is used only in that process and is not saved to a file.

```powershell
mubu-export fetch --cache cache/backup-001 --prompt-token
mubu-export inspect --cache cache/backup-001
mubu-export export --cache cache/backup-001 --out exports/backup-001 --images local
```

If the API requires `data-unique-id`, set `MUBU_UNIQUE_ID`. For automation, the token can be read from `MUBU_TOKEN`. Keep it out of scripts, command-line arguments, screenshots and Git.

The backup paginates through documents, merges daily notes and fetches all documents again. Existing cache files do not cause updates to be skipped. A daily-notes API failure stops the backup; use `--no-daily` if you explicitly want to exclude daily notes.

Downloads and exports are staged in a temporary directory on the same drive. The new directory is put in place only after all checks pass. Existing directories are not overwritten. Conversion reads only the documents listed in `tree.json`, so stale files cannot slip into the export.

## Common options

```powershell
# Convert a local cache without network requests
mubu-export export --cache cache/backup-001 --out exports/text --images skip --no-color

# Use fully nested lists
mubu-export export --cache cache/backup-001 --out exports/bullets --style bullets

# Include source document IDs and Mubu URLs in front matter
mubu-export export --cache cache/backup-001 --out exports/with-source --source-metadata
```

By default, the summary displays counts only, without account details, document names or document IDs. Source IDs and URLs are excluded from front matter unless requested. The text, filenames, node anchors, original links and images may still contain private material. Do not commit private exports to a public repository.

Image requests do not carry the Mubu token. By default, downloads require public HTTPS addresses and reject redirects, private network addresses, non-image responses, empty responses and files over 32 MiB. For a trusted local image source, `--allow-private-images` explicitly permits HTTP and private network addresses. Image downloads contact the servers named in the source URLs, which can be external sites.

Link schemes and color values are validated by default; unsafe values cause an error. `--trusted-input` relaxes both checks for trusted input and should not be used on unknown caches. `--no-color` omits color rendering while preserving the text.

## Local cache format

```text
cache/backup-001/
  tree.json          # folders and documents lists, keyed by document ID
  docs/<id>.json     # {"meta": {...}, "data": {"definition": ..., "directory": [...]}}
  manifest.json      # schema version and document count for new backups
```

`definition` may be a JSON object or a JSON-encoded string and must contain a `nodes` list. Use `{"nodes": []}` for a valid empty note. IDs may contain only letters, digits, underscores and hyphens. The maximum depth is 64 levels of nodes and 32 levels of folders. Existing caches that follow this format are supported; keep private caches outside the source repository.

An export contains `index.md`, the individual notes and `manifest.json`. The manifest records the number of documents, image mode, actual file paths and SHA-256 hashes for verification and migration.

## Development and verification

```powershell
python -m pip install ".[dev]"
python -m pytest
python -m ruff check .
python -m build
```

Tests use synthetic data and include real requests to a local HTTP server; no Mubu account is needed. CI tests, lints, builds and runs the installed example on Windows and Linux with Python 3.10 and 3.12. Public CI does not exercise the live Mubu API; offline tests cannot establish current API compatibility.

## Privacy and limitations

The repository contains no login data, account information, real notes, private diagnostics or personal screenshots. Examples and tests are handcrafted and synthetic. Protect access to tokens and backups; see the [privacy notes](PRIVACY.md).

This tool does not guarantee API stability, bypass permissions or send notes to AI or analytics services. Markdown readers vary in support for equations, highlighting, cloze deletions and HTML. Attachments, embedded pages and other objects not listed above may not convert. Compare important exports with their sources before publishing them.
