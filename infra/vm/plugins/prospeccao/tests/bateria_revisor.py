# Real-model battery for the prospecting reviewer (costs model calls): run inside the container with the a0 venv.
import importlib.util, json, time
spec = importlib.util.spec_from_file_location("p", str(__import__("pathlib").Path(__file__).resolve().parents[1] / "helpers" / "prospeccao.py"))
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)
lead = {"id": "L1", "nome": "Zen Marmitas", "handle": "zen.marmitas", "segmento": "marmitas congeladas e saladas no pote",
        "cidade": "Salvador", "seguidores": "1.283", "historico": [],
        "motivo": "Bio oferece comida caseira e saudável em Salvador; posts recentes mostram rondelli, cordon bleu e tilápia prontos para aquecer, além de kit de sabores congelados.",
        "sinal": "", "evidencias": {"post_recente": "rondelli recheado congelado, kit de sabores"}}
casos = [  # (id, tipo, texto, base, esperado)
 ("b1", "aquecer", "Esse rondelli recheado parece bem caprichado. Ele também entra no kit da semana?", "post de 08/10: rondelli congelado", True),
 ("b2", "dm_abertura", "Oi, Zen Marmitas! Vi o rondelli congelado de vocês, parece bem caprichado. Uma pergunta de quem também mexe com isso: vocês sabem quanto sobra de verdade em cada marmita depois de embalagem e entrega? Se quiser, me manda a receita de um e o preço que vocês cobram que eu faço essa conta de graça. — Matheus, da Raiz Connect", "post de 08/10: rondelli", True),
 ("b3", "dm_lembrete", "Oi, Zen! Só pra não deixar passar: o cálculo continua de pé. Muita gente descobre que um prato que vende bem dá menos lucro do que imaginava. Se quiser, é só mandar a receita de um deles 🙂", "", True),
 ("b4", "aquecer", "Tilápia pronta pra aquecer salva qualquer dia corrido 👏 Sai mais no almoço ou no jantar?", "post de 07/10: tilápia congelada", True),
 ("b5", "dm_abertura", "Oi, pessoal da Zen! Acompanhei os congelados de vocês, o cordon bleu chamou atenção. Com frango e embalagem subindo do jeito que tá, muita marmitaria vende com margem menor sem perceber. Se quiser, calculo de graça o custo e o lucro de 1 prato de vocês, só preciso da receita e do preço. Topa? — Matheus, da Raiz Connect", "", True),
 ("r6", "aquecer", "Que capricho nesse rondelli! Já são 5 anos de casa, né? Parabéns pela trajetória!", "post de 08/10: rondelli", False),
 ("r7", "dm_lembrete", "Oi, Zen! Ainda não recebi a receita… essa é a última chance de garantir o cálculo grátis, hein! Responde aí 🙏🙏", "", False),
 ("r1", "aquecer", "Que lasanha de berinjela linda! Vocês fazem por encomenda pra festa?", "", False),
 ("r2", "aquecer", "Lindo! Conhece um sistema que calcula o lucro de cada marmita? Chama no direct", "post de 08/10: rondelli", False),
 ("r3", "dm_abertura", "Oi! Nosso ERP de gestão integrada reduz seu CMV em 30% garantido. Quer uma demonstração da solução? — Matheus, da Raiz Connect", "", False),
 ("r4", "dm_abertura", "Oi, Zen Marmitas! Vi que vocês abriram a terceira unidade no Rio Vermelho, parabéns! Vocês sabem quanto sobra em cada marmita? Me manda a receita que eu calculo de graça. — Matheus, da Raiz Connect", "", False),
 ("r5", "dm_abertura", "oi zen vi seus produto mt bom vc sab quanto sobra?? manda a receita q eu calculo de graça pra vc ai. — Matheus, da Raiz Connect", "post de 08/10: rondelli", False),
]
acertos = 0
d = {"leads": [lead]}
for rodada in range(2):
    acoes = [{"id": c[0], "lead_id": "L1", "tipo": c[1], "texto": c[2], "base": c[3]} for c in casos]
    t = time.time()
    v = p.revisar_textos(d, acoes)
    for c in casos:
        r = v[c[0]]
        certo = r["aprovado"] == c[4]
        acertos += certo
        print(rodada, c[0], "OK " if certo else "ERR", r["aprovado"], r["motivo"][:110])
    print("s", round(time.time() - t, 1))
print(f"{acertos}/{2*len(casos)}")
