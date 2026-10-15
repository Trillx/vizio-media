const test=require('node:test');
const assert=require('node:assert/strict');
const {create}=require('../web/suggestions.js');

function fixture() {
    let timer, next=0;
    const requests=[], states=[];
    const controller=create((method,url,body,callback)=>requests.push({method,url,callback}),state=>states.push(state),{
        clock:{setTimeout(fn){timer=fn;return ++next;},clearTimeout(){timer=null;}}
    });
    return {controller,requests,states,tick(){const fn=timer;timer=null;if(fn){fn();}}};
}

test('typing is debounced, uses the selected filter, and returns at most three titles',()=>{
    const f=fixture(); f.controller.search('A','all'); f.tick(); assert.equal(f.requests.length,0);
    f.controller.search('Ali','movie'); f.controller.search('Alien','movie');
    assert.equal(f.requests.length,0); f.tick(); assert.equal(f.requests.length,1);
    assert.equal(f.requests[0].url,'/api/catalog/search?q=Alien&kind=movie&page=1');
    f.requests[0].callback(true,{items:[1,2,3,4]});
    assert.deepEqual(f.states.at(-1),{state:'ready',items:[1,2,3]});
});

test('a late response cannot replace suggestions for a newer query or reopen a dismissed search',()=>{
    const f=fixture(); f.controller.search('Old','all'); f.tick();
    f.controller.search('New','all'); f.tick();
    f.requests[1].callback(true,{items:['new']}); f.requests[0].callback(true,{items:['old']});
    assert.deepEqual(f.states.at(-1).items,['new']);
    f.controller.clear(); f.requests[1].callback(true,{items:['late']});
    assert.deepEqual(f.states.at(-1),{state:'idle',items:[]});
});

test('short queries, watchlists, errors, and malformed responses have explicit states',()=>{
    const f=fixture(); f.controller.search('test','watchlist'); f.tick(); assert.equal(f.requests.length,0);
    f.controller.search('test','tv'); f.tick(); f.requests[0].callback(false,{detail:'Unavailable'});
    assert.equal(f.states.at(-1).state,'error');
    f.controller.search('test','tv'); f.tick(); f.requests[1].callback(true,{});
    assert.equal(f.states.at(-1).state,'error');
    f.controller.search('','all'); assert.equal(f.states.at(-1).state,'idle');
});
