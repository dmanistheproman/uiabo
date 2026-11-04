from io import BytesIO
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image

from app.analyses import images
from app.main import app
from app.routers import analysis, deepfakeAI_analysis, image_context_analysis


class MemoryImages:
    def __init__(self):
        self.objects = {}
        self.uploads = 0

    def upload(self, uid, reservation, data, content_type):
        self.uploads += 1
        path = images.image_prefix(uid, reservation['result_id']) + reservation['token']
        self.objects[path] = data
        return images.SavedImage(object_path=path, generation=1,
                                 content_type=content_type, size_bytes=len(data))

    def read(self, uid, result_id, attachment):
        assert attachment['object_path'].startswith(images.image_prefix(uid, result_id))
        return self.objects[attachment['object_path']]

    def delete(self, uid, result_id, attachment):
        if isinstance(attachment, images.SavedImage):
            attachment = attachment.model_dump()
        self.objects.pop(attachment['object_path'], None)


@pytest.fixture
def saved_images(signed_analysis, monkeypatch):
    store, identity = signed_analysis
    store.documents["users", identity["user"].uid]["role"] = "premium"
    memory = MemoryImages()
    monkeypatch.setenv('SAVE_ANALYSIS_IMAGES', '1')
    monkeypatch.setattr(images, 'get_image_storage', lambda: memory)
    monkeypatch.setattr(analysis, 'get_image_storage', lambda: memory)
    for router in [deepfakeAI_analysis, image_context_analysis]:
        monkeypatch.setattr(router, 'get_analysis_store', lambda: store)
    monkeypatch.setattr(deepfakeAI_analysis, 'analyse_deepfakeAI', lambda image: {
        'label': 'Fake', 'confidence': .9, 'real_probability': .1,
        'fake_probability': .9, 'explanation': None})
    monkeypatch.setattr(image_context_analysis, 'extract_caption', lambda image: {
        'extracted_caption': 'A sample claim', 'main_claim': 'A sample claim'})
    monkeypatch.setattr(image_context_analysis, 'analyse_image_context', lambda **kwargs: {
        'concern_label': 'High Concern', 'explanation': 'Mock evidence contradicts the claim.',
        'evidence_links': []})
    stream = BytesIO()
    Image.new('RGB', (10, 10), 'blue').save(stream, format='PNG')
    return store, identity, memory, stream.getvalue()


def submit(data, endpoint='/analysis/deepfakeAI'):
    return TestClient(app).post(endpoint, headers={'Idempotency-Key': 'saved-image-test'},
        files={'image': ('sample.png', data, 'image/png')})


@pytest.mark.parametrize('endpoint', ['/analysis/deepfakeAI', '/analysis/image-context'])
def test_save_reopen_retry_and_remove(saved_images, endpoint):
    store, identity, memory, data = saved_images
    response = submit(data, endpoint)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['saved_image']['size_bytes'] == len(data)
    assert memory.uploads == 1
    retry = submit(data, endpoint)
    assert retry.json() == result
    assert memory.uploads == 1
    assert store.documents['usage_allowances', identity['user'].uid]['successful_submissions'] == 1
    path = f"/analysis/results/{result['result_id']}"
    client = TestClient(app)
    assert client.get(path).json()['saved_image'] == result['saved_image']
    image = client.get(path + '/image')
    assert image.content == data
    assert image.headers['cache-control'] == 'private, no-store'
    assert client.delete(path + '/image').status_code == 204
    assert client.delete(path + '/image').status_code == 204
    assert client.get(path + '/image').status_code == 404
    assert client.get(path).json()['processing_status'] == 'completed'
    assert not memory.objects


def test_other_user_cannot_read_or_delete(saved_images):
    store, identity, memory, data = saved_images
    result = submit(data).json()
    identity['user'] = identity['user'].model_copy(update={'uid': 'other-user'})
    store.documents['users', 'other-user'] = {'role': 'free', 'account_status': 'active'}
    path = f"/analysis/results/{result['result_id']}/image"
    assert TestClient(app).get(path).status_code == 404
    assert TestClient(app).delete(path).status_code == 404
    assert memory.objects


def test_suspended_owner_cannot_read(saved_images):
    store, identity, memory, data = saved_images
    result = submit(data).json()
    store.documents['users', identity['user'].uid]['account_status'] = 'suspended'
    assert TestClient(app).get(f"/analysis/results/{result['result_id']}/image").status_code == 403


