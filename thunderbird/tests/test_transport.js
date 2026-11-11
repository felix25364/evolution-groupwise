/* SPDX-License-Identifier: LGPL-2.1-or-later */
const assert = require('node:assert/strict');
const Transport = require('../extension/transport.js');
class Event {
  constructor() { this.listeners=[]; }
  addListener(f) { this.listeners.push(f); }
  emit(v) { this.listeners.forEach(f => f(v)); }
}
function runtime() {
  return {ports:[], connectNative(name) {
    assert.equal(name,'org.evolution_groupwise.host');
    const port={onMessage:new Event(),onDisconnect:new Event(),sent:[],
      postMessage(m){this.sent.push(m);},disconnect(){this.onDisconnect.emit();}};
    this.ports.push(port);return port;
  }};
}
(async () => {
  const r=runtime(), t=new Transport(r,100);
  const a=t.request('ping'), b=t.request('listFolders');
  const port=r.ports[0];
  port.onMessage.emit({id:port.sent[1].id,ok:true,result:{folders:[]}});
  port.onMessage.emit({id:port.sent[0].id,ok:true,result:{protocolVersion:1}});
  assert.deepEqual(await a,{protocolVersion:1});assert.deepEqual(await b,{folders:[]});
  const fail=t.request('login');
  port.onMessage.emit({id:port.sent[2].id,ok:false,error:{code:'AUTH_FAILED',message:'Login failed'}});
  await assert.rejects(fail,{code:'AUTH_FAILED'});
  const lost=t.request('ping');port.onDisconnect.emit();
  await assert.rejects(lost,{code:'HOST_DISCONNECTED'});
  const again=t.request('ping');assert.equal(r.ports.length,2);
  r.ports[1].onMessage.emit({id:r.ports[1].sent[0].id,ok:true,result:{}});await again;
  // Late disconnect from an obsolete port must not close a replacement port.
  port.onDisconnect.emit();assert.equal(t.port,r.ports[1]);
  const timeout=t.request('ping');await assert.rejects(timeout,{code:'HOST_TIMEOUT'});
  assert.equal(t.pending.size,0);assert.equal(t.port,null);
  const closed=t.request('ping');t.close();await assert.rejects(closed,{code:'HOST_CLOSED'});
  await assert.rejects(t.request('ping',{data:'x'.repeat(250000)}),/REQUEST_TOO_LARGE/);
  await assert.rejects(t.request('ping',{data:'✓'.repeat(85000)}),/REQUEST_TOO_LARGE/);
  const vm=require('node:vm'),fs=require('node:fs');
  let beforeSend;
  const browser={runtime:{onMessage:{addListener(){}},connectNative(){}},
    groupwise:{onRequest:{addListener(){}},bootstrap(){},async isGroupwiseIdentity(id){return id==='groupwise';}},
    compose:{onBeforeSend:{addListener(f){beforeSend=f;}}}};
  vm.runInNewContext(fs.readFileSync(require.resolve('../extension/background.js'),'utf8'),{browser,GroupwiseTransport:Transport});
  assert.equal((await beforeSend({}, {identityId:'groupwise'})).cancel,true);
  assert.equal((await beforeSend({}, {identityId:'other'})).cancel,undefined);
  console.log('transport: correlation, structured errors, disconnect/reconnect, stale disconnect, timeout, close, size limit passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
