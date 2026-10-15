import json
from types import SimpleNamespace

from app.coco import CocoProvider, DEFAULT_PROVIDERS, PROVIDERS
from app.playback import Choice, format_hint, recommended_file, source_rank
from test_accounts_catalog import environment, owner, WRITE


def test_owner_can_save_provider_selection_and_disable_public_search(environment):
    client, _, app = environment
    assert client.get('/api/admin/source-providers').status_code == 401
    owner(client)
    result = client.get('/api/admin/source-providers').json()['providers']
    assert len(result) == 8
    assert [item['id'] for item in result if item['enabled']] == DEFAULT_PROVIDERS
    for invalid in [['not-a-provider'], ['torrentio','torrentio']]:
        assert client.put('/api/admin/source-providers', json={'providers':invalid}, headers=WRITE).status_code == 422
    chosen = ['ytsmx','nyaa','1337x']
    assert client.put('/api/admin/source-providers', json={'providers':chosen}).status_code == 403
    saved = client.put('/api/admin/source-providers', json={'providers':chosen}, headers=WRITE)
    assert saved.status_code == 200
    assert app.state.services.config('cocoscrapers')['providers'] == chosen
    assert [item['id'] for item in client.get('/api/admin/source-providers').json()['providers'] if item['enabled']] == ['ytsmx','nyaa','1337x']
    assert client.put('/api/admin/source-providers', json={'providers':[]}, headers=WRITE).status_code == 200
    assert CocoProvider(lambda: app.state.services.config('cocoscrapers')).search({'title':'A Test Film'}) == {'items':[], 'providers':{}}
    assert client.post('/api/admin/logout', json={}, headers=WRITE).status_code == 200
    assert client.put('/api/admin/source-providers', json={'providers':chosen}, headers=WRITE).status_code == 401


def test_worker_receives_only_supported_enabled_providers(monkeypatch):
    calls = []
    def run(*args, **kwargs):
        calls.append(json.loads(kwargs['input']))
        return SimpleNamespace(returncode=0,stdout='{"items":[],"providers":{}}')
    monkeypatch.setattr('app.coco.subprocess.run', run)
    CocoProvider(lambda:{'providers':['nyaa','untrusted-module','knaben']}).search({'title':'A Film'})
    assert calls[0]['providers'] == ['nyaa','knaben']
    assert len({item['id'] for item in PROVIDERS}) == len(PROVIDERS)


def test_tv_compatibility_precedes_readiness_then_ready_compatible_sources_win():
    def item(name, ready=False):
        return {'filename':name, **format_hint(name), 'size':100,
                'provider':'real_debrid_library' if ready else 'cocoscrapers', 'status':'downloaded'}
    incompatible = item('A.Film.2160p.HEVC.HDR.DTS.mkv',True)
    compatible = item('A.Film.1080p.H264.AAC.mp4')
    ready = item('A.Film.1080p.H264.AAC.mp4',True)
    assert sorted([incompatible,compatible,ready], key=source_rank) == [ready,compatible,incompatible]
    assert format_hint('A.Film.Dolby.Vision.1080p.H264.mp4')['warning']


def test_recommended_file_ignores_extras_and_wrong_episodes():
    choice = Choice('profile','owner',{'title':'A Test Film','year':'2020'},None,None,{})
    def file(number, path, size=100): return {'id':number,'path':path,'bytes':size}
    files = [file(1,'/A.Test.Film.2020.Extras.H264.AAC.mp4',1000),
             file(2,'/A.Test.Film.2020.sample.mp4'),
             file(3,'/A.Test.Film.2020.HEVC.DTS.mkv',10000),
             file(4,'/A.Test.Film.2020.1080p.H264.AAC.mp4',2000),
             file(5,'/A.Test.Film.2020.1080p.H264.AAC.mp4',500)]
    assert recommended_file(files,choice) == 4
    assert recommended_file(files[:2],choice) is None
    choice.title={'title':'A Test Show','year':'2021'}; choice.season=1; choice.episode=2
    assert recommended_file([file(1,'/A.Test.Show.S01E01.H264.AAC.mp4'),file(2,'/A.Test.Show.S01E02.H264.AAC.mp4')],choice) == 2
    assert recommended_file([file(1,'/A.Test.Show.S01E01.H264.AAC.mp4')],choice) is None