@pytest.mark.parametrize('endpoint', ['/analysis/deepfakeAI', '/analysis/image-context'])
def test_upload_failure_is_retryable_and_does_not_charge(saved_images, monkeypatch, endpoint):
    store, identity, memory, data = saved_images
    upload = memory.upload
    monkeypatch.setattr(memory, 'upload', Mock(side_effect=RuntimeError('storage down')))
    response = submit(data, endpoint)
    assert response.status_code == 503
    assert store.documents['usage_allowances', identity['user'].uid]['successful_submissions'] == 0
    assert ('analysis_locks', identity['user'].uid) not in store.documents
    monkeypatch.setattr(memory, 'upload', upload)
    assert submit(data, endpoint).status_code == 200


def test_result_save_failure_removes_unreferenced_image(saved_images, monkeypatch):
    store, identity, memory, data = saved_images
    monkeypatch.setattr(store, 'finish', Mock(side_effect=RuntimeError('database down')))
    assert submit(data).status_code == 503
    assert not memory.objects
    assert store.documents['usage_allowances', identity['user'].uid]['successful_submissions'] == 0


def test_ambiguous_commit_preserves_saved_image_and_returns_result(saved_images, monkeypatch):
    store, identity, memory, data = saved_images
    finish = store.finish
    def committed_then_timeout(*args, **kwargs):
        finish(*args, **kwargs)
        raise TimeoutError()
    monkeypatch.setattr(store, 'finish', committed_then_timeout)
    assert submit(data).status_code == 200
    assert memory.objects
    assert store.documents['usage_allowances', identity['user'].uid]['successful_submissions'] == 1


def test_unknown_commit_outcome_does_not_delete_image(saved_images, monkeypatch):
    store, identity, memory, data = saved_images
    monkeypatch.setattr(store, 'finish', Mock(side_effect=TimeoutError()))
    monkeypatch.setattr(store, 'get_owned', Mock(side_effect=TimeoutError()))
    assert submit(data).status_code == 503
    assert memory.objects


def test_analysis_failure_does_not_upload(saved_images, monkeypatch):
    store, identity, memory, data = saved_images
    monkeypatch.setattr(deepfakeAI_analysis, 'analyse_deepfakeAI', Mock(side_effect=RuntimeError()))
    assert submit(data).status_code == 503
    assert memory.uploads == 0


def test_storage_disabled_keeps_existing_behaviour(saved_images, monkeypatch):
    store, identity, memory, data = saved_images
    monkeypatch.setenv('SAVE_ANALYSIS_IMAGES', '0')
    result = submit(data).json()
    assert result['saved_image'] is None
    assert memory.uploads == 0


@pytest.mark.parametrize('endpoint', ['/analysis/deepfakeAI', '/analysis/image-context'])
def test_upload_limit_before_reservation(saved_images, monkeypatch, endpoint):
    store, identity, memory, data = saved_images
    monkeypatch.setattr(images, 'MAX_IMAGE_BYTES', 5)
    assert submit(data, endpoint).status_code == 413
    assert not any(collection == 'usage_allowances' for collection, _ in store.documents)


def test_decoded_size_limit(saved_images, monkeypatch):
    monkeypatch.setattr(images, 'MAX_IMAGE_PIXELS', 10)
    assert submit(saved_images[3]).status_code == 400


def test_wrong_object_prefix_rejected():
    adapter = images.ImageStorage(Mock())
    attachment = images.SavedImage(object_path='someone-elses/image', generation=1,
                                   content_type='image/png', size_bytes=10)
    with pytest.raises(ValueError):
        adapter.read('owner', 'a' * 32, attachment)


def test_cloud_upload_is_private_and_generation_guarded():
    bucket = Mock()
    bucket.blob.return_value.generation = 4
    adapter = images.ImageStorage(bucket)
    attachment = adapter.upload('owner', {'result_id': 'a' * 32, 'token': 'server-token'}, b'png', 'image/png')
    assert attachment.generation == 4
    assert bucket.blob.return_value.cache_control == 'private, no-store'
    bucket.blob.return_value.upload_from_string.assert_called_once_with(
        b'png', content_type='image/png', if_generation_match=0, timeout=30)
    bucket.blob.return_value.make_public.assert_not_called()
