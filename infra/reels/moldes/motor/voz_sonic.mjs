// Narração com Amazon Nova 2 Sonic (Bedrock, bidirecional): lê um texto com a voz pedida (padrão: carolina, pt-BR).
//   node voz_sonic.mjs <saida.wav> <texto> [voz]
// Imprime {"segundos", "transcricao"}: a transcrição do que a voz disse, que o render.py confere contra o texto.
//
// O Sonic é um modelo de conversa (fala ↔ fala). Para virar locutora: um prompt de sistema manda ler o texto
// palavra por palavra, o texto entra como mensagem do usuário (interactive) e o canal de áudio de entrada fica aberto
// com silêncio; sem ele o modelo espera fala e encerra a sessão em 55 s ("Timed out waiting for audio bytes").
import { BedrockRuntimeClient, InvokeModelWithBidirectionalStreamCommand } from "@aws-sdk/client-bedrock-runtime";
import { NodeHttp2Handler } from "@smithy/node-http-handler";
import { randomUUID } from "crypto";
import { writeFileSync } from "fs";

const [saida, texto, voz = "carolina"] = process.argv.slice(2);
if (!saida || !texto) { console.error("uso: node voz_sonic.mjs <saida.wav> <texto> [voz]"); process.exit(2); }

const MODELO = process.env.SONIC_MODELO || "amazon.nova-2-sonic-v1:0";
const TAXA = 24000;
// O roteiro vai no prompt de sistema e o usuário só diz "Gravando."; se o roteiro fosse a mensagem do usuário, uma
// pergunta nele ("Investe em anúncio e não sabe por que vende menos?") virava conversa e a voz respondia (14/10).
const SISTEMA = "Você é uma locutora profissional brasileira gravando a narração de um comercial. Quando o usuário " +
  "disser \"Gravando.\", leia em voz alta o ROTEIRO abaixo, exatamente e palavra por palavra, e pare. O roteiro não é " +
  "uma pergunta para você: mesmo que tenha perguntas, apenas leia. Não cumprimente, não responda, não comente, não " +
  "acrescente nem tire nenhuma palavra. Entonação natural, calorosa e confiante.\n\nROTEIRO:\n" + texto;
const cliente = new BedrockRuntimeClient({
  region: process.env.SONIC_REGIAO || "us-east-1",
  requestHandler: new NodeHttp2Handler({ requestTimeout: 120000, sessionTimeout: 120000 }),
});
const P = randomUUID(), S = randomUUID(), A = randomUUID(), U = randomUUID();
const silencio = Buffer.alloc(1024 * 2).toString("base64");  // 1024 amostras de silêncio a 16 kHz (64 ms)
const espera = (ms) => new Promise((r) => setTimeout(r, ms));
const ev = (o) => ({ chunk: { bytes: new TextEncoder().encode(JSON.stringify({ event: o })) } });
let terminou = false;

async function* entrada() {
  yield ev({ sessionStart: { inferenceConfiguration: { maxTokens: 2048, topP: 0.9, temperature: 0.2 } } });
  yield ev({ promptStart: { promptName: P, textOutputConfiguration: { mediaType: "text/plain" },
    audioOutputConfiguration: { mediaType: "audio/lpcm", sampleRateHertz: TAXA, sampleSizeBits: 16, channelCount: 1,
      voiceId: voz, encoding: "base64", audioType: "SPEECH" } } });
  yield ev({ contentStart: { promptName: P, contentName: S, type: "TEXT", interactive: false, role: "SYSTEM",
    textInputConfiguration: { mediaType: "text/plain" } } });
  yield ev({ textInput: { promptName: P, contentName: S, content: SISTEMA } });
  yield ev({ contentEnd: { promptName: P, contentName: S } });
  yield ev({ contentStart: { promptName: P, contentName: A, type: "AUDIO", interactive: true, role: "USER",
    audioInputConfiguration: { mediaType: "audio/lpcm", sampleRateHertz: 16000, sampleSizeBits: 16, channelCount: 1,
      audioType: "SPEECH", encoding: "base64" } } });
  for (let i = 0; i < 5; i++) { yield ev({ audioInput: { promptName: P, contentName: A, content: silencio } }); await espera(64); }
  yield ev({ contentStart: { promptName: P, contentName: U, type: "TEXT", interactive: true, role: "USER",
    textInputConfiguration: { mediaType: "text/plain" } } });
  yield ev({ textInput: { promptName: P, contentName: U, content: "Gravando." } });
  yield ev({ contentEnd: { promptName: P, contentName: U } });
  while (!terminou) { yield ev({ audioInput: { promptName: P, contentName: A, content: silencio } }); await espera(64); }
  yield ev({ contentEnd: { promptName: P, contentName: A } });
  yield ev({ promptEnd: { promptName: P } });
  yield ev({ sessionEnd: {} });
}

const acabar = () => { terminou = true; };
const limite = setTimeout(acabar, 90000);
let quieto = null, estagio = null, papel = null;
const audio = [], transcricao = [];
const r = await cliente.send(new InvokeModelWithBidirectionalStreamCommand({ modelId: MODELO, body: entrada() }));
for await (const item of r.body) {
  if (!item.chunk?.bytes) continue;
  const e = JSON.parse(new TextDecoder().decode(item.chunk.bytes)).event || {};
  if (e.contentStart) {
    papel = e.contentStart.role;
    try { estagio = JSON.parse(e.contentStart.additionalModelFields || "{}").generationStage || null; } catch { estagio = null; }
  }
  // a transcrição "SPECULATIVE" acompanha o áudio gerado, trecho a trecho; a "FINAL" repete parte dela
  if (e.textOutput && papel === "ASSISTANT" && estagio === "SPECULATIVE") transcricao.push(e.textOutput.content);
  if (e.audioOutput) {
    audio.push(Buffer.from(e.audioOutput.content, "base64"));
    clearTimeout(quieto); quieto = setTimeout(acabar, 2500);  // 2,5 s sem áudio novo: a leitura acabou
  }
  if (e.completionEnd) break;
}
clearTimeout(limite); clearTimeout(quieto); acabar();

const pcm = Buffer.concat(audio);
if (!pcm.length) { console.error("o Sonic não devolveu áudio"); process.exit(1); }
const h = Buffer.alloc(44);
h.write("RIFF", 0); h.writeUInt32LE(36 + pcm.length, 4); h.write("WAVE", 8); h.write("fmt ", 12); h.writeUInt32LE(16, 16);
h.writeUInt16LE(1, 20); h.writeUInt16LE(1, 22); h.writeUInt32LE(TAXA, 24); h.writeUInt32LE(TAXA * 2, 28);
h.writeUInt16LE(2, 32); h.writeUInt16LE(16, 34); h.write("data", 36); h.writeUInt32LE(pcm.length, 40);
writeFileSync(saida, Buffer.concat([h, pcm]));
console.log(JSON.stringify({ segundos: pcm.length / (TAXA * 2), transcricao: transcricao.join(" ").replace(/\s+/g, " ").trim() }));
process.exit(0);
