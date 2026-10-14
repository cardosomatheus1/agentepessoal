# AgendaJá (fictitious brand): four app screens drawn in plain HTML, captured like a phone print (300x649 css, dpr 2.6).
import os
from playwright.sync_api import sync_playwright
F = "file://" + os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../motor/fontes")) + "/"
OUT = os.path.dirname(os.path.abspath(__file__)) + "/"
CSS = f"""@font-face{{font-family:B;src:url({F}brico.woff2)}}
@font-face{{font-family:I;src:url({F}Inter-Medium.otf);font-weight:500}}@font-face{{font-family:I;src:url({F}Inter-Bold.otf);font-weight:700}}@font-face{{font-family:I;src:url({F}Inter-ExtraBold.otf);font-weight:800}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{width:300px;height:649px;overflow:hidden;background:#f6f4fb;font-family:I;color:#1d1530;font-size:12px}}
.sb{{display:flex;justify-content:space-between;padding:12px 20px 0;font-weight:700;font-size:12px}}
.top{{padding:14px 18px 6px;display:flex;align-items:center;justify-content:space-between}}
h1{{font-family:B;font-size:26px;font-weight:800;letter-spacing:-.5px}}
.sub{{color:#6b6480;font-size:12px;padding:0 18px}}
.av{{width:34px;height:34px;border-radius:50%;background:#e9e0fb;color:#6d28d9;font-weight:800;display:flex;align-items:center;justify-content:center}}
.dias{{display:flex;gap:6px;padding:12px 18px}}
.dia{{flex:1;background:#fff;border-radius:12px;padding:7px 0;text-align:center;color:#6b6480;font-size:10px;box-shadow:0 1px 3px rgba(40,20,80,.06)}}
.dia b{{display:block;font-size:15px;color:#1d1530;margin-top:2px}}
.dia.on{{background:#6d28d9;color:#e9dcff}}.dia.on b{{color:#fff}}
.lista{{padding:4px 18px;display:flex;flex-direction:column;gap:8px}}
.it{{display:flex;gap:10px;align-items:center;background:#fff;border-radius:14px;padding:10px 12px;box-shadow:0 1px 3px rgba(40,20,80,.07)}}
.h{{font-weight:800;font-size:13px;width:40px}}
.it .q{{flex:1}}.it .q b{{display:block;font-size:13px}}.it .q span{{color:#6b6480;font-size:11px}}
.tag{{font-size:10px;font-weight:700;padding:4px 8px;border-radius:999px;background:#e7f7ee;color:#147a43}}
.tag.esp{{background:#fff1e8;color:#c2410c}}
.livre{{border:1.5px dashed #c9b8f2;background:transparent;box-shadow:none;color:#6d28d9}}
.fab{{position:absolute;left:18px;right:18px;bottom:22px;height:48px;border-radius:14px;background:#6d28d9;color:#fff;font-weight:800;font-size:15px;display:flex;align-items:center;justify-content:center;gap:8px}}
.nav{{position:absolute;left:0;right:0;bottom:0;height:62px;background:#fff;display:flex;justify-content:space-around;align-items:center;color:#9a93ad;font-size:10px;font-weight:700;border-top:1px solid #ece8f5}}
.nav div{{text-align:center}}.nav .on{{color:#6d28d9}}
.card{{margin:8px 18px;background:#fff;border-radius:16px;padding:14px;box-shadow:0 1px 3px rgba(40,20,80,.07)}}
.lbl{{color:#6b6480;font-size:11px;font-weight:700;margin-bottom:8px}}
.srv{{display:flex;justify-content:space-between;align-items:center;padding:9px 0;border-bottom:1px solid #f0edf6;font-size:13px;font-weight:700}}
.srv span{{color:#6b6480;font-weight:500;font-size:11px;display:block}}
.srv.on{{color:#6d28d9}}
.rad{{width:18px;height:18px;border-radius:50%;border:2px solid #cfc6e3}}.srv.on .rad{{border:5px solid #6d28d9}}
.horas{{display:grid;grid-template-columns:repeat(4,1fr);gap:6px}}
.hr{{text-align:center;padding:8px 0;border-radius:10px;background:#f3effb;font-weight:700;font-size:12px}}
.hr.x{{color:#c3bdd2;text-decoration:line-through;background:#f7f6fa}}.hr.on{{background:#6d28d9;color:#fff}}
.kpi{{display:grid;grid-template-columns:1fr 1fr;gap:8px;padding:6px 18px}}
.k{{background:#fff;border-radius:14px;padding:12px;box-shadow:0 1px 3px rgba(40,20,80,.07)}}
.k span{{color:#6b6480;font-size:11px;font-weight:700}}.k b{{display:block;font-family:B;font-size:24px;margin-top:4px}}
.k i{{font-style:normal;font-size:10px;font-weight:700;color:#147a43}}
.ok{{display:inline-flex;width:16px;height:16px;border-radius:50%;background:#147a43;color:#fff;align-items:center;justify-content:center}}
"""
CHK = '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12.5l5 5L20 6.5"/></svg>'
NAV = lambda on: '<div class="nav">' + ''.join(f'<div class="{"on" if i == on else ""}">{n}</div>' for i, n in enumerate(["Agenda", "Clientes", "Lembretes", "Caixa"])) + '</div>'
SB = '<div class="sb"><span>9:41</span><span>5G 100%</span></div>'
TELAS = {
 "agendaja-1": SB + """<div class="top"><h1>Agenda</h1><div class="av">SN</div></div><div class="sub">Studio Navalha · 9 horários hoje, 2 livres</div>
 <div class="dias">""" + ''.join(f'<div class="dia{" on" if d == "14" else ""}">{s}<b>{d}</b></div>' for s, d in [("seg","12"),("ter","13"),("qua","14"),("qui","15"),("sex","16"),("sáb","17")]) + """</div>
 <div class="lista">
 <div class="it"><div class="h">09:00</div><div class="q"><b>Rafael</b><span>Corte + barba · Léo</span></div><span class="tag">Confirmado</span></div>
 <div class="it"><div class="h">10:00</div><div class="q"><b>Bianca</b><span>Escova · Carla</span></div><span class="tag">Confirmado</span></div>
 <div class="it livre"><div class="h">11:00</div><div class="q"><b>Horário livre</b><span>aberto no link</span></div></div>
 <div class="it"><div class="h">13:30</div><div class="q"><b>Diego</b><span>Degradê · Léo</span></div><span class="tag esp">Aguardando</span></div>
 <div class="it"><div class="h">14:30</div><div class="q"><b>Marina</b><span>Corte e hidratação · Carla</span></div><span class="tag">Confirmado</span></div>
 <div class="it livre"><div class="h">16:00</div><div class="q"><b>Horário livre</b><span>aberto no link</span></div></div>
 </div>""" + NAV(0),
 "agendaja-2": SB + """<div class="top"><h1>Agendar</h1></div><div class="sub">Studio Navalha · agendaja.app/navalha</div>
 <div class="card"><div class="lbl">Serviço</div>
 <div class="srv"><div>Corte<span>40 min</span></div><div class="rad"></div></div>
 <div class="srv on"><div>Corte + barba<span>1 h</span></div><div class="rad"></div></div>
 <div class="srv" style="border:0"><div>Barba<span>30 min</span></div><div class="rad"></div></div></div>
 <div class="card"><div class="lbl">Sábado, 17 de outubro</div><div class="horas">""" + ''.join(f'<div class="hr{c}">{h}</div>' for h, c in [("09:00"," x"),("10:00",""),("11:00"," x"),("13:00",""),("14:00"," on"),("15:00"," x"),("16:00",""),("17:00","")]) + """</div></div>
 <div class="fab">Confirmar horário</div>""",
 "agendaja-3": SB + """<div class="top"><h1>Lembretes</h1></div><div class="sub">Enviados sozinhos, 24 horas antes</div>
 <div class="lista" style="margin-top:12px">
 <div class="it"><div class="q"><b>Rafael · amanhã 09:00</b><span>Lembrete enviado ontem às 09:00</span></div><span class="tag">Confirmou</span></div>
 <div class="it"><div class="q"><b>Bianca · amanhã 10:00</b><span>Lembrete enviado ontem às 10:00</span></div><span class="tag">Confirmou</span></div>
 <div class="it"><div class="q"><b>Diego · amanhã 13:30</b><span>Pediu para remarcar</span></div><span class="tag esp">Remarcou</span></div>
 <div class="it"><div class="q"><b>Marina · amanhã 14:30</b><span>Lembrete enviado ontem às 14:30</span></div><span class="tag">Confirmou</span></div>
 </div>
 <div class="card" style="margin-top:14px"><div class="lbl">Mensagem do lembrete</div><div style="font-size:13px;line-height:1.45">Oi, Rafael! Seu horário no Studio Navalha é amanhã às 9h. Toque para confirmar ou remarcar.</div></div>""" + NAV(2),
 "agendaja-4": SB + """<div class="top"><h1>Caixa</h1></div><div class="sub">Semana de 5 a 10 de outubro</div>
 <div class="kpi" style="margin-top:10px">
 <div class="k"><span>Atendimentos</span><b>46</b></div>
 <div class="k"><span>Faturado</span><b>R$ 2.940</b></div>
 <div class="k"><span>Faltas</span><b>1</b></div>
 <div class="k"><span>Remarcados</span><b>4</b></div></div>
 <div class="card"><div class="lbl">Por profissional</div>
 <div class="srv"><div>Léo<span>27 atendimentos</span></div><div>R$ 1.710</div></div>
 <div class="srv" style="border:0"><div>Carla<span>19 atendimentos</span></div><div>R$ 1.230</div></div></div>""" + NAV(3),
}
with sync_playwright() as pw:
    b = pw.chromium.launch(args=["--allow-file-access-from-files"])
    pg = b.new_page(viewport={"width": 300, "height": 649}, device_scale_factor=2.6)
    for nome, corpo in TELAS.items():
        p = f"/tmp/{nome}.html"
        open(p, "w").write(f"<!doctype html><html><head><meta charset=utf-8><style>{CSS}</style></head><body>{corpo}</body></html>")
        pg.goto("file://" + p); pg.evaluate("document.fonts.ready"); pg.wait_for_timeout(300)
        pg.screenshot(path=OUT + nome + ".png")
    b.close()
