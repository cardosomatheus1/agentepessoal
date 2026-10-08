### salvar_rotina
Salva uma **rotina** reutilizável (vira skill: aparece em `/` e é carregada quando o pedido combina) ou grava uma **correção** numa rotina existente.
- `acao: "salvar"`: `nome`, `descricao` (uma frase: o que faz e quando usar), `passos` (lista, com as decisões e cuidados de cada um), `quando_usar`, `entradas` (dados e acessos necessários; senhas só como §§secret(NOME)), `verificar` (como conferir que deu certo), `entregar` (o que devolver ao usuário), `aprovacao` (o que precisa do ok dele), `gatilhos` (palavras que indicam esta rotina).
- `acao: "corrigir"`: `nome` + `correcao` — quando o usuário corrigir o jeito de fazer algo desta rotina.
Input schema for tool_args: {"type": "object", "properties": {"acao": {"type": "string", "enum": ["salvar", "corrigir"]}, "nome": {"type": "string"}, "descricao": {"type": "string"}, "quando_usar": {"type": "string"}, "entradas": {"type": "string"}, "passos": {"type": "array", "items": {"type": "string"}}, "verificar": {"type": "string"}, "entregar": {"type": "string"}, "aprovacao": {"type": "string"}, "gatilhos": {"type": "array", "items": {"type": "string"}}, "correcao": {"type": "string"}}, "required": ["nome"]}
usage:
~~~json
{
    "thoughts": ["Deu certo e ele disse que faz isso toda semana; vou salvar como rotina."],
    "headline": "Salvando a rotina de conferir exames",
    "tool_name": "salvar_rotina",
    "tool_args": {"acao": "salvar", "nome": "Conferir exames novos", "descricao": "Entrar no portal do laboratório, ver se saíram resultados novos e resumir.", "passos": ["Abrir o portal do laboratório", "Entrar com §§secret(LAB_SENHA)", "Abrir 'Resultados' e comparar com a última lista", "Baixar os novos em PDF"], "verificar": "A lista mostra a data de hoje e os PDFs abrem", "entregar": "Resumo em 3 linhas + PDFs pelo whatsapp_enviar", "aprovacao": "Nada; é só leitura", "gatilhos": ["exames", "resultado do laboratório"]}
}
~~~
