import asyncio
from copy import deepcopy
from io import BytesIO
from threading import Event
from types import SimpleNamespace
import json
from unittest.mock import Mock
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from app.main import app
from app.routers import deepfakeAI_analysis, image_context_analysis
from app.analyses import image_execution
from app.image_context_analysis import analysis_service


def picture():
    data=BytesIO(); Image.new('RGB',(32,32)).save(data,format='PNG'); return data.getvalue()


@pytest.mark.parametrize('route,module',[('/analysis/deepfakeAI',deepfakeAI_analysis),('/analysis/image-context',image_context_analysis)])
def test_free_user_denied_before_provider(signed_analysis,monkeypatch,route,module):
    store,_=signed_analysis
    monkeypatch.setattr(module,'get_analysis_store',lambda:store)
    response=TestClient(app).post(route,files={'image':('image.png',picture(),'image/png')})
    assert response.status_code==403
    assert response.json()['detail']['error_code']=='PREMIUM_REQUIRED'
    assert len(store.documents)==1


def test_provided_caption_skips_ocr_and_changes_fingerprint(signed_analysis,monkeypatch):
    store,identity=signed_analysis
    store.documents['users',identity['user'].uid]['role']='premium'
    monkeypatch.setenv('SAVE_ANALYSIS_IMAGES','0')
    monkeypatch.setattr(image_context_analysis,'get_analysis_store',lambda:store)
    extraction=Mock(side_effect=AssertionError('Should not OCR provided caption'))
    monkeypatch.setattr(image_context_analysis,'extract_caption',extraction)
    analysis=Mock(return_value={'concern_label':'Not Enough Information','explanation':'No usable sources.','evidence_links':[]})
    monkeypatch.setattr(image_context_analysis,'analyse_image_context',analysis)
    client=TestClient(app)
    def post(caption): return client.post('/analysis/image-context',files={'image':('image.png',picture(),'image/png')},
        data={'caption':caption},headers={'Idempotency-Key':'caption-test'})
    assert post('An event in Singapore today.').status_code==200
    assert post('An event in Singapore today.').status_code==200
    assert post('A different claim.').status_code==409
    assert analysis.call_count==1
    assert analysis.call_args.kwargs['extracted_caption']=='An event in Singapore today.'
    assert store.documents['usage_allowances',identity['user'].uid]['successful_submissions']==1


def test_timeout_keeps_worker_slot_until_inference_finishes():
    done=Event()
    async def scenario():
        with pytest.raises(HTTPException) as timeout:
            await image_execution.run_image_work(lambda:done.wait(2),timeout=.01)
        assert timeout.value.status_code==504
        with pytest.raises(HTTPException) as busy:
            await image_execution.run_image_work(lambda:None)
        assert busy.value.status_code==429
        done.set()
        await asyncio.sleep(.05)
        assert await image_execution.run_image_work(lambda:'ready')=='ready'
    asyncio.run(scenario())


def test_directional_image_label_needs_grounded_citation(monkeypatch):
    monkeypatch.setattr(analysis_service,'GEMINI_API_KEY','test')
    monkeypatch.setattr(analysis_service,'_search_tavily',lambda claim:[{'url':'https://example.org','title':'Report','content':'An exact supporting passage here.'}])
    result={'concern_label':'High Concern','explanation':'A model claim.','evidence_links':[]}
    client=SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kwargs:SimpleNamespace(text=json.dumps(result))))
    monkeypatch.setattr(analysis_service,'client',client)
    def assess(): return analysis_service.analyse_image_context(Image.new('RGB',(32,32)),'caption','claim','image.png')
    assert assess()['concern_label']=='Not Enough Information'
    result['evidence_links']=[{'url':'https://example.org','relationship':'contradicts','summary':'Says otherwise','quote':'Invented evidence passage.'}]
    with pytest.raises(ValueError): assess()
    result['evidence_links'][0]['quote']='An exact supporting passage here.'
    assert assess()['concern_label']=='High Concern'


def test_deepfake_provider_outage_is_not_a_completed_uncertain_result(monkeypatch):
    from app.deepfakeAI_analysis import service
    monkeypatch.setattr(service, 'score_deepfakeAI', lambda image: {'label':'Real'})
    monkeypatch.setattr(service, 'analyse_with_gemini', Mock(side_effect=TimeoutError('provider outage')))
    with pytest.raises(TimeoutError): service.analyse_deepfakeAI(Image.new('RGB',(32,32)))


def test_request_body_limit_before_image_decode(signed_analysis):
    response=TestClient(app).post('/analysis/image-context',content=b'',headers={'Content-Length':str(12*1024*1024)})
    assert response.status_code==413
