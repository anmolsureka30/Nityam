from google.cloud import storage


class ObjectStore:
    def __init__(self, bucket_name: str, client=None):
        self._bucket_name = bucket_name
        self._client = client or storage.Client()

    def upload(self, local_path: str, dest_path: str) -> str:
        bucket = self._client.bucket(self._bucket_name)
        bucket.blob(dest_path).upload_from_filename(local_path)
        return f"gs://{self._bucket_name}/{dest_path}"

    def download(self, uri: str, local_path: str) -> None:
        prefix = f"gs://{self._bucket_name}/"
        assert uri.startswith(prefix), f"{uri} is not in bucket {self._bucket_name}"
        dest_path = uri[len(prefix):]
        bucket = self._client.bucket(self._bucket_name)
        bucket.blob(dest_path).download_to_filename(local_path)
