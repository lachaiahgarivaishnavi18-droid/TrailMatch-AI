import httpx
from app import main


def test_crud_matching_reports_and_cascade_delete(client):
    assert client.get('/api/health').status_code == 200
    created=client.post('/api/patients',json={"code":"TEST-001","age":54,"conditions":["T2DM"],"labs":{"HbA1c":{"value":8.2,"unit":"%"}}})
    assert created.status_code == 201
    patient=created.json()
    response=client.post('/api/matches',json={"patient_id":patient['id']})
    assert response.status_code == 201
    run=response.json()
    assert run['created_at'].endswith('+00:00')
    assert client.get('/api/runs').json()[0]['created_at'].endswith('+00:00')
    assert len(run['logs']) == 5 and run['results']
    assert client.get(f"/api/runs/{run['id']}").json()['id'] == run['id']
    report=client.get(f"/api/runs/{run['id']}/export?format=csv")
    assert report.status_code == 200 and 'patient_value' in report.text
    assert client.get(f"/api/runs/{run['id']}/export").json()['results']
    assert client.delete(f"/api/patients/{patient['id']}").status_code == 204
    assert client.get(f"/api/runs/{run['id']}").status_code == 404


def test_csv_atomic_validation_and_document_upload(client):
    before=len(client.get('/api/patients').json())
    bad=client.post('/api/patients/import-csv',files={'file':('patients.csv',b'code,age,conditions\nOK,30,T2DM\nBAD,-4,CKD','text/csv')})
    assert bad.status_code == 422
    assert len(client.get('/api/patients').json()) == before
    ok=client.post('/api/patients/import-csv',files={'file':('patients.csv',b'code,age,conditions\nCSV-001,45,T2DM;HTN','text/csv')})
    assert ok.json()['imported'] == 1
    p=next(x for x in client.get('/api/patients').json() if x['code']=='CSV-001')
    note=client.post(f"/api/patients/{p['id']}/document",files={'file':('note.txt',b'No CKD.','text/plain')})
    assert note.status_code == 200
    assert note.json()['normalized_conditions'] == ['type 2 diabetes','hypertension']
    assert client.post(f"/api/patients/{p['id']}/document",files={'file':('binary.txt',b'\x00\xff')}).status_code == 422


def test_import_fallback_and_deduplication(client,monkeypatch):
    def unavailable(*args):
        raise httpx.ConnectError('Offline')
    monkeypatch.setattr(main,'fetch_trials',unavailable)
    assert client.post('/api/trials/import',json={'condition':'diabetes'}).json()['fallback'] is True
    from app.schemas import TrialInput
    t=TrialInput(id='NCT01234567',title='Mocked registry trial',source='ClinicalTrials.gov')
    monkeypatch.setattr(main,'fetch_trials',lambda *args:[t])
    for _ in range(2):
        assert client.post('/api/trials/import',json={'condition':'diabetes'}).json()['imported'] == 1
    assert len([x for x in client.get('/api/trials').json() if x['id']==t.id]) == 1


def test_validation_missing_record_and_local_trial(client):
    assert client.post('/api/patients',json={'code':'bad','age':200}).status_code == 422
    assert client.post('/api/matches',json={'patient_id':'missing'}).status_code == 404
    assert client.post('/api/trials',json={'id':'LOCAL-01','title':'Local trial','eligibility':'Inclusion Criteria:\nAge >= 18'}).status_code == 201
    assert client.get('/api/trials/LOCAL-01/criteria').json()[0]['value'] == 18
    assert client.post('/api/trials/LOCAL-01/suggest-criteria').status_code == 422
