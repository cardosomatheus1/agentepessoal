"""Commercial coordination with the ERP. No screen action is authorized from a local cache.
The local JSON remains the action journal; company identity, ownership and opt-out belong to ops_leads.
"""
import json
import os
import urllib.request


class CoordenacaoIndisponivel(RuntimeError):
    pass


def _pedir(path, payload):
    origin = os.environ.get('RAIZ_CRM_URL', '').rstrip('/')
    token = os.environ.get('PROSPECTING_BRIDGE_TOKEN', '')
    if not origin or len(token) < 32:
        raise CoordenacaoIndisponivel('coordenação comercial não configurada; nenhuma abordagem liberada')
    if not origin.startswith('https://') and not origin.startswith('http://127.0.0.1:'):
        raise CoordenacaoIndisponivel('a coordenação exige HTTPS')
    req = urllib.request.Request(origin + '/api/v1/partners/bridge/' + path,
        data=json.dumps(payload).encode(), method='POST',
        headers={'Content-Type': 'application/json', 'X-Raiz-Prospecting-Token': token})
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.loads(response.read())
    except Exception as exc:
        # Never expose the token, request headers or upstream response payload.
        raise CoordenacaoIndisponivel('não foi possível conferir a reserva no ERP; aguarde') from None


def registro(lead):
    stage = lead.get('etapa', 'novo')
    history = lead.get('historico') or []
    refusal = any('etapa:descartado' == h.get('tipo') and any(w in str(h.get('texto', '')).lower()
        for w in ('não quer', 'nao quer', 'não contat', 'nao contat', 'disse não', 'disse nao', 'opt-out', 'não tenho interesse', 'nao tenho interesse')) for h in history)
    state = 'OPT_OUT' if refusal else 'CLIENT' if stage == 'cliente' else 'RAIZ' if stage in ('aquecido','abordado','lembrado','respondeu','lead','demo','teste') or lead.get('humano') else 'FREE'
    row = {'externalId': lead['id'], 'companyName': lead.get('nome') or lead['handle'],
        'segment': lead.get('segmento') or 'alimentação', 'city': lead.get('cidade') or '',
        'instagram': lead['handle'], 'score': int(lead.get('nota') or 0),
        'source': lead.get('fonte') or lead.get('origem') or 'instagram',
        'evidence': str(lead.get('motivo') or '')[:500], 'state': state}
    for source, target in [('cnpj','cnpj'),('telefone','phone'),('whatsapp','whatsapp'),('email','email'),('site','website'),('bairro','neighborhood'),('uf','uf')]:
        if lead.get(source):
            row[target] = lead[source]
    return row


def permitir(lead):
    answer = _pedir('sync', {'leads': [registro(lead)]})
    rows = answer.get('leads') or []
    if len(rows) != 1 or rows[0].get('blocked'):
        return False, 'lead reservado, já cliente ou com pedido de não contato no ERP'
    claim = _pedir('claim', {'leadId': rows[0]['leadId']})
    if claim.get('allowed') is not True:
        return False, 'o ERP não liberou a abordagem'
    return True, ''


def sincronizar(leads):
    """Bootstrap/replay by source ids, through the same ingestion and dedupe as all ERP sources."""
    output = []
    for start in range(0, len(leads), 50):
        output.extend(_pedir('sync', {'leads': [registro(l) for l in leads[start:start+50]]}).get('leads') or [])
    return output
