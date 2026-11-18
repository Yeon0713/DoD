// 음성은 이 파일 뒤에 숨긴다. 화면 코드는 여기 함수만 부른다.
// 웹 음성 입력: 서버의 VOICE_STT가 켜져 있으면 네이버 CSR, 꺼져 있으면 Web Speech API.
// 읽기는 서버가 실시간으로 만든 CLOVA 음성을 재생한다.
import { Platform } from 'react-native';

import { BASE } from './api';

type Recognition = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((e: any) => void) | null;
  onend: (() => void) | null;
  onerror: ((e: any) => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
};

const isWeb = Platform.OS === 'web';
const win: any = isWeb && typeof window !== 'undefined' ? window : null;
const RecognitionCtor: (new () => Recognition) | null = win ? win.SpeechRecognition ?? win.webkitSpeechRecognition ?? null : null;

export type MicResult = 'granted' | 'denied' | 'unsupported';

type Listener = {
  /** 말하는 도중의 글자. 화면 맨 아래 듣기 알약에 그대로 보여 준다 */
  onInterim: (text: string) => void;
  /** 말이 끝났을 때의 글자. 이것만 서버로 보낸다 */
  onFinal: (text: string, confidence: number) => void;
  onError?: (reason: string) => void;
};

let recognition: Recognition | null = null;
let wantListening = false;
let paused = false;
// 도나 목소리는 '다 읽었다' 뒤에도 스피커에 조금 남아 있다. 그 꼬리가 마이크로 들어가 사장님 말로 받아 적히지 않게
// RESUME_TAIL_MS 뒤에 다시 듣는다 (2026-11-18 무한 브리핑 반복. 그래도 들어온 말은 서버가 흘려듣는다: server/voice/dialog/echo.py)
const RESUME_TAIL_MS = 700;
let resumeTimer: ReturnType<typeof setTimeout> | undefined;

// ---------- 도나 목소리 (서버에서 만든 소리) ----------
const canPlay = !!win?.fetch && !!win?.Audio && !!win?.URL?.createObjectURL;
let cancelActive: (() => void) | null = null;

