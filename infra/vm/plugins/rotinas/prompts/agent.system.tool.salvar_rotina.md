### salvar_rotina
Salva uma **rotina** reutilizável (vira skill: aparece em `/` e é carregada quando o pedido combina), grava uma **correção** ou **ajusta** um trecho de uma rotina existente.
- `acao: "salvar"`: `nome`, `descricao` (uma frase: o que faz e quando usar), `passos` (lista, com as decisões e cuidados de cada um), `quando_usar`, `entradas` (dados e acessos necessários; senhas só como §§secret(NOME)), `verificar` (como conferir que deu certo), `entregar` (o que devolver ao usuário), `aprovacao` (o que precisa do ok dele), `gatilhos` (palavras que indicam esta rotina). As correções já gravadas continuam na rotina.
- `acao: "corrigir"`: `nome` + `correcao` — quando o usuário corrigir o jeito de fazer algo desta rotina. Correção igual a uma que já existe é recusada.
- `acao: "ler"`: `nome` — mostra a rotina como está agora e a `versao` dela.
- `acao: "ajustar"`: `nome`, `trecho` (texto exato que existe uma vez na rotina), `novo` (o que entra no lugar) e `versao` (a que o `ler` devolveu). Sem reler antes, ou se a rotina mudou depois, nada é trocado: leia de novo.
- Quando a ferramenta disser que a rotina acumulou muitas correções: `ler`, reescreva os passos limpos já com as correções dentro deles e `salvar` com `consolidar: true` e a `versao` lida (a seção de correções sai; a versão anterior fica guardada).
Input schema for tool_args: {"type": "object", "properties": {"acao": {"type": "string", "enum": ["salvar", "corrigir", "ler", "ajustar"]}, "nome": {"type": "string"}, "descricao": {"type": "string"}, "quando_usar": {"type": "string"}, "entradas": {"type": "string"}, "passos": {"type": "array", "items": {"type": "string"}}, "verificar": {"type": "string"}, "entregar": {"type": "string"}, "aprovacao": {"type": "string"}, "gatilhos": {"type": "array", "items": {"type": "string"}}, "correcao": {"type": "string"}, "trecho": {"type": "string"}, "novo": {"type": "string"}, "versao": {"type": "string"}, "consolidar": {"type": "boolean"}}, "required": ["nome"]}
usage:
~~~json
{
    "thoughts": ["Deu certo e ele disse que faz isso toda semana; vou salvar como rotina."],
    "headline": "Salvando a rotina de conferir exames",
    "tool_name": "salvar_rotina",
    "tool_args": {"acao": "salvar", "nome": "Conferir exames novos", "descricao": "Entrar no portal do laboratório, ver se saíram resultados novos e resumir.", "passos": ["Abrir o portal do laboratório", "Entrar com §§secret(LAB_SENHA)", "Abrir 'Resultados' e comparar com a última lista", "Baixar os novos em PDF"], "verificar": "A lista mostra a data de hoje e os PDFs abrem", "entregar": "Resumo em 3 linhas + PDFs pelo whatsapp_enviar", "aprovacao": "Nada; é só leitura", "gatilhos": ["exames", "resultado do laboratório"]}
}
~~~
~~~json
{
    "thoughts": ["Li a rotina (versao 3f2a9c1b7d0e); o passo 3 mudou: troco só ele."],
    "headline": "Ajustando um passo da rotina de exames",
    "tool_name": "salvar_rotina",
    "tool_args": {"acao": "ajustar", "nome": "Conferir exames novos", "versao": "3f2a9c1b7d0e", "trecho": "3. Abrir 'Resultados' e comparar com a última lista", "novo": "3. Abrir 'Laudos' (o menu mudou) e comparar com a última lista"}
}
~~~
