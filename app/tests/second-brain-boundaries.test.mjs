import test from 'node:test';
import assert from 'node:assert/strict';
import {promises as fs} from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {loadSecondBrain,handleSecondBrainRequest,redact,MAX_BYTES,FICHA_MARCA} from '../lib/second-brain.mjs';
// Fontes da allowlist que este fixture não cria: aparecem como ausentes, cada uma com o próprio aviso.
const NOVAS_AUSENTES=[['contexto','ausente'],['rotinas','ausente'],['projetos','ausente'],['documentos','ausente']];
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
test('fixed Matheus sources ignore Fernanda, malformed/oversized files and symlink',async()=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'brain-test-'));
 try{
 await fs.mkdir(path.join(root,'memoria/decisoes'),{recursive:true});await fs.mkdir(path.join(root,'memoria/usuarios'),{recursive:true});await fs.mkdir(path.join(root,'fios'));
 await fs.writeFile(path.join(root,'memoria/decisoes/matheus.json'),JSON.stringify({decisoes:[{id:1,estado:'ativa',valor:'Matheus fixture'}]}));
 await fs.writeFile(path.join(root,'memoria/decisoes/fernanda.json'),JSON.stringify({decisoes:[{valor:'FERNANDA_PRIVATE_SENTINEL'}]}));
 await fs.writeFile(path.join(root,'memoria/usuarios/matheus.md'),`> ${FICHA_MARCA}\n- Fato fixture\n`);await fs.writeFile(path.join(root,'fios/matheus.json'),'{invalid');
 let d=await loadSecondBrain({root});assert.equal(d.decisions.length,1);assert.equal(d.profile.length,1);assert.deepEqual(d.warnings.map(w=>[w.fonte,w.codigo]),[['fios','invalida'],...NOVAS_AUSENTES]);assert.ok(!JSON.stringify(d).includes('FERNANDA_PRIVATE_SENTINEL'));
 await fs.writeFile(path.join(root,'fios/matheus.json'),'x'.repeat(MAX_BYTES+1));d=await loadSecondBrain({root});assert.equal(d.threads.length,0);assert.deepEqual(d.warnings.map(w=>[w.fonte,w.codigo]),[['fios','grande'],...NOVAS_AUSENTES]);
 await fs.unlink(path.join(root,'memoria/usuarios/matheus.md'));await fs.symlink(path.join(root,'memoria/decisoes/fernanda.json'),path.join(root,'memoria/usuarios/matheus.md'));d=await loadSecondBrain({root});assert.equal(d.profile.length,0);assert.ok(!JSON.stringify(d).includes('FERNANDA_PRIVATE_SENTINEL'));
 await fs.symlink(root,path.join(root,'alias'));d=await loadSecondBrain({root:path.join(root,'alias')});assert.equal(d.decisions.length,0);
 }finally{await fs.rm(root,{recursive:true,force:true});}
});
test('common secret formats removed',()=>{assert.ok(!redact('password=fixtureSecret senha: fixtureSecret Bearer abcdefghijk sk-abcdefghijklmnopqrstu').includes('fixtureSecret'));assert.ok(!redact('Bearer abcdefghijk').includes('abcdefghijk'));});