async function prepare(text: string): Promise<Blob | null> {
  if (!canPlay) return null;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 6500);
  try {
    const res = await win.fetch(`${BASE}/v1/tts?text=${encodeURIComponent(text)}`, {
      signal: controller.signal, cache: 'no-store',
    });
    return res.status === 200 ? await res.blob() : null;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

const STT_RATE = 16000;
const SEND_SAMPLES = 1600; // 0.1초씩 보낸다
type ServerStt = { ws: WebSocket; ctx: AudioContext; stream: MediaStream; node: ScriptProcessorNode };
let serverStt: ServerStt | null = null;
let startGeneration = 0;
let captureGeneration = 0;
const canStream = () => !!(win?.navigator?.mediaDevices?.getUserMedia && win?.WebSocket && (win?.AudioContext ?? win?.webkitAudioContext));

/** 백엔드가 받아 적을 수 있는지 (GET /v1/stt/status). 1.5초 안에 답이 없으면 아니라고 본다. */
async function serverSttReady(): Promise<boolean> {
  if (!canStream()) return false;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 1500);
  try {
    const res = await win.fetch(`${BASE}/v1/stt/status`, { signal: ctrl.signal, cache: 'no-store' });
    return res.ok && !!(await res.json()).available;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

/** 마이크 소리(보통 48kHz float) → 16kHz 16비트. 구간 평균으로 줄인다. */
function to16k(input: Float32Array, rate: number): Int16Array {
  const ratio = rate / STT_RATE;
  const out = new Int16Array(Math.floor(input.length / ratio));
  for (let i = 0; i < out.length; i++) {
    const from = Math.floor(i * ratio);
    const to = Math.min(input.length, Math.floor((i + 1) * ratio));
    let sum = 0;
    for (let j = from; j < to; j++) sum += input[j];
    const v = Math.max(-1, Math.min(1, sum / Math.max(1, to - from)));
    out[i] = v < 0 ? v * 0x8000 : v * 0x7fff;
  }
  return out;
}

async function startServerStt(listener: Listener, session: number, onLost: () => void): Promise<boolean> {
  let stream: MediaStream;
  try {
    stream = await win.navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
  } catch {
    if (session === startGeneration) listener.onError?.('denied');
    return true; // 마이크를 못 쓰면 브라우저 인식으로도 못 듣는다
  }
  if (session !== startGeneration || !wantListening) {
    stream.getTracks().forEach((t) => t.stop());
    return true;
  }
  const Ctx = win.AudioContext ?? win.webkitAudioContext;
  let context: AudioContext | undefined;
  let socket: WebSocket | undefined;
  let node: ScriptProcessorNode;
  try {
    const ctx: AudioContext = new Ctx();
    context = ctx;
    const source = ctx.createMediaStreamSource(stream);
    node = ctx.createScriptProcessor(4096, 1, 1);
    source.connect(node);
    node.connect(ctx.destination); // 출력 버퍼는 무음
    socket = new WebSocket(`${BASE.replace(/^http/, 'ws')}/v1/stt/stream`);
  } catch {
    stream.getTracks().forEach((t) => t.stop());
    void context?.close().catch(() => {});
    return false;
  }
  const ctx = context;
  const ws = socket;
  ws.binaryType = 'arraybuffer';
  let pending: number[] = [];
  let frameGeneration = captureGeneration;
  node.onaudioprocess = (e: AudioProcessingEvent) => {
    if (frameGeneration !== captureGeneration) {
      pending = [];
      frameGeneration = captureGeneration;
    }
    if (paused || ws.readyState !== 1) return;
    const samples = to16k(e.inputBuffer.getChannelData(0), ctx.sampleRate);
    for (let i = 0; i < samples.length; i++) pending.push(samples[i]);
    while (pending.length >= SEND_SAMPLES) {
      ws.send(Int16Array.from(pending.slice(0, SEND_SAMPLES)).buffer);
      pending = pending.slice(SEND_SAMPLES);
    }
  };
  const me: ServerStt = { ws, ctx, stream, node };
  serverStt = me;
  const readyTimer = setTimeout(() => { if (serverStt === me) ws.close(); }, 5000);
  ws.onopen = () => {
    ws.send(JSON.stringify({ type: paused ? 'pause' : 'resume', generation: captureGeneration }));
  };
  ws.onmessage = (event: MessageEvent) => {
    let m: { type?: string; text?: string; generation?: number } = {};
    try {
      m = JSON.parse(String(event.data));
    } catch {
      return;
    }
    if (m.type === 'ready') { clearTimeout(readyTimer); return; }
    if (paused || session !== startGeneration || m.generation !== captureGeneration) return;
    if (m.type === 'speech_start') listener.onInterim('…');
    if (m.type === 'final' && m.text?.trim()) listener.onFinal(m.text.trim(), 0.9);
  };
  ws.onclose = () => {
    clearTimeout(readyTimer);
    if (serverStt === me) {
      closeServerStt();
      if (wantListening) onLost(); // 백엔드가 꺼졌다: 브라우저 인식으로 이어서 듣는다
    }
  };
  return true;
}

function closeServerStt() {
  const s = serverStt;
  serverStt = null;
  if (!s) return;
  try {
    s.node.disconnect();
    s.stream.getTracks().forEach((t) => t.stop());
    void s.ctx.close().catch(() => {});
    if (s.ws.readyState <= 1) s.ws.close();
  } catch {
    /* 무시 */
  }
}

function startBrowserStt(listener: Listener) {
  if (!wantListening) return;
  if (!RecognitionCtor) { listener.onError?.('unsupported'); return; }
  const r = new RecognitionCtor();
  r.lang = 'ko-KR';
  r.continuous = true;
  r.interimResults = true;
  r.onresult = (e: any) => {
    if (paused || r !== recognition) return;
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const res = e.results[i];
      const text = String(res[0]?.transcript ?? '').trim();
      if (!text) continue;
      if (res.isFinal) listener.onFinal(text, Number(res[0]?.confidence ?? 0.9) || 0.9);
      else listener.onInterim(text);
    }
  };
  r.onerror = (e: any) => {
    if (e?.error === 'not-allowed' || e?.error === 'service-not-allowed') {
      wantListening = false;
      listener.onError?.('denied');
    }
  };
  // 브라우저는 조용하면 듣기를 스스로 끝낸다. 계속 듣고 있어야 하므로 다시 켠다.
  r.onend = () => {
    if (wantListening && recognition === r) {
      try {
        r.start();
      } catch {
        /* 이미 켜지는 중 */
      }
    }
  };
  recognition = r;
  try {
    r.start();
  } catch {
    listener.onError?.('start_failed');
  }
}

export const voice = {
  sttSupported: () => !!RecognitionCtor || canStream(),
  ttsSupported: () => canPlay,

  /** 도나 알림 소리 한 번 (D-05, D-23). 말은 하지 않는다. */
  chime() {
    const Ctx = win?.AudioContext ?? win?.webkitAudioContext;
    if (!Ctx) return;
    try {
      const ctx = new Ctx();
      [880, 1175].forEach((freq: number, i: number) => {
        const o = ctx.createOscillator();
        const g = ctx.createGain();
        o.frequency.value = freq;
        g.gain.setValueAtTime(0.0001, ctx.currentTime + i * 0.14);
        g.gain.exponentialRampToValueAtTime(0.15, ctx.currentTime + i * 0.14 + 0.02);
        g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + i * 0.14 + 0.3);
        o.connect(g).connect(ctx.destination);
        o.start(ctx.currentTime + i * 0.14);
        o.stop(ctx.currentTime + i * 0.14 + 0.32);
      });
    } catch {
      // 소리를 못 내도 화면의 알림은 그대로 보인다
    }
  },

  /** 마이크를 써도 되는지 묻는다 (E-03 → E-04). */
  async requestMic(): Promise<MicResult> {
    if (!(RecognitionCtor || (await serverSttReady())) || !win?.navigator?.mediaDevices?.getUserMedia) return 'unsupported';
    try {
      const stream: MediaStream = await win.navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((t) => t.stop());
      return 'granted';
    } catch {
      return 'denied';
    }
  },

  /** 앱이 켜져 있는 동안 계속 듣는다. 버튼도 호출어도 없다. */
  start(listener: Listener) {
    voice.stop();
    wantListening = true;
    paused = false;
    const generation = ++startGeneration;
    void serverSttReady().then(async (ready) => {
      if (!wantListening || generation !== startGeneration) return;
      if (ready && (await startServerStt(listener, generation, () => startBrowserStt(listener)))) return;
      if (generation !== startGeneration) return;
      startBrowserStt(listener);
    });
  },

  stop() {
    wantListening = false;
    startGeneration++;
    closeServerStt();
    const r = recognition;
    recognition = null;
    try {
      r?.abort();
    } catch {
      /* 무시 */
    }
  },

  /** 도나가 읽는 동안에는 듣지 않는다. 스피커 소리가 마이크로 다시 들어오기 때문이다. */
  pause() {
    clearTimeout(resumeTimer);
    paused = true;
    captureGeneration++;
    if (serverStt?.ws.readyState === 1) serverStt.ws.send(JSON.stringify({ type: 'pause', generation: captureGeneration }));
  },
  resume() {
    clearTimeout(resumeTimer);
    resumeTimer = setTimeout(() => {
      paused = false;
      if (serverStt?.ws.readyState === 1) serverStt.ws.send(JSON.stringify({ type: 'resume', generation: captureGeneration }));
    }, RESUME_TAIL_MS);
  },

  prepare,

  speak(text: string, opts: { sound: boolean; ready?: Promise<Blob | null>; onStart?: () => void }) {
    cancelActive?.();
    let finish: (ok: boolean) => void;
    const done = new Promise<boolean>((resolve) => { finish = resolve; });
    let ended = false;
    let audio: HTMLAudioElement | undefined;
    let url: string | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const end = (ok: boolean) => {
      if (ended) return;
      ended = true;
      clearTimeout(timer);
      audio?.pause();
      if (url) win.URL.revokeObjectURL(url);
      cancelActive = null;
      finish(ok);
    };
    const cancel = () => end(false);
    cancelActive = cancel;
    if (!opts.sound || !isWeb) {
      timer = setTimeout(() => end(true), Math.max(1400, text.length * 130));
    } else {
      (opts.ready ?? prepare(text)).then(async (blob) => {
        if (ended) return;
        if (!blob) return end(false);
        url = win.URL.createObjectURL(blob);
        const player: HTMLAudioElement = new win.Audio(url);
        audio = player;
        player.onended = () => end(true);
        player.onerror = () => end(false);
        player.onplaying = () => { if (!ended) opts.onStart?.(); };
        timer = setTimeout(() => end(false), Math.max(15000, text.length * 700));
        await player.play();
      }).catch(() => end(false));
    }
    return { done, cancel };
  },

  cancelSpeech() {
    cancelActive?.();
  },
};
