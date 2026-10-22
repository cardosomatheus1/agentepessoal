"""credential_process for the narration on the agent VM: short-lived credentials of the role agentepessoal-voz (only
Nova 2 Sonic and Polly) from credenciais_meta.py on the host. The container never keeps a key."""
import urllib.request

print(urllib.request.urlopen("http://host.docker.internal:8788/voz", timeout=20).read().decode())
