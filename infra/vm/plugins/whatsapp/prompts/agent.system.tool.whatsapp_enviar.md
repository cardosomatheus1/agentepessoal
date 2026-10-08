### whatsapp_enviar
Manda para o WhatsApp **do dono desta conversa** (e de mais ninguém) um arquivo, imagem ou recado curto. Use para entregar prints, PDFs, planilhas ou fotos que ele pediu, ou um aviso importante no meio de uma tarefa longa. Respostas normais já chegam sozinhas no WhatsApp quando a conversa é de lá — não repita a resposta por aqui.
`arquivo`: caminho em /a0/usr (até 95 MB). `legenda` (opcional): texto que acompanha o arquivo. `texto` (opcional): recado.
Input schema for tool_args: {"type": "object", "properties": {"arquivo": {"type": "string"}, "legenda": {"type": "string"}, "texto": {"type": "string"}}}
usage:
~~~json
{
    "thoughts": ["Ele pediu o print da campanha; vou mandar no WhatsApp dele."],
    "headline": "Enviando o print no WhatsApp",
    "tool_name": "whatsapp_enviar",
    "tool_args": {"arquivo": "/a0/usr/chats/abc/anexos/campanha.png", "legenda": "Campanha criada, pausada"}
}
~~~
