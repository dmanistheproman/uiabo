from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.accounts import deletion
from app.auth.models import AuthenticatedUser
from app.main import app

RUN_PENDING = deletion.DeletionService.run_pending

NOW = datetime(2026,11,2,tzinfo=timezone.utc)


class Database:
    def __init__(self): self.docs = {}
    def collection(self,name): return Collection(self,name)
    def transaction(self): return self
    def update(self,ref,data): ref.set(data,merge=True)
    def set(self,ref,data,**kwargs): ref.set(data,**kwargs)


class Reference:
    def __init__(self,db,collection,key): self.db,self.collection,self.id=db,collection,key
    def get(self,**kwargs): return self
    def to_dict(self): return deepcopy(self.db.docs.get((self.collection,self.id)))
    @property
    def reference(self): return self
    def set(self,data,merge=False):
        key=(self.collection,self.id)
        self.db.docs[key]={**(self.db.docs.get(key,{}) if merge else {}),**data}
    def delete(self): self.db.docs.pop((self.collection,self.id),None)


class Collection:
    def __init__(self,db,name,field_filter=None): self.db,self.name,self.filter=db,name,field_filter
    def document(self,key): return Reference(self.db,self.name,key)
    def where(self,filter): return Collection(self.db,self.name,filter)
    def stream(self):
        return iter([self.document(key) for (name,key),data in list(self.db.docs.items())
            if name==self.name and (self.filter is None or data.get(self.filter.field_path)==self.filter.value)])


@pytest.fixture
def context(monkeypatch):
    monkeypatch.setattr(deletion.firestore,"transactional",lambda f:f)
    monkeypatch.setattr(deletion,"get_firebase_app",lambda:None)
    monkeypatch.delenv("FIREBASE_STORAGE_BUCKET",raising=False)
    for name in ["update_user","revoke_refresh_tokens","delete_user"]:
        monkeypatch.setattr(deletion.auth,name,Mock())
    db=Database()
    db.docs['users','owner']={'role':'premium','account_status':'active'}
    service=deletion.DeletionService(db,lambda:NOW)
    user=AuthenticatedUser(uid='owner',email='owner@example.org',email_verified=True,auth_time=int(NOW.timestamp()))
    return db,service,user


def test_deletion_requires_recent_auth_and_app_role(context):
    db,service,user=context
    with pytest.raises(HTTPException): service.request(user.model_copy(update={'auth_time':None}))
    with pytest.raises(HTTPException): service.request(user.model_copy(update={'auth_time':int(NOW.timestamp())-301}))
    db.docs['users','owner']['role']='system_admin'
    with pytest.raises(HTTPException): service.request(user)
    assert ('account_deletions','owner') not in db.docs


def test_deletion_refuses_active_analysis_then_is_idempotent(context):
    db,service,user=context
    db.docs['analysis_locks','owner']={'expires_at':NOW+timedelta(seconds=60)}
    with pytest.raises(HTTPException): service.request(user)
    db.docs.pop(('analysis_locks','owner'))
    assert service.request(user)['status']=='pending'
    assert service.request(user)['status']=='pending'
    assert db.docs['users','owner']['account_status']=='deactivated'
    assert db.docs['account_deletions','owner']['not_before']==NOW+timedelta(minutes=5)


def test_staff_type_cannot_self_delete_even_with_stale_premium_role(context):
    db, service, user = context
    db.docs['users', 'owner']['account_type'] = 'staff'
    db.docs['users', 'owner']['operational_roles'] = ['data_engineer', 'system_admin']
    with pytest.raises(HTTPException) as error:
        service.request(user)
    assert error.value.status_code == 403
    assert ('account_deletions', 'owner') not in db.docs


def test_cleanup_owned_content_and_images_only(context,monkeypatch):
    db,service,user=context
    service.request(user)
    for collection in ['analysis_results','feedback','result_reports']:
        db.docs[collection,'mine']={'user_id':'owner'}
        db.docs[collection,'other']={'user_id':'someone-else'}
    db.docs['pipeline_runs','mine']={'run_id':'mine'}
    db.docs['usage_allowances','owner']={}
    db.docs['demo_payments','owner']={'user_id':'owner','mode':'demo'}
    db.docs['analysis_results','mine']['saved_image']={'object_path':'owned'}
    bucket=Mock()
    blob=Mock(generation=12)
    bucket.list_blobs.return_value=[blob]
    monkeypatch.setattr(deletion,'get_image_storage',lambda:SimpleNamespace(bucket=bucket))
    service.cleanup('owner')
    blob.delete.assert_called_once_with(if_generation_match=12,timeout=30)
    prefix=bucket.list_blobs.call_args.kwargs['prefix']
    assert prefix.startswith('analysis-images/') and '//' not in prefix
    assert {key for key in db.docs if key[0] != 'deleted_account_receipts'}=={('analysis_results','other'),('feedback','other'),('result_reports','other')}
    assert len([key for key in db.docs if key[0] == 'deleted_account_receipts']) == 1
    deletion.auth.delete_user.assert_called_once()


def test_storage_failure_keeps_job_and_auth_record_for_retry(context,monkeypatch):
    db,service,user=context
    service.request(user)
    db.docs['analysis_results','mine']={'user_id':'owner','saved_image':{'object_path':'owned'}}
    monkeypatch.setattr(deletion,'get_image_storage',Mock(side_effect=RuntimeError('offline')))
    with pytest.raises(RuntimeError): service.cleanup('owner')
    assert ('account_deletions','owner') in db.docs and ('analysis_results','mine') in db.docs
    deletion.auth.delete_user.assert_not_called()


def test_delete_endpoint_uses_authenticated_owner(signed_analysis):
    _,identity=signed_analysis
    service=Mock()
    service.request.return_value={'status':'pending'}
    app.dependency_overrides[deletion.get_deletion_service]=lambda:service
    response=TestClient(app).delete('/account/me')
    assert response.status_code==202
    assert service.request.call_args.args[0].uid==identity['user'].uid


def test_pending_cleanup_resumes_and_retries_after_failure(context, monkeypatch):
    db, service, user = context
    service.request(user)
    cleanup = Mock(side_effect=RuntimeError('temporary storage outage'))
    monkeypatch.setattr(service, 'cleanup', cleanup)
    RUN_PENDING(service)
    cleanup.assert_not_called()
    service.clock = lambda: NOW + timedelta(minutes=6)
    RUN_PENDING(service)
    assert db.docs['account_deletions','owner']['status'] == 'retry_pending'
    assert db.docs['account_deletions','owner']['not_before'] == NOW + timedelta(minutes=7)
    assert 'temporary storage outage' not in str(db.docs)


def test_late_report_write_cannot_recreate_deleted_data(context):
    from app.accounts.owned_writes import write_owned
    db, service, user = context
    service.request(user)
    with pytest.raises(HTTPException):
        write_owned(db, 'result_reports', 'report', 'owner', {'user_id':'owner'})
    assert ('result_reports','report') not in db.docs


def test_deleted_profile_cannot_be_recreated_by_late_request(context):
    from app.accounts.repository import FirestoreAccountRepository
    db, service, user = context
    service.request(user)
    service.cleanup(user.uid)
    repository = FirestoreAccountRepository(db, clock=lambda:NOW)
    with pytest.raises(HTTPException) as error:
        repository.ensure_free_profile(user, 'A stale profile request')
    assert error.value.status_code == 403
    assert ('users',user.uid) not in db.docs
