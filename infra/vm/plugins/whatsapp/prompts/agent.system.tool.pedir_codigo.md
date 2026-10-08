### pedir_codigo
Pede ao usuário, **pelo WhatsApp dele**, um código de uso único (2FA, SMS, e-mail, app autenticador) e espera até 10 min pela resposta. Use quando um site pedir um código que você não tem como ler. Para senhas use o cofre (`§§secret(NOME)`), não esta ferramenta.
`pergunta`: qual site e que código (ex.: "Código de 6 dígitos que o Facebook mandou por SMS").
Input schema for tool_args: {"type": "object", "properties": {"pergunta": {"type": "string"}}, "required": ["pergunta"]}
usage:
~~~json
{
    "thoughts": ["O Facebook pediu o código de 2FA enviado por SMS."],
    "headline": "Pedindo o código pelo WhatsApp",
    "tool_name": "pedir_codigo",
    "tool_args": {"pergunta": "Código de 6 dígitos que o Facebook mandou por SMS para entrar"}
}
~~~
