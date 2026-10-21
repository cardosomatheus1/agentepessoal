### ler
Lê um arquivo inteiro, em páginas: planilha `.xlsx`/`.xls` (os **valores calculados**, não as fórmulas; todas as abas visíveis; até 2000 linhas por chamada), `.csv`, Word `.docx` (parágrafos e tabelas), PDF (texto por página; avisa as páginas escaneadas e como ler) e texto. Use para planilha e documento em vez de `document_query` quando precisar dos dados exatos (contar, somar, conferir linha a linha).
`caminho`: o arquivo. `inicio` (opcional): a linha/parágrafo/página onde começar (o resultado diz o próximo). `limite` (opcional): quantas linhas (padrão 200; páginas no PDF: 20). `aba` (opcional): só essa aba da planilha.
Contas e contagens sobre os dados: faça por código (python), não de cabeça.
Input schema for tool_args: {"type": "object", "properties": {"caminho": {"type": "string"}, "inicio": {"type": "integer"}, "limite": {"type": "integer"}, "aba": {"type": "string"}}, "required": ["caminho"]}
usage:
~~~json
{
    "thoughts": ["Vou ler a planilha de NCM inteira para conferir linha a linha."],
    "headline": "Lendo a planilha",
    "tool_name": "ler",
    "tool_args": {"caminho": "/a0/usr/workdir/ncm_76437182/76437182_CL.xlsx", "limite": 500}
}
~~~
