import test from 'node:test';
import assert from 'node:assert/strict';
import {promises as fs} from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {loadSecondBrain,handleSecondBrainRequest,redact,MAX_BYTES,MAX_ARQUIVOS} from '../lib/second-brain.mjs';
import {frontmatter} from './fixture-brain.mjs';
const hash=createHash('sha256').update('fixture-access').digest('hex');
test('fail closed, wrong token, forbidden tenant and methods',async()=>{
 for(const [url,headers,method,status,env] of [
 ['/',{},'GET',503,{}],['/',{},'GET',401,{SECOND_BRAIN_TOKEN_SHA256:hash}],
 ['/',{authorization:'Bearer wrong'},'GET',401,{SECOND_BRAIN_TOKEN_SHA256:hash}],
 ['/?owner=fernanda',{authorization:'Bearer fixture-access'},'GET',400,{SECOND_BRAIN_TOKEN_SHA256:hash}],
 ['/',{authorization:'Bearer fixture-access','x-tenant':'fernanda'},'GET',403,{SECOND_BRAIN_TOKEN_SHA256:hash}],
 ['/',{},'POST',405,{SECOND_BRAIN_TOKEN_SHA256:hash}]]){
 const r=await handleSecondBrainRequest(new Request('http://localhost'+url,{headers,method}),env);assert.equal(r.status,status);assert.match(r.headers['Cache-Control'],/no-store/);
 }
});
test('only the fixed Pasta folders are read: non-.md, dotfiles, subfolders and index are skipped; count capped',async()=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'brain-test-'));
 const P=path.join(root,'segundo_cerebro/pasta');
 try{
 await fs.mkdir(path.join(P,'Decisoes/sub'),{recursive:true});await fs.mkdir(path.join(P,'Documentos'),{recursive:true});
 await fs.writeFile(path.join(P,'Decisoes/0001-a.md'),frontmatter({id:1,estado:'ativa',valor:'Matheus fixture',area:'Raiz'})+'# a\n');
 await fs.writeFile(path.join(P,'Decisoes/indice.md'),'# índice\n');
 await fs.writeFile(path.join(P,'Decisoes/.0002-oculto.md'),frontmatter({id:2,valor:'HIDDEN_SENTINEL'}));
 await fs.writeFile(path.join(P,'Decisoes/0003-b.json'),JSON.stringify({id:3,valor:'HIDDEN_SENTINEL'}));
 await fs.writeFile(path.join(P,'Decisoes/sub/0004-c.md'),frontmatter({id:4,valor:'HIDDEN_SENTINEL'}));
 await fs.writeFile(path.join(P,'Decisoes/.lock'),'');
 await fs.writeFile(path.join(P,'Pendencias'),'not a folder');
 await fs.writeFile(path.join(P,'Documentos/big.md'),'x'.repeat(MAX_BYTES+1));
 let d=await loadSecondBrain({root});
 assert.deepEqual(d.decisions.map(x=>x.id),['1']);assert.ok(!JSON.stringify(d).includes('HIDDEN_SENTINEL'));
 const f=(id)=>d.sources.find(s=>s.id===id);
 assert.deepEqual([f('pendencias').estado,f('pendencias').codigo],['indisponivel','ausente'],'a file where a folder should be is not a source');
 assert.deepEqual([f('documentos').estado,f('documentos').codigo],['indisponivel','grande']);
 for(let i=0;i<MAX_ARQUIVOS+5;i++)await fs.writeFile(path.join(P,'Documentos',`n${String(i).padStart(5,'0')}.md`),`# n${i}\n`);
 await fs.rm(path.join(P,'Documentos/big.md'));
 d=await loadSecondBrain({root});
 assert.equal(d.documents.length,MAX_ARQUIVOS);assert.deepEqual([d.sources.find(s=>s.id==='documentos').estado,d.sources.find(s=>s.id==='documentos').codigo],['ok','truncada']);
 assert.ok(d.warnings.some(w=>w.fonte==='documentos'&&w.codigo==='truncada'));
 }finally{await fs.rm(root,{recursive:true,force:true});}
});
test('common secret formats removed',()=>{assert.ok(!redact('password=fixtureSecret senha: fixtureSecret Bearer abcdefghijk sk-abcdefghijklmnopqrstu').includes('fixtureSecret'));assert.ok(!redact('Bearer abcdefghijk').includes('abcdefghijk'));});
