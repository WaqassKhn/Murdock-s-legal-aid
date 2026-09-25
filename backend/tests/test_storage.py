from types import SimpleNamespace

import httpx
import pytest

from app.storage import StorageError, SupabaseStorage, storage


KEY = '01a0c345-67da-76a1-a048-5ccb5cf46611.pdf'


def test_local_roundtrip(tmp_path):
    adapter = storage(SimpleNamespace(storage_dir=tmp_path, supabase_url='', supabase_secret_key=''))
    adapter.write(KEY, b'private document')
    assert adapter.read(KEY) == b'private document'
    adapter.delete(KEY)
    adapter.delete(KEY)
    assert not (tmp_path / KEY).exists()


@pytest.mark.parametrize('key', ['../secret.pdf', '/secret', KEY + '/x', '%2e%2e.pdf', 'file.txt'])
def test_invalid_keys(tmp_path, key):
    adapter = storage(SimpleNamespace(storage_dir=tmp_path, supabase_url='', supabase_secret_key=''))
    for operation in [
        lambda: adapter.write(key, b'x'),
        lambda: adapter.read(key),
        lambda: adapter.delete(key),
    ]:
        with pytest.raises(ValueError, match='storage key'):
            operation()


def test_remote_roundtrip_and_secret_headers():
    objects = {}

    def handle(request):
        assert request.headers['apikey'] == 'sb_secret_test'
        assert 'authorization' not in request.headers
        if request.method == 'POST':
            assert request.headers['x-upsert'] == 'true'
            assert request.url.path == '/storage/v1/object/legallens-documents/' + KEY
            objects[KEY] = request.content
            return httpx.Response(200, json={})
        if request.method == 'GET':
            assert request.url.path == '/storage/v1/object/authenticated/legallens-documents/' + KEY
            return httpx.Response(200, content=objects[KEY])
        assert request.method == 'DELETE'
        assert request.url.path == '/storage/v1/object/legallens-documents'
        assert request.read() == b'{"prefixes":["' + KEY.encode() + b'"]}'
        objects.pop(KEY, None)
        return httpx.Response(200, json=[])

    adapter = SupabaseStorage(
        'https://example.supabase.co', 'sb_secret_test', transport=httpx.MockTransport(handle)
    )
    adapter.write(KEY, b'private document')
    assert adapter.read(KEY) == b'private document'
    adapter.delete(KEY)
    adapter.delete(KEY)
    assert not objects


def test_remote_errors_are_safe_and_redirects_not_followed():
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(307, headers={'Location': 'https://attacker.example'}, text='private body')

    adapter = SupabaseStorage(
        'https://example.supabase.co', 'sb_secret_test', transport=httpx.MockTransport(handle)
    )
    with pytest.raises(StorageError, match='storage read failed') as error:
        adapter.read(KEY)
    assert 'private' not in str(error.value)
    assert len(requests) == 1


def test_delete_missing_and_legacy_key():
    def handle(request):
        assert request.headers['authorization'] == 'Bearer eyJ.legacy.signature'
        return httpx.Response(404)

    SupabaseStorage(
        'https://example.supabase.co', 'eyJ.legacy.signature', transport=httpx.MockTransport(handle)
    ).delete(KEY)


@pytest.mark.parametrize(
    'url',
    [
        'http://example.supabase.co',
        'https://user:pass@example.com',
        'https://example.com?key=x',
        'https://example.com/path',
    ],
)
def test_unsafe_base_url(url):
    with pytest.raises(ValueError, match='Supabase URL'):
        SupabaseStorage(url, 'sb_secret_test')


def test_transport_failure_is_bounded():
    calls = []

    def handle(request):
        calls.append(request)
        raise httpx.ReadTimeout('private detail', request=request)

    adapter = SupabaseStorage(
        'https://example.supabase.co', 'sb_secret_test', transport=httpx.MockTransport(handle)
    )
    with pytest.raises(StorageError) as error:
        adapter.write(KEY, b'x')
    assert 'private detail' not in str(error.value)
    assert len(calls) == 2


def test_remote_size_bounds():
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, content=b'123456')

    adapter = SupabaseStorage(
        'https://example.supabase.co', 'sb_secret_test', max_bytes=5, transport=httpx.MockTransport(handle)
    )
    with pytest.raises(StorageError, match='size'):
        adapter.write(KEY, b'123456')
    assert not calls
    with pytest.raises(StorageError, match='size'):
        adapter.read(KEY)
    assert len(calls) == 1


def test_partial_configuration_does_not_fall_back_to_temporary_disk(tmp_path):
    with pytest.raises(ValueError, match='Configure both'):
        storage(
            SimpleNamespace(
                storage_dir=tmp_path, supabase_url='https://example.supabase.co', supabase_secret_key=''
            )
        )


def test_publishable_key_is_rejected():
    with pytest.raises(ValueError, match='server secret'):
        SupabaseStorage('https://example.supabase.co', 'sb_publishable_test')
