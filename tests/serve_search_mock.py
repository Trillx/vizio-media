"""Isolated UI fixture for provider-list recovery and live title suggestions."""
from pathlib import Path
import sys
import tempfile
import time

import httpx
import uvicorn
from fastapi.responses import JSONResponse

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.config import Settings
from app.main import create_app
from app.security import password_hash
from playback_fixtures import FakeCoco
from serve_mock import BrowserCloud


class SearchCloud(BrowserCloud):
    def __init__(self):
        super().__init__(); self.queries=[]

    def __call__(self,request):
        if request.url.path.startswith('/3/search/'):
            query=request.url.params.get('query',''); self.queries.append(query)
            if query.casefold()=='outage':
                return httpx.Response(503,json={'error':'Controlled test outage'})
            if query.casefold() in {'slow','fast','nomatch'}:
                if query.casefold()=='slow': time.sleep(1.5)
                title='Old slow response' if query.casefold()=='slow' else 'New fast response'
                return httpx.Response(200,json={'total_pages':1,'results':[] if query.casefold()=='nomatch' else
                    [{'id':101,'media_type':'movie','title':title,'release_date':'2020-01-01'}]})
        return super().__call__(request)


if __name__=='__main__':
    (ROOT/'.tmp').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='browser-search-',dir=ROOT/'.tmp') as directory:
        cloud=SearchCloud()
        app=create_app(Settings(bind_ip='127.0.0.1',port=8770,data_dir=Path(directory),media_dir=ROOT/'media'),
                       transport=httpx.MockTransport(cloud),coco=FakeCoco())
        app.state.services.configure('tmdb',{'read_token':'TMDB-READ-SECRET'})
        app.state.store.setup_owner(password_hash('search-fixture-owner-password'))
        app.state.provider_failed=False

        @app.middleware('http')
        async def fail_once(request,call_next):
            if request.method=='GET' and request.url.path=='/api/admin/source-providers' and not app.state.provider_failed:
                app.state.provider_failed=True
                return JSONResponse({'detail':'Provider list temporarily unavailable in this test. Retry.'},status_code=503)
            return await call_next(request)

        @app.get('/__test__/search-state')
        def search_state():
            return {'queries':cloud.queries}

        uvicorn.run(app,host='127.0.0.1',port=8770,proxy_headers=False,access_log=False)
