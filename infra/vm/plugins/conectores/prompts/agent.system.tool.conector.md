### conector
Ferramentas dos conectores (google, github) que não estão na sua lista: a lista leva só as de uso comum; todas as outras continuam possíveis.
- `acao`: "listar" (`conector`, opcional `busca`) | "ativar" (`ferramentas`: nomes; entram na lista a partir da próxima chamada) | "descrever" (`ferramenta`: descrição e parâmetros completos)
- GitHub sem `ferramentas`: ativa o básico de leitura (repositórios, arquivos, commits, PRs).
Input schema for tool_args: {"type": "object", "properties": {"acao": {"type": "string", "enum": ["listar", "ativar", "descrever"]}, "conector": {"type": "string", "enum": ["google", "github"]}, "ferramentas": {"type": "array", "items": {"type": "string"}}, "ferramenta": {"type": "string"}, "busca": {"type": "string"}}, "required": ["acao"]}
~~~json
{"tool_name": "conector", "tool_args": {"acao": "ativar", "conector": "google", "ferramentas": ["create_doc", "modify_doc_text"]}}
~~~
