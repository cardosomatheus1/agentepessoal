# Real-model battery for the prospecting reviewer (costs model calls): run inside the container with the a0 venv.
import importlib.util, json, time
spec = importlib.util.spec_from_file_location("p", str(__import__("pathlib").Path(__file__).resolve().parents[1] / "helpers" / "prospeccao.py"))
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)
lead = {"id": "L1", "nome": "Zen Marmitas", "handle": "zen.marmitas", "segmento": "marmitas congeladas e saladas no pote",
        "cidade": "Salvador", "seguidores": "1.283", "historico": [],
        "motivo": "Bio oferece comida caseira e saudável em Salvador; posts recentes mostram rondelli, cordon bleu e tilápia prontos para aquecer, além de kit de sabores congelados.",
        "sinal": "", "evidencias": {"post_recente": "rondelli recheado congelado, kit de sabores"}}
casos = [  # (id, tipo, texto, base, esperado)
 ("b1", "aquecer", "Esse rondelli recheado parece bem caprichado. Ele também entra no kit da semana?", "post de 08/10: rondelli congelado", False),  # comment with a question (playbook: observation, no question)
 ("b2", "dm_abertura", "Oi, Zen Marmitas! Vi o rondelli congelado de vocês, parece bem caprichado. Uma pergunta de quem também mexe com isso: vocês sabem quanto sobra de verdade em cada marmita depois de embalagem e entrega? A gente fez uma calculadora grátis que mostra isso em poucos minutos, quer que eu mande o link? — Matheus, da Raiz Connect", "post de 08/10: rondelli", False),  # 20/10: rondelli → calculadora is "sem nexo"
 ("b2r", "dm_abertura", "Oi, pessoal da Zen! Vi o rondelli congelado de vocês, parece bem caprichado. Vocês sabem quanto sobra de verdade em cada marmita depois de embalagem e entrega? Se quiser, me manda a receita de um e o preço que vocês cobram que eu faço essa conta de graça. — Matheus, da Raiz Connect", "post de 08/10: rondelli", False),  # asking for the recipe feels invasive (Matheus, 11/10)
 ("b3", "dm_lembrete", "Oi, Zen! Só pra não deixar passar: a calculadora grátis continua no ar: https://raizconnect.com.br/materiais/precificacao/calculadora?utm_source=instagram&utm_medium=dm 🙂", "", False),  # link only in a reply
 ("b4", "aquecer", "Tilápia pronta pra aquecer salva qualquer dia corrido 👏 Sai mais no almoço ou no jantar?", "post de 07/10: tilápia congelada", False),  # comment with a question
 ("b5", "dm_abertura", "Oi, pessoal da Zen! Acompanhei os congelados de vocês, o cordon bleu chamou atenção. Com frango e embalagem subindo do jeito que tá, muita marmitaria vende com margem menor sem perceber. Se quiser, calculo de graça o custo e o lucro de 1 prato de vocês, só preciso da receita e do preço. Topa? — Matheus, da Raiz Connect", "", False),  # market claim with no source (the insumo variant left the playbook)
 ("b6", "dm_abertura", "Oi, Zen Marmitas! Vi o rondelli congelado de vocês, ficou com uma cara ótima. Tô conversando com donos de marmitaria aqui em Salvador pra entender uma coisa: vocês definem o preço fazendo a conta de cada ingrediente ou vai mais pelo preço da concorrência? — Matheus, da Raiz Connect", "post de 08/10: rondelli", False),  # says who but not what the Raiz does
 ("b7", "dm_lembrete", "Oi, Zen! Passando só pra deixar uma coisa útil: fizemos uma calculadora grátis que mostra quanto sobra em cada marmita depois de insumo, embalagem e taxa do iFood, dá pra começar sem cadastro: https://raizconnect.com.br/materiais/precificacao/calculadora?utm_source=instagram&utm_medium=dm 🙂", "", False),  # link only in a reply
 ("r8", "dm_lembrete", "Oi, Zen! Última chamada: só hoje a calculadora grátis tá liberada, corre que amanhã sai do ar! https://raizconnect.com.br/materiais/precificacao/calculadora", "", False),
 ("r6", "aquecer", "Que capricho nesse rondelli! Já são 5 anos de casa, né? Parabéns pela trajetória!", "post de 08/10: rondelli", False),
 ("r7", "dm_lembrete", "Oi, Zen! Ainda não recebi a receita… essa é a última chance de garantir o cálculo grátis, hein! Responde aí 🙏🙏", "", False),
 ("r1", "aquecer", "Que lasanha de berinjela linda! Vocês fazem por encomenda pra festa?", "", False),
 ("r2", "aquecer", "Lindo! Conhece um sistema que calcula o lucro de cada marmita? Chama no direct", "post de 08/10: rondelli", False),
 ("r3", "dm_abertura", "Oi! Nosso ERP de gestão integrada reduz seu CMV em 30% garantido. Quer uma demonstração da solução? — Matheus, da Raiz Connect", "", False),
 ("r4", "dm_abertura", "Oi, Zen Marmitas! Vi que vocês abriram a terceira unidade no Rio Vermelho, parabéns! Vocês sabem quanto sobra em cada marmita? Me manda a receita que eu calculo de graça. — Matheus, da Raiz Connect", "", False),
 # AR Board 20/10 (real messages): gancho sem nexo com a oferta reprova; gancho que leva à oferta passa
 ("n1", "dm_abertura", "Vi que vocês publicaram um cardápio novo nos stories! Sou Matheus, da Raiz Connect, que calcula custo e preço de quem produz comida. Fiz uma calculadora grátis: posso te mandar o link?", "story: cardápio novo", False),
 ("n2", "dm_abertura", "Vi a pergunta no post sobre a diferença entre marinar e temperar! Sou Matheus, da Raiz Connect, que calcula custo e preço pra quem produz comida. Fiz uma calculadora grátis pra mostrar quanto sobra em cada produto. Posso te mandar?", "post: marinar x temperar", False),
 ("n3", "dm_abertura", "Vi que o cardápio de vocês também está no iFood! Aqui é o Matheus, da Raiz Connect: o sistema puxa os pedidos do iFood e mostra quanto sobra em cada marmita depois da taxa. Posso te mandar como funciona?", "bio: peça pelo iFood", True),
 ("n4", "dm_abertura", "Vi que vocês recebem pedidos de marmitas pelo link da bio! Sou o Matheus, da Raiz Connect, que calcula custo e preço para marmitarias. Como vocês chegam no preço: planilha, caderno ou de cabeça?", "bio: link de pedidos", True),
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
