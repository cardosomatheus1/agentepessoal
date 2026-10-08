### whatsapp_guardar_token
Guarda direto no cofre da AWS, **sem você ler o valor**, o que está visível na página da Meta: `campo: "token"` (logo depois de "Gerar token de acesso" na Configuração da API) ou `campo: "app_secret"` (Configurações do app → Básico → "Mostrar" na Chave Secreta). Nunca copie, digite ou repita esses valores.
Input schema for tool_args: {"type": "object", "properties": {"campo": {"type": "string", "enum": ["token", "app_secret"]}}}
usage:
~~~json
{
    "thoughts": ["O token foi gerado na tela; vou guardar sem ler."],
    "headline": "Guardando o token do WhatsApp",
    "tool_name": "whatsapp_guardar_token",
    "tool_args": {}
}
~~~
