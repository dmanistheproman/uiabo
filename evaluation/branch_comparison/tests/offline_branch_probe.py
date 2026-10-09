"""Exercise each real branch's result assembly without network or Firestore."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
import tempfile

backend=Path(sys.argv[1])
sys.path.insert(0,str(backend))
os.environ['PYTHONDONTWRITEBYTECODE']='1'
os.environ.pop('PYTHON_DOTENV_DISABLED',None)

def forbidden(*args,**kwargs):
    raise AssertionError('Network or Firebase access during offline evaluation check')

socket.socket.connect=forbidden
import httpx
httpx.Client.send=forbidden
httpx.AsyncClient.send=forbidden
from app.pipeline.orchestration import dependencies
from app.pipeline.orchestration.repository import FirestoreResultRepository
from app.pipeline.orchestration.service import PipelineOrchestrator
from app.pipeline.input_preparation.service import prepare_text
from app.pipeline.shared.models import ClaimAnalysis
FirestoreResultRepository.save_result=forbidden
FirestoreResultRepository.save_failure=forbidden

def fake_runtime():
    return PipelineOrchestrator(prepare_input=prepare_text,
        analyze_claim=lambda _: ClaimAnalysis(extracted_claim=None,claim_category='opinion',checkable=False,
            classification_reason='Offline fixture',claim_confidence=1),
        retrieve_evidence=forbidden,assess_evidence=forbidden,
        repository=FirestoreResultRepository(),pipeline_version='offline-fixture')

dependencies.get_pipeline_orchestrator=fake_runtime
path=Path(__file__).resolve().parents[1]/'worker.py'
spec=importlib.util.spec_from_file_location('probe_worker',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
with tempfile.TemporaryDirectory() as tmp:
    creds=Path(tmp)/'.env'
    creds.write_text('OLLAMA_API_KEY=FAKE_SECRET_FOR_TEST_ONLY\nTAVILY_API_KEY=FAKE_SECRET_FOR_TEST_ONLY\nJEV_API_KEY=FAKE_SECRET_FOR_TEST_ONLY\n',encoding='utf-8')
    result=json.loads(module.run(backend,sys.argv[2],creds,{'claim':'Blue is my favourite colour.',
        'assessed_at':'2026-09-29T01:00:00+00:00','forecast_fixture':None}))
    assert result.get('outcome')=='not_checkable', result.get('error_code')
    assert not result['requests']
    assert result['result']['created_at']=='2026-09-29T01:00:00Z'
    assert result['result']['misinformation_risk_score'] is None
    assert 'FAKE_SECRET_FOR_TEST_ONLY' not in json.dumps(result)
    print(json.dumps({'branch':sys.argv[2],'outcome':result['outcome'],'network_requests':0,'firebase_writes':0}))
