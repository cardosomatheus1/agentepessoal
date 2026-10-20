import test from 'node:test';
import assert from 'node:assert/strict';
import {normalizeDecisions,normalizeThreads,buildConnections,handleSecondBrainRequest} from '../lib/second-brain.mjs';
import {createHash} from 'node:crypto';
import {createServer} from 'node:http';
const src={id:'fios',rotulo:'Fios'};
test('Unix timestamps and expiry match the real store contract',()=>{
 const [d]=normalizeDecisions({decisoes:[{id:1,estado:'ativa',em:1700000000,valido_ate:1700000100}]},src,'2026-01-01',new Date('2026-01-01'));
 assert.equal(d.em,'2023-11-14T22:13:20.000Z');assert.equal(d.vigente,false);assert.equal(d.estadoEfetivo,'expirada');
});
test('real string ligacoes remains verbatim explicit evidence',()=>{
 const threads=normalizeThreads({fios:[{id:'a',titulo:'A',ligacoes:'Ligação escrita explicitamente',criado:1700000000,atualizado:1700000100}]},src,'2026-01-01');
 const graph=buildConnections(threads);assert.equal(graph.edges.length,1);assert.equal(graph.nodes.find(n=>n.tipo==='texto').rotulo,'Ligação escrita explicitamente');assert.equal(graph.edges[0].evidencia.fioId,'a');assert.ok(graph.edges[0].evidencia.em);
});
test('actual HTTP adapter denies unauthenticated/tenant requests and disables caching',async()=>{
 const env={SECOND_BRAIN_TOKEN_SHA256:createHash('sha256').update('fixture-not-a-real-secret').digest('hex'),SECOND_BRAIN_DATA_ROOT:'/nonexistent-fixture'};
 const server=createServer(async(req,res)=>{const r=await handleSecondBrainRequest(new Request(`http://127.0.0.1${req.url}`,{headers:req.headers}),env);res.writeHead(r.status,r.headers);res.end(JSON.stringify(r.body));});
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 try{const base=`http://127.0.0.1:${server.address().port}`;assert.equal((await fetch(base)).status,401);assert.equal((await fetch(base+'?login=fernanda')).status,400);assert.equal((await fetch(base,{headers:{'x-login':'fernanda'}})).status,403);const r=await fetch(base,{headers:{Authorization:'Bearer fixture-not-a-real-secret'}});assert.equal(r.status,200);assert.match(r.headers.get('cache-control'),/no-store/);const d=await r.json();assert.equal(d.owner,'matheus');assert.deepEqual(d.warnings.map(w=>[w.fonte,w.codigo]),['decisoes','perfil','fios','contexto','rotinas','projetos','documentos'].map(f=>[f,'ausente']));assert.ok(!JSON.stringify(d).includes('fernanda'));}finally{await new Promise(resolve=>server.close(resolve));}
});
