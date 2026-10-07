### analisar_imagens
Analisa muitas imagens (fotos, prints, páginas de documento) **uma a uma** e devolve só texto: o que aparece em cada uma e todo texto legível (lote, caixa, packing list, placa, etiqueta, data). Também salva tudo em `notas_imagens.md` na pasta da conversa e guarda em cache (chamar de novo com as mesmas imagens e pergunta não custa nada).
**Use sempre que houver mais de ~5 imagens** — `vision_load` carrega as imagens na conversa, que comporta poucas; acima disso as antigas somem e o agente entra em loop recarregando. Depois, compare e conclua pelas notas; não recarregue as imagens.
`caminhos`: lista de arquivos, pastas ou padrões (ex.: `/a0/usr/chats/<id>/anexos/whatsapp/*.jpg`). `pergunta`: o que procurar (ex.: "número do lote, caixa e packing list; placa do caminhão"). `contexto` (opcional): informação que vale para todas (ex.: legendas conhecidas). Até 300 imagens por chamada.
Input schema for tool_args: {"type": "object", "properties": {"caminhos": {"type": "array", "items": {"type": "string"}}, "pergunta": {"type": "string"}, "contexto": {"type": "string"}, "arquivo_notas": {"type": "string"}}, "required": ["caminhos"]}
usage:
~~~json
{
    "thoughts": ["São 48 fotos; vou analisar em lote e comparar pelas notas."],
    "headline": "Analisando as fotos em lote",
    "tool_name": "analisar_imagens",
    "tool_args": {"caminhos": ["/a0/usr/chats/abc/anexos/whatsapp/*.jpg"], "pergunta": "lote, caixa, packing list e placa do caminhão"}
}
~~~
