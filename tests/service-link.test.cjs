const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../web/service-link.js'),'utf8');

function fixture() {
  const timers=new Map(); let counter=0;
  const scope={window:{},Date,setTimeout(fn){timers.set(++counter,fn);return counter;},clearTimeout(id){timers.delete(id);}};
  vm.runInNewContext(source,scope);
  return {create:scope.window.VizioLink,timers};
}
const paths={start:service=>'/accounts/'+service+'/start',flow:id=>'/flows/'+id};
const pending={id:'test-flow',state:'pending',interval:1,expires_at:Date.now()/1000+60};

test('completion callback can clear the linking controller without a stale poll',()=>{
  const {create,timers}=fixture(); let linker;
  const request=(method,path,data,done)=>done(true,path.endsWith('/poll')?{...pending,state:'connected'}:pending);
  linker=create(request,paths,flow=>{if(flow&&flow.state==='connected') linker.cancel();});
  linker.start('trakt');
  assert.equal(timers.size,1);
  const callback=[...timers.values()][0]; timers.clear();
  assert.doesNotThrow(callback);
  assert.equal(timers.size,0);
});

test('cancel while requesting a device code also cancels the late returned flow',()=>{
  const {create,timers}=fixture(), requests=[]; let respond;
  const linker=create((method,path,data,done)=>{
    requests.push({method,path});
    if(method==='POST') respond=done; else done(true,{});
  },paths,()=>{});
  linker.start('trakt'); linker.cancel(); respond(true,pending);
  assert.deepEqual(requests,[{method:'POST',path:'/accounts/trakt/start'},{method:'DELETE',path:'/flows/test-flow'}]);
  assert.equal(timers.size,0);
});

test('an error callback can cancel without leaving a retry timer',()=>{
  const {create,timers}=fixture(); let linker;
  const request=(method,path,data,done)=>done(!path.endsWith('/poll'),path.endsWith('/poll')?{detail:'Offline'}:pending);
  linker=create(request,paths,(flow,error)=>{if(flow&&error) linker.cancel();});
  linker.start('trakt');
  const callback=[...timers.values()][0]; timers.clear();
  assert.doesNotThrow(callback);
  assert.equal(timers.size,0);
});
