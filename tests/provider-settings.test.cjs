const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function fixture() {
    const elements = new Map(), requests = [], events = {};
    function element(id) {
        if (!elements.has(id)) {
            elements.set(id, {id,innerHTML:'',textContent:'',hidden:false,disabled:false,
                setAttribute(){},removeAttribute(){},querySelector(){return element(id+'-submit');}});
        }
        return elements.get(id);
    }
    element('provider-options').innerHTML='<legend>Search providers</legend><p>Loading providers...</p>';
    class Request {
        open(method,url) { this.url=url; requests.push(this); }
        setRequestHeader() {} send() {}
        respond(status,data) { this.status=status; this.responseText=JSON.stringify(data); this.onload(); }
    }
    vm.runInNewContext(fs.readFileSync('web/manage.js','utf8'), {
        document:{getElementById:element,addEventListener(name,fn){events[name]=fn;}},
        window:{addEventListener(){}},XMLHttpRequest:Request,clearInterval(){},setInterval(){}
    });
    requests[0].respond(200,{setup_required:false,signed_in:true});
    return {element, requests, events};
}

test('a failed provider request replaces Loading providers with an inline error and retry', () => {
    const f=fixture();
    f.requests.find(request=>request.url==='/api/admin/source-providers').respond(503,{detail:'Server temporarily unavailable.'});
    const html=f.element('provider-options').innerHTML;
    assert.doesNotMatch(html,/Loading providers/);
    assert.match(html,/Server temporarily unavailable/);
    assert.match(html,/providers-retry/);
    assert.equal(f.element('source-providers-submit').disabled,true);
});

test('retry reloads the list and enables saving only after providers arrive', () => {
    const f=fixture();
    f.requests.find(request=>request.url==='/api/admin/source-providers').respond(503,{detail:'Temporary outage'});
    f.events.click({target:{getAttribute(name){return name==='data-action'?'providers-retry':null;}}});
    f.requests.filter(request=>request.url==='/api/admin/status').at(-1).respond(200,{signed_in:true});
    f.requests.filter(request=>request.url==='/api/admin/source-providers').at(-1).respond(200,{providers:[{id:'torrentio',name:'Torrentio',scope:'Movies',enabled:true}]});
    assert.match(f.element('provider-options').innerHTML,/provider-torrentio/);
    assert.doesNotMatch(f.element('provider-options').innerHTML,/Loading providers/);
    assert.equal(f.element('source-providers-submit').disabled,false);
});

test('expired sessions, invalid responses, and network timeouts cannot leave an indefinite loading state', () => {
    for (const kind of ['expired','invalid','timeout']) {
        const f=fixture(), request=f.requests.find(request=>request.url==='/api/admin/source-providers');
        if(kind==='expired') { request.respond(401,{detail:'Sign in'}); }
        if(kind==='invalid') { request.respond(200,{}); }
        if(kind==='timeout') { request.status=0; request.responseText=''; request.ontimeout(); }
        assert.doesNotMatch(f.element('provider-options').innerHTML,/Loading providers/);
        assert.match(f.element('provider-options').innerHTML,/providers-retry/);
        assert.equal(f.element('source-providers-submit').disabled,true);
    }
});
