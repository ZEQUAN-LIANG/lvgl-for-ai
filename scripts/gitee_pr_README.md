# Gitee PR helper

`scripts/gitee_pr.py` creates, updates and verifies Gitee pull requests without
passing Chinese text through the Windows shell.  Inline command-line Chinese
can be re-encoded as GBK/ANSI and stored as `����`; this helper reads UTF-8
files, sends an explicit `charset=utf-8` form, and reads the PR back to verify
the stored title/body.

## Requirements

- `GITEE_TOKEN` in the environment (never on the command line)
- `origin` pointing at `https://gitee.com/OWNER/REPO.git` or `git@gitee.com:OWNER/REPO.git`
- UTF-8 title/body files (no need to strip BOM)

## Commands

```bash
# Create a PR from a feature branch to dev
python -I scripts/gitee_pr.py create \
  --head feat/esp32-ble-dual --base dev \
  --title-file .test-tmp/pr_title.txt \
  --body-file .test-tmp/pr_body.md --json

# Update title/body
python -I scripts/gitee_pr.py update 24 \
  --body-file .test-tmp/pr_body.md --json

# Inspect a PR and its encoding
python -I scripts/gitee_pr.py show 24 --json

# Verify stored title/body against local UTF-8 files
python -I scripts/gitee_pr.py verify 24 \
  --title-file .test-tmp/pr_title.txt \
  --body-file .test-tmp/pr_body.md --json
```

Useful options:

- `--repo OWNER/REPO` overrides the repo inferred from `git remote get-url origin`
- `--head` defaults to the current branch; `--base` defaults to `dev`
- `--dry-run` prints the request without calling Gitee
- `--no-verify` skips the read-back check
- `--api-base` is for tests/local fakes

## Verification rules

- `title` must match after stripping surrounding whitespace.
- `body` is compared exactly first. If Gitee removed an emoji or collapsed it
  to a space, a normalized comparison (drop astral-plane characters, collapse
  spaces) is accepted and reported as `exact=false`.
- Any `�` (U+FFFD) in the stored body is an error.
- Exit codes: `0` verified, `1` request/config error, `2` stored content
  differs from the local files.

## Why not `curl` with `--data-urlencode "body=..."`?

On Windows the shell can encode the argument before curl sees it.  Even a
correct-looking command can store mojibake.  Files plus explicit UTF-8 bytes
avoid that layer entirely; the read-back check catches regressions.
