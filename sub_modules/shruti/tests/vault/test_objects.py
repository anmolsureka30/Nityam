from shruti.vault.objects import ObjectStore


class FakeBlob:
    def __init__(self, store, path):
        self._store, self._path = store, path

    def upload_from_filename(self, local_path):
        with open(local_path, "rb") as f:
            self._store[self._path] = f.read()

    def download_to_filename(self, local_path):
        with open(local_path, "wb") as f:
            f.write(self._store[self._path])


class FakeBucket:
    def __init__(self, store):
        self._store = store

    def blob(self, path):
        return FakeBlob(self._store, path)


class FakeGcsClient:
    def __init__(self):
        self._store = {}

    def bucket(self, name):
        return FakeBucket(self._store)


def test_object_store_roundtrip(tmp_path):
    store = ObjectStore(bucket_name="test-bucket", client=FakeGcsClient())
    src = tmp_path / "in.png"
    src.write_bytes(b"pixel-data")

    uri = store.upload(str(src), "board/bs1.png")
    assert uri == "gs://test-bucket/board/bs1.png"

    dest = tmp_path / "out.png"
    store.download(uri, str(dest))
    assert dest.read_bytes() == b"pixel-data"
