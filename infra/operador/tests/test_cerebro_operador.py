"""The operator's Stop hook (.claude/hooks/cerebro_operador.py): only his words and the operator's report leave, only
what is new since the last Stop, never the backlog, secrets masked."""

import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "cerebro_operador_teste", Path(__file__).resolve().parents[3] / ".claude" / "hooks" / "cerebro_operador.py")
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)


def _l(**d):
    return json.dumps(d, ensure_ascii=False)


def _user(uuid, texto, kind="human"):
    return _l(type="user", uuid=uuid, origin={"kind": kind}, message={"role": "user", "content": texto})


def _assist(uuid, texto):
    return _l(type="assistant", uuid=uuid, message={"role": "assistant", "content": [{"type": "text", "text": texto}]})


LINHAS = [
    _user("u1", "pedido antigo"), _assist("a1", "feito o antigo"),
    _user("u2", "Sobre o vídeo, quero que ele seja a postagem de amanhã <system-reminder>lixo</system-reminder>"),
    _l(type="assistant", uuid="a2", message={"content": [{"type": "tool_use", "name": "Bash"}]}),
    _l(type="user", uuid="t2", message={"content": [{"type": "tool_result", "content": "saída"}]}),
    _user("n2", "<task-notification>vídeo pronto</task-notification>", kind="task-notification"),
    _assist("a3", "Agendei o vídeo para 21/10 às 11:45 e andei os outros posts um dia."),
]


def test_primeira_vez_so_o_turno_atual():
    dele, relato, fim = h.novidades(LINHAS, "")
    assert dele == ["Sobre o vídeo, quero que ele seja a postagem de amanhã"], dele
    assert "Agendei o vídeo" in relato and "feito o antigo" not in relato
    assert fim == "a3"


def test_so_o_que_veio_depois_do_ultimo_enviado():
    dele, relato, fim = h.novidades(LINHAS + [_assist("a4", "Conferi o Crítico.")], "a3")
    assert dele == [] and relato == "Conferi o Crítico." and fim == "a4"


def test_notificacao_e_resultado_de_ferramenta_nao_sao_falas_dele():
    dele, _r, _f = h.novidades(LINHAS, "a1")
    assert all("task-notification" not in d and "saída" not in d for d in dele)


def test_segredo_mascarado():
    dele, relato, _ = h.novidades([_user("x", "a chave é sk-abcdefghijklmnopqrstuvwxyz123"),
                                   _assist("y", "token ghp_abcdefghijklmnopqrstuvwxyz0123")], "")
    assert "sk-abc" not in dele[0] and "ghp_" not in relato


def test_desligado_nao_envia():
    import os
    enviados = []
    h.enviar = lambda payload, sessao: enviados.append(payload)
    os.environ["CEREBRO_OPERADOR"] = "0"
    h.main()
    os.environ.pop("CEREBRO_OPERADOR")
    assert enviados == []


def test_inicio_extrai_so_o_bloco_do_cerebro():
    spec2 = importlib.util.spec_from_file_location(
        "cerebro_inicio_teste", Path(__file__).resolve().parents[3] / ".claude" / "hooks" / "cerebro_inicio.py")
    i = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(i)
    saida = "lixo do ssm\n<<<CEREBRO>>>\n# Segundo Cérebro\n- #39 [preferencia] marketing.video-audio-antes: x\n<<<FIM-CEREBRO>>>\nfim"
    assert i.extrair(saida).startswith("# Segundo Cérebro") and "lixo" not in i.extrair(saida)
    assert i.extrair("falhou a conexão") == ""
    assert "<<<CEREBRO>>>" not in i.SCRIPT and "<<<FIM-CEREBRO>>>" not in i.SCRIPT, "um erro citando o script não vira bloco"


if __name__ == "__main__":
    for nome, f in sorted(globals().items()):
        if nome.startswith("test_"):
            f()
            print("✓", nome)
