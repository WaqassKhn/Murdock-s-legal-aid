"""Measure submission size without publishing, modifying Git, or reading document contents."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

BUDGET = 8_000_000
LIMIT = 10_000_000
EXCLUDED_DIRS = {
    '.git',
    '.venv',
    '.uv-cache',
    '.pytest_cache',
    '.ruff_cache',
    '__pycache__',
    'node_modules',
    'dist',
    'data',
    'test-results',
    'playwright-report',
    'coverage',
    '.submission-check',
    '.clean-check',
    'screenshots',
}
EXCLUDED_SUFFIXES = {'.db', '.db-shm', '.db-wal', '.log', '.pyc', '.tsbuildinfo'}


def git(root: Path, *arguments: str) -> bytes:
    result = subprocess.run(
        ['git', '-C', str(root), *arguments],
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f'Git command failed: {arguments[0]} (exit {result.returncode})')
    return result.stdout


def directory_bytes(path: Path) -> int:
    if not path.is_dir():
        return 0
    return sum(item.stat().st_size for item in path.rglob('*') if item.is_file() and not item.is_symlink())


def candidate_files(root: Path) -> list[Path]:
    candidates = []
    for directory, children, files in os.walk(root):
        children[:] = [
            name
            for name in children
            if name not in EXCLUDED_DIRS and not (Path(directory) / name).is_symlink()
        ]
        for name in files:
            path = Path(directory) / name
            if path.is_symlink() or (name.startswith('.env') and name != '.env.example'):
                continue
            if path.suffix in EXCLUDED_SUFFIXES or name.endswith(('.db-shm', '.db-wal')):
                continue
            candidates.append(path)
    return candidates


def measure(root: Path) -> dict:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError('The selected repository directory does not exist.')
    try:
        git_root = Path(git(root, 'rev-parse', '--show-toplevel').decode().strip()).resolve()
        is_repository = git_root == root
    except (RuntimeError, FileNotFoundError):
        is_repository = False
    result = {
        'units': 'bytes (decimal MB = 1,000,000 bytes)',
        'budget_bytes': BUDGET,
        'strict_limit_bytes': LIMIT,
        'public_repository_url': 'NOT VERIFIED',
        'unauthenticated_access': 'NOT VERIFIED; this script performs no network requests',
        'fresh_clone': 'NOT VERIFIED; run these measurements in a fresh public clone before submission',
        'secret_and_private_content_review': 'NOT VERIFIED; size inspection is not a content audit',
    }
    if not is_repository:
        paths = candidate_files(root)
        sizes = [(path.relative_to(root).as_posix(), path.stat().st_size) for path in paths]
        total = sum(size for _, size in sizes)
        return {
            **result,
            'status': 'NOT VERIFIED: no Git repository at the selected root',
            'candidate_estimate_bytes': total,
            'candidate_file_count': len(sizes),
            'candidate_method': 'Filesystem estimate excluding common runtime directories, screenshots, .env secrets and caches; not a tracked-file or history measurement',
            'candidate_excluded_directories': sorted(EXCLUDED_DIRS),
            'tracked_file_bytes': None,
            'git_object_bytes': None,
            'git_history_uncompressed_bytes': None,
            'conservative_budget_exceeded': None,
            'largest_candidate_files': [
                {'path': name, 'bytes': size}
                for name, size in sorted(sizes, key=lambda pair: pair[1], reverse=True)[:15]
            ],
        }

    # The index is the proposed submission tree, including newly staged files.
    entries = [entry for entry in git(root, 'ls-files', '--stage', '-z').split(b'\0') if entry]
    files, object_ids = [], []
    for entry in entries:
        header, name = entry.split(b'\t', 1)
        mode, object_id, stage = header.split()
        if stage != b'0':
            raise ValueError('Resolve merge conflicts before measuring the submission.')
        if mode == b'160000':
            raise ValueError('Git submodules are not permitted by the submission rules.')
        files.append(name.decode('utf-8', errors='surrogateescape'))
        object_ids.append(object_id)
    objects = subprocess.run(
        ['git', '-C', str(root), 'cat-file', '--batch-check=%(objectsize)'],
        input=b'\n'.join(object_ids) + b'\n' if object_ids else b'',
        capture_output=True,
        check=True,
    ).stdout.splitlines()
    sizes = list(zip(files, (int(size) for size in objects), strict=True))
    tracked_size = sum(size for _, size in sizes)
    git_dir = Path(git(root, 'rev-parse', '--absolute-git-dir').decode().strip())
    object_dir = Path(git(root, 'rev-parse', '--git-path', 'objects').decode().strip())
    if not object_dir.is_absolute():
        object_dir = root / object_dir
    reachable = git(root, 'rev-list', '--objects', '--all').splitlines()
    reachable_ids = [row.split(b' ', 1)[0] for row in reachable]
    history_sizes = subprocess.run(
        ['git', '-C', str(root), 'cat-file', '--batch-check=%(objectsize)'],
        input=b'\n'.join(reachable_ids) + b'\n' if reachable_ids else b'',
        capture_output=True,
        check=True,
    ).stdout.splitlines()
    history_size = sum(int(size) for size in history_sizes)
    git_bytes = directory_bytes(git_dir)
    physical_objects = directory_bytes(object_dir)
    conservative = tracked_size + git_bytes
    # Also check logical history because the organizer's measurement is unspecified.
    exceeded = max(conservative, history_size) >= BUDGET
    strict_exceeded = max(conservative, history_size) >= LIMIT
    return {
        **result,
        'status': 'BUDGET EXCEEDED'
        if exceeded
        else 'LOCAL SIZE CHECK PASSED; public submission remains NOT VERIFIED',
        'tracked_file_count': len(sizes),
        'tracked_file_bytes': tracked_size,
        'tracked_file_method': 'Sum of staged Git blob sizes, counting each tracked path; unstaged changes are excluded',
        'unstaged_changes_present': bool(git(root, 'diff', '--name-only')),
        'git_object_bytes': physical_objects,
        'git_directory_bytes': git_bytes,
        'git_history_uncompressed_bytes': history_size,
        'git_history_object_count': len(reachable_ids),
        'history_method': 'Sum of unique reachable object sizes across all refs; physical objects also include local unreachable objects',
        'conservative_combined_bytes': conservative,
        'conservative_method': 'Tracked tree plus the complete local Git directory; independently check uncompressed reachable history',
        'conservative_budget_exceeded': exceeded,
        'strict_limit_exceeded': strict_exceeded,
        'largest_tracked_files': [
            {'path': name, 'bytes': size}
            for name, size in sorted(sizes, key=lambda pair: pair[1], reverse=True)[:15]
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, help='Optional JSON report path')
    args = parser.parse_args()
    report = measure(args.root)
    rendered = json.dumps(report, indent=2, ensure_ascii=True) + '\n'
    print(rendered, end='')
    if args.output:
        args.output.write_text(rendered, encoding='utf-8')
    return 1 if report.get('conservative_budget_exceeded') is not False else 0


if __name__ == '__main__':
    raise SystemExit(main())
