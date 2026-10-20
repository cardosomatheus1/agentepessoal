import asyncio, re, time
from pathlib import Path
from flask import Request, Response
from helpers.api import ApiHandler
from plugins._browser.helpers.runtime import _BrowserRuntimeCore, get_runtime
CTX="H91mXoKi"; NEXOS_TAB=48; ADS_TAB=4
ACCOUNT="1838075407512261"; COMPANY="NEXOS TESTE REVISÃO ADS"
NAME="Teste de tráfego 3"; URL="https://dev.sejanexos.com.br"; COPY="Conheça a Raiz Connect."
BASE=Path('/a0/usr/chats/H91mXoKi/anexos/videos/fase3')

async def _page(self, tab, host):
    entry=self.pages.get(tab)
    if not entry: return None,"tab_unavailable"
    p=entry.page; u=await p.evaluate('() => location.href')
    if not str(u).startswith('https://'+host+'/'): return None,"origin_mismatch"
    return p,None

async def workflow(self, op):
    if self.current_context_id != CTX: return {"blocked":"context_mismatch"}
    allowed={'inspect','record_nexos_start','record_nexos_stop','record_ads_start','record_ads_stop','open_create','form_snapshot','submit_create','inspect_nexos','inspect_manager','open_budget','budget_snapshot','fill_budget_35','confirm_budget','cleanup'}
    if op not in allowed: return {"blocked":"unsupported_operation"}
    if op=='cleanup':
        state=getattr(self,'_ads3_capture',None)
        if state:
            state['stop']=True
            with __import__('contextlib').suppress(Exception): await state['task']
            delattr(self,'_ads3_capture')
        return {"ok":True}
    if op in {'record_nexos_start','record_nexos_stop','record_ads_start','record_ads_stop'}:
        stop=op.endswith('_stop'); tab=ADS_TAB if '_ads_' in op else NEXOS_TAB
        p,err=await _page(self,tab,'adsmanager.facebook.com' if tab==ADS_TAB else 'dev.sejanexos.com.br')
        if err:return {"blocked":err}
        state=getattr(self,'_ads3_capture',None)
        if stop:
            if not state:return {"blocked":"no_capture_active"}
            if state['tab']!=tab:return {"blocked":"capture_source_mismatch"}
            state['stop']=True
            await state['task']
            frames=state['frames']; result={"stopped":True,"tab":tab,"frames":frames,"dir":str(state['dir']),"start":state['start'],"end":time.time()}
            delattr(self,'_ads3_capture'); return result
        if state:return {"blocked":"capture_already_active"}
        stamp=time.strftime('%Y%m%d_%H%M%S')
        d=BASE/f'ads3_source_tab_{tab}_{stamp}_raw'
        d.mkdir(parents=True,exist_ok=False)
        state={'tab':tab,'dir':d,'start':time.time(),'frames':0,'stop':False}
        async def loop():
            start=time.time(); idx=0
            while not state['stop'] and time.time()-start<600:
                try:
                    await p.screenshot(path=str(d/f'frame_{idx:05d}.png'),full_page=False)
                    idx+=1; state['frames']=idx
                except Exception as e:
                    state['error']=type(e).__name__; break
                await asyncio.sleep(0.25)
        state['task']=asyncio.create_task(loop()); self._ads3_capture=state
        await asyncio.sleep(.6)
        return {"recording":True,"tab":tab,"frames":state['frames'],"dir":str(d),"start":state['start'],'max_seconds':600}
    p,err=await _page(self,NEXOS_TAB,'dev.sejanexos.com.br')
    if err:return {"blocked":err}
    body=await p.locator('body').inner_text()
    if op in {'inspect','inspect_nexos'}:
        i=body.find('Teste de tráfego 3')
        return {'url_ok':True,'account_present':ACCOUNT in body or COMPANY in body,'campaign3_present':i>=0,'around':body[max(0,i-300):i+1400] if i>=0 else body[-2200:],'buttons':await p.locator('button').all_text_contents(),'inputs':await p.locator('input,textarea,select').evaluate_all("els=>els.map(e=>({tag:e.tagName,type:e.type||'',name:e.name||'',placeholder:e.placeholder||'',aria:e.getAttribute('aria-label')||'',value:(e.type==='password'||/token|secret|password/i.test((e.name||'')+' '+(e.placeholder||'')))?'[redacted]':e.value||''}))")}
    if op=='open_create':
        if NAME in body:return {'blocked':'campaign3_already_present_no_duplicate'}
        if 'NEXOS TESTE REVISÃO ADS' not in body or ACCOUNT not in body:return {'blocked':'sandbox_account_not_confirmed'}
        btn=p.get_by_role('button',name='Criar campanha de teste',exact=True)
        n=await btn.count()
        if n!=1:return {'blocked':'create_button_not_unique','count':n}
        await btn.click(); await p.wait_for_timeout(600)
        return {'opened':True,'text':(await p.locator('body').inner_text())[-2500:]}
    if op=='form_snapshot':
        return {'text':body[-3500:],'fields':await p.locator('input,textarea,select').evaluate_all("els=>els.map(e=>({tag:e.tagName,type:e.type||'',name:e.name||'',placeholder:e.placeholder||'',aria:e.getAttribute('aria-label')||'',value:(e.type==='password'||/token|secret|password/i.test((e.name||'')+' '+(e.placeholder||'')))?'[redacted]':e.value||''}))"),'buttons':await p.locator('button').all_text_contents()}
    if op=='submit_create':
        if NAME in body:return {'blocked':'campaign3_already_present_no_duplicate'}
        if NAME not in body or URL not in body or COPY not in body or 'R$ 20,00' not in body:return {'blocked':'form_values_not_verified'}
        buttons=await p.locator('button').all_text_contents()
        if 'Revisar campanha' not in [x.strip() for x in buttons] and 'Revisar' not in [x.strip() for x in buttons]:return {'blocked':'review_button_not_found','buttons':buttons}
        label='Revisar campanha' if 'Revisar campanha' in [x.strip() for x in buttons] else 'Revisar'
        await p.get_by_role('button',name=label,exact=True).click(); await p.wait_for_timeout(700)
        return {'review_opened':True,'text':(await p.locator('body').inner_text())[-3200:]}
    if op=='inspect_manager':
        q,e=await _page(self,ADS_TAB,'adsmanager.facebook.com')
        if e:return {'blocked':e}
        mu=await q.evaluate('() => location.href')
        if ('act='+ACCOUNT) not in str(mu):return {'blocked':'wrong_ads_account'}
        t=await q.locator('body').inner_text(); i=t.find(NAME)
        return {'url_ok':True,'campaign_present':i>=0,'excerpt':t[max(0,i-300):i+1200] if i>=0 else t[-1200:]}
    if op=='open_budget':
        if NAME not in body:return {'blocked':'campaign3_not_visible'}
        if 'R$ 20,00 por dia' not in body:return {'blocked':'campaign3_budget_not_20'}
        result=await p.evaluate("""({name})=>{let hs=[...document.querySelectorAll('*')].filter(e=>e.children.length===0&&(e.textContent||'').trim()===name);let set=new Set;for(let n of hs){for(let a=n,d=0;a&&d<9;a=a.parentElement,d++){let t=a.innerText||'';if(t.includes(name)&&t.includes('R$ 20,00 por dia'))for(let b of a.querySelectorAll('button'))if((b.innerText||'').trim()==='Mudar orçamento')set.add(b)}}if(set.size!==1)return {clicked:false,candidates:set.size};let b=[...set][0];b.click();return {clicked:true,label:(b.innerText||'').trim()}}""",{'name':NAME})
        return result
    if op=='budget_snapshot':
        return {'text':body[-2600:],'fields':await p.locator('input,textarea,select').evaluate_all("els=>els.map(e=>({tag:e.tagName,type:e.type||'',name:e.name||'',label:e.getAttribute('aria-label')||'',value:e.value||''}))"),'buttons':await p.locator('button').all_text_contents()}
    if op=='fill_budget_35':
        # Fill only if exact campaign name and budget-change review context visible.
        if NAME not in body or ('Mudar orçamento' not in body and 'Alterar orçamento' not in body):return {'blocked':'budget_dialog_not_visible'}
        fields=await p.locator('input').count()
        if fields!=1:return {'blocked':'budget_input_not_unique','count':fields}
        await p.locator('input').fill('35'); return {'filled':True,'value':'35'}
    if op=='confirm_budget':
        if NAME not in body or 'R$ 20,00' not in body or 'R$ 35,00' not in body:return {'blocked':'budget_review_not_exact'}
        labels=[x.strip() for x in await p.locator('button').all_text_contents()]
        opts=[x for x in labels if x in {'Confirmar','Confirmar alteração','Salvar alteração','Confirmar orçamento'}]
        if len(opts)!=1:return {'blocked':'confirm_not_unique','labels':labels}
        await p.get_by_role('button',name=opts[0],exact=True).click(); await p.wait_for_timeout(1200)
        after=await p.locator('body').inner_text(); i=after.find(NAME)
        return {'clicked':True,'excerpt':after[max(0,i-300):i+1200] if i>=0 else after[-1800:]}
    return {'blocked':'unhandled'}

_BrowserRuntimeCore.nexos_ads_campaign3_workflow=workflow
class Fixed(ApiHandler):
    @classmethod
    def requires_loopback(cls):return True
    @classmethod
    def requires_auth(cls):return False
    @classmethod
    def requires_csrf(cls):return False
    @classmethod
    def get_methods(cls):return ['POST']
    async def process(self,input:dict,request:Request):
        allowed={'inspect','record_nexos_start','record_nexos_stop','record_ads_start','record_ads_stop','open_create','form_snapshot','submit_create','inspect_nexos','inspect_manager','open_budget','budget_snapshot','fill_budget_35','confirm_budget','cleanup'}
        if set(input)!={'operation'} or input.get('operation') not in allowed:return Response('invalid fixed request',400)
        rt=await get_runtime(CTX,create=False)
        if rt is None:return {'blocked':'original_runtime_not_registered'}
        return await rt.call('nexos_ads_campaign3_workflow',input['operation'])
