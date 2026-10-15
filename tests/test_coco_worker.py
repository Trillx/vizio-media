"""Exercise the unchanged bundled provider parser in an isolated process."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys

from app.coco import ARCHIVE_SHA256

ROOT = Path(__file__).resolve().parents[1]


def test_bundled_coco_archive_matches_pinned_upstream():
    assert hashlib.sha256((ROOT / "vendor/cocoscrapers-1.0.32.zip").read_bytes()).hexdigest() == ARCHIVE_SHA256


def test_real_torrentio_parser_runs_without_kodi_and_filters_wrong_titles():
    script = """
import json,sys
sys.path.insert(0,'coco_worker')
from worker import run_search
calls=[]
def request(url,**kwargs):
 calls.append(url)
 return json.dumps({'streams':[
  {'infoHash':'a'*40,'title':'Big.Buck.Bunny.2008.1080p.H264.AAC.mp4\\n👤 12 💾 1.2 GB'},
  {'infoHash':'b'*40,'title':'A.Different.Movie.2008.1080p.mp4\\n👤 15 💾 2 GB'}]})
result=run_search({'title':{'title':'Big Buck Bunny','year':'2008','ids':{'imdb_id':'tt1254207'}},'providers':['torrentio']},request=request)
print(json.dumps({'result':result,'calls':calls}))
"""
    result = subprocess.run([sys.executable, "-c", script], cwd=ROOT, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["calls"] == ["https://torrentio.strem.fun/stream/movie/tt1254207.json"]
    assert data["result"]["providers"] == {"torrentio": "ok"}
    assert len(data["result"]["items"]) == 1
    assert data["result"]["items"][0]["quality"] == "1080p"
    assert data["result"]["items"][0]["hash"] == "a" * 40


def test_additional_upstream_parsers_and_media_scopes():
    script = """
import json,sys
sys.path.insert(0,'coco_worker')
from worker import run_search
calls=[]
def request(url,**kwargs):
 calls.append(url)
 if 'yts.mx' in url:
  return json.dumps({'status':'ok','data':{'movie_count':1,'movies':[{'title_long':'Big Buck Bunny (2008)',
   'torrents':[{'hash':'c'*40,'quality':'1080p','type':'web','seeds':10,'size':'1 GB'}]}]}})
 return None
title={'title':'Big Buck Bunny','year':'2008','ids':{'imdb_id':'tt1254207'}}
movies=run_search({'title':title,'providers':['piratebay','ytsmx','eztv','not-allowed']},request=request)
episodes=run_search({'title':title,'season':1,'episode':2,'providers':['ytsmx']},request=request)
missing=run_search({'title':{'title':'A Film','year':'2020'},'providers':['torrentio','ytsmx']},request=request)
print(json.dumps({'movies':movies,'episodes':episodes,'missing':missing,'calls':calls}))
"""
    result = subprocess.run([sys.executable, '-c', script], cwd=ROOT, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data['movies']['providers'] == {'ytsmx':'ok','eztv':'skipped'}
    assert {item['hash'] for item in data['movies']['items']} == {'c'*40}
    assert data['episodes']['providers'] == {'ytsmx':'skipped'}
    assert data['missing']['providers'] == {'torrentio':'missing_imdb','ytsmx':'missing_imdb'}
    assert len(data['calls']) == 1
