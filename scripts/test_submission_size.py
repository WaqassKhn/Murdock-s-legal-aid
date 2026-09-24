"""Submission accounting checks use fabricated Git responses, never modify a repository."""

import subprocess
from pathlib import Path

import pytest

from submission_size import BUDGET, LIMIT, measure


def test_candidate_estimate_is_never_reported_as_verified(tmp_path, monkeypatch):
    monkeypatch.setattr(
        'submission_size.git', lambda *_: (_ for _ in ()).throw(RuntimeError('not a repository'))
    )
    (tmp_path / 'source.py').write_bytes(b'12345')
    (tmp_path / '.env').write_bytes(b'synthetic-secret')
    (tmp_path / 'node_modules').mkdir()
    (tmp_path / 'node_modules' / 'ignored').write_bytes(b'large')
    result = measure(tmp_path)
    assert result['candidate_estimate_bytes'] == 5
    assert result['tracked_file_bytes'] is None
    assert result['conservative_budget_exceeded'] is None
    assert result['status'].startswith('NOT VERIFIED')


def fake_git(tmp_path, monkeypatch, tracked_size, history_size):
    git_dir = tmp_path / '.git'
    (git_dir / 'objects').mkdir(parents=True)
    (git_dir / 'objects' / 'synthetic-object').write_bytes(b'1234')
    answers = {
        ('rev-parse', '--show-toplevel'): str(tmp_path).encode(),
        ('ls-files', '--stage', '-z'): b'100644 blob-id 0\tsource.py\0',
        ('rev-parse', '--absolute-git-dir'): str(git_dir).encode(),
        ('rev-parse', '--git-path', 'objects'): str(git_dir / 'objects').encode(),
        ('rev-list', '--objects', '--all'): b'blob-id source.py\n',
        ('diff', '--name-only'): b'',
    }
    monkeypatch.setattr('submission_size.git', lambda root, *args: answers[args])
    sizes = iter([tracked_size, history_size])
    monkeypatch.setattr(
        'submission_size.subprocess.run',
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, stdout=f'{next(sizes)}\n'.encode()),
    )


def test_staged_tree_and_history_are_both_accounted_for(tmp_path, monkeypatch):
    fake_git(tmp_path, monkeypatch, 50, 70)
    result = measure(tmp_path)
    assert result['tracked_file_bytes'] == 50
    assert result['git_object_bytes'] == 4
    assert result['git_history_uncompressed_bytes'] == 70
    assert result['conservative_combined_bytes'] == 54
    assert result['conservative_budget_exceeded'] is False
    assert result['fresh_clone'].startswith('NOT VERIFIED')


@pytest.mark.parametrize('size', [BUDGET, LIMIT])
def test_exact_budget_boundary_or_large_history_fails(tmp_path, monkeypatch, size):
    fake_git(tmp_path, monkeypatch, 50, size)
    result = measure(tmp_path)
    assert result['conservative_budget_exceeded'] is True
    assert result['strict_limit_exceeded'] is (size >= LIMIT)


def test_missing_directory_is_an_error(tmp_path):
    with pytest.raises(ValueError, match='does not exist'):
        measure(Path(tmp_path / 'missing'))
