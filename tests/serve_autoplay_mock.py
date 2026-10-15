"""Isolated browser fixture for failed-source recovery and remote pagination."""
from pathlib import Path
import sys
import tempfile
import time
from urllib.parse import parse_qs

import httpx
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.config import Settings
from app.main import create_app
import app.playback as playback_module
from playback_fixtures import media_response
from serve_playback_mock import BrowserPlaybackCloud


class ManySources:
    def search(self,title,season=None,episode=None):
        time.sleep(.6)
        return {'items':[{'hash':str(i)*40,'name':f'A.Test.Film.2020.1080p.H264.AAC.Source{i}.mp4',
                          'provider':'torrentio','size':i} for i in range(1,9)],'providers':{'torrentio':'ok'}}


class AutoCloud(BrowserPlaybackCloud):
    def __init__(self):
        super().__init__(); self.attempts=[]; self.failures=True

    def __call__(self,request):
        path=request.url.path
        if path.endswith('/downloads') or path.endswith('/torrents'):
            return httpx.Response(200,json=[])
        if path.endswith('/torrents/addMagnet'):
            magnet=parse_qs(request.content.decode())['magnet'][0]
            number=magnet.split('btih:')[1][0]; self.attempts.append(number)
            if self.failures and number=='1':
                return httpx.Response(503,json={'error':'unavailable'})
            return httpx.Response(201,json={'id':'source-'+number})
        if '/torrents/info/' in path:
            number=path[-1]
            return httpx.Response(200,json={'id':'source-'+number,'status':'downloaded','progress':100,
                'files':[{'id':20,'path':f'/A.Test.Film.2020.1080p.H264.AAC.Source{number}.mp4','selected':1,'bytes':123456}],
                'links':['https://real-debrid.com/d/source-'+number]})
        if path.endswith('/unrestrict/link'):
            number=parse_qs(request.content.decode())['link'][0][-1]
            return httpx.Response(200,json={'id':'download-'+number,'download':'https://media.example.com/'+number,
                'filename':f'A.Test.Film.2020.1080p.H264.AAC.Source{number}.mp4','filesize':123456,'mimeType':'video/mp4'})
        return super().__call__(request)


if __name__=='__main__':
    (ROOT/'.tmp').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='browser-autoplay-',dir=ROOT/'.tmp') as directory:
        cloud=AutoCloud(); video=(ROOT/'media/sample.mp4').read_bytes()
        def fixture_url(value):
            if value not in ['https://media.example.com/'+str(i) for i in range(1,9)]:
                raise ValueError('Unknown fixture URL')
            return value
        def cdn(request):
            data=b'This is an invalid video.' if cloud.failures and request.url.path=='/2' else video
            return media_response(request,data)
        playback_module.stream_url=fixture_url
        app=create_app(Settings(bind_ip='127.0.0.1',port=8769,data_dir=Path(directory),media_dir=ROOT/'media'),
                       transport=httpx.MockTransport(cloud),coco=ManySources(),media_transport=httpx.MockTransport(cdn))
        app.state.services.configure('tmdb',{'read_token':'TMDB-READ-SECRET'})
        app.state.services.personal_token('household','PRIVATE-RD-API-TOKEN')
        @app.get('/test/state')
        def state():
            return {'attempts':cloud.attempts,'viewings':len(app.state.playback.viewings)}
        @app.post('/test/reset')
        def reset():
            cloud.attempts=[]; cloud.failures=False
            return {'ok':True}
        uvicorn.run(app,host='127.0.0.1',port=8769,proxy_headers=False,access_log=False)
