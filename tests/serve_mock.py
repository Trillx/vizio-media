"""Isolated browser fixture. Never used by run.py or production routes."""

import sys
import os
import tempfile
from pathlib import Path

import httpx
import uvicorn
from fastapi import Request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.config import Settings
from app.main import create_app
from test_accounts_catalog import Cloud
from playback_fixtures import FakeCoco


class BrowserCloud(Cloud):
    def __call__(self,request):
        if request.url.path=='/3/trending/all/week':
            data=super().__call__(request).json()
            data['results']=data['results'][:2]+[{'id':i+500,'media_type':'movie','title':'Movie night '+str(i+1),'release_date':'2020-02-01'} for i in range(18)]
            return httpx.Response(200,json=data)
        if request.url.path.startswith('/3/movie/') and request.url.path.endswith('/recommendations'):
            return httpx.Response(200,json={'results':[{'id':505,'title':'Another Test Film'}]})
        if request.url.path.startswith('/3/movie/5'):
            identifier=int(request.url.path.rsplit('/',1)[1])
            return httpx.Response(200,json={'id':identifier,'title':'Movie night '+str(identifier-499),'release_date':'2020-02-01'})
        if request.url.path.startswith('/3/search/') and request.url.params.get('query')=='Many':
            return httpx.Response(200,json={'total_pages':2,'results':[
                {'id':i+500,'media_type':'movie','title':'A longer catalog title for result '+str(i+1),'release_date':'2020-02-01'} for i in range(20)
            ]})
        if request.url.path in {'/t/p/w342/art.jpg','/t/p/w780/wide.jpg'}:
            return httpx.Response(200,content=(ROOT/'web/art/hero.jpg').read_bytes(),headers={'Content-Type':'image/jpeg'})
        return super().__call__(request)


if __name__=='__main__':
    (ROOT/'.tmp').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='browser-accounts-',dir=ROOT/'.tmp') as directory:
        cloud=BrowserCloud()
        port=int(os.getenv('VIZIO_FIXTURE_PORT','8767'))
        app=create_app(Settings(bind_ip='127.0.0.1',port=port,data_dir=Path(directory),media_dir=ROOT/'media'),transport=httpx.MockTransport(cloud),coco=FakeCoco())

        @app.post('/__test__/approve/{service}')
        def approve(service: str):
            cloud.approved[service]=True
            return {'approved':True}

        uvicorn.run(app,host='127.0.0.1',port=port,proxy_headers=False,access_log=False)
