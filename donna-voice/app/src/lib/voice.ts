// 음성은 이 파일 뒤에 숨긴다. 화면 코드는 여기 함수만 부른다.
// 듣기(STT, 2026-11-18): 음성 백엔드가 받아 적는다 (Faster-Whisper large-v3-turbo + Silero VAD, server/voice/stt.py).
//   마이크 소리를 16kHz 16비트로 바꿔 WebSocket /v1/stt/stream 으로 계속 보내고, 말이 끝나면 글자를 받는다.
//   백엔드 받아 적기가 꺼져 있거나 연결이 끊기면 예전처럼 브라우저 음성 인식(Web Speech API)으로 듣는다.
//   휴대폰·태블릿 앱(웹이 아닌 것)용 듣기는 아직 없다 (docs/open-features.md).
// 읽기(TTS)는 도나 목소리가 먼저다: 백엔드가 CosyVoice 2(도나 본보기 목소리)로 미리 만들어 둔 소리 (GET /v1/tts).
// 아직 만들지 못한 문장이면 그 문장만 기기 목소리(speechSynthesis)로 읽는다.
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
let startGeneration = 0; // start() 를 다시 부르면 앞의 준비(서버 확인 중)는 버린다
const RESUME_TAIL_MS = 700;
let resumeTimer: ReturnType<typeof setTimeout> | undefined;
let lastCancelAt = 0; // 기기 목소리를 마지막으로 지운 때 (크롬은 지운 직후의 읽기를 버리는 일이 있다)

// ---------- 도나 목소리 (서버에서 만든 소리) ----------
const canPlay = !!win?.fetch && !!win?.Audio && !!win?.URL?.createObjectURL;
const voiceUrls = new Map<string, Promise<string | null>>();
let playing: HTMLAudioElement | null = null;
/** 서버가 답하기를 이만큼까지만 기다린다. 넘으면 그 문장은 기기 목소리로 읽는다. */
const VOICE_WAIT_MS = 1500;

/** 도나 목소리 주소 (blob). 만들어 둔 것이 없으면 null (그 사이 서버가 만들기 시작한다). */
function donnaVoice(text: string): Promise<string | null> {
  if (!canPlay) return Promise.resolve(null);
  let found = voiceUrls.get(text);
  if (!found) {
    found = win
      .fetch(`${BASE}/v1/tts?text=${encodeURIComponent(text)}`)
      .then(async (res: Response) => (res.status === 200 ? win.URL.createObjectURL(await res.blob()) : null))
      .catch(() => null) as Promise<string | null>;
    voiceUrls.set(text, found);
    // 아직 없던 문장은 다음에 다시 묻는다 (서버가 그 사이 만들어 둔다)
    found.then((url) => {
      if (!url) voiceUrls.delete(text);
    });
  }
  return found;
}

// ---------- 백엔드 받아 적기 (Faster-Whisper) ----------
const STT_RATE = 16000;
const SEND_SAMPLES = 1600; // 0.1초씩 보낸다
type ServerStt = { ws: WebSocket; ctx: AudioContext; stream: MediaStream; node: ScriptProcessorNode };
let serverStt: ServerStt | null = null;
const canStream = () => !!(win?.navigator?.mediaDevices?.getUserMedia && win?.WebSocket && (win?.AudioContext ?? win?.webkitAudioContext));

/** 백엔드가 받아 적을 수 있는지 (GET /v1/stt/status). 1.5초 안에 답이 없으면 아니라고 본다. */
async function serverSttReady(): Promise<boolean> {
  if (!canStream()) return false;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 1500);
  try {
    const res = await win.fetch(`${BASE}/v1/stt/status`, { signal: ctrl.signal });
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

async function startServerStt(listener: Listener, onLost: () => void): Promise<boolean> {
  let stream: MediaStream;
  try {
    stream = await win.navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
  } catch {
    listener.onError?.('denied');
    return true; // 마이크를 못 쓰면 브라우저 인식으로도 못 듣는다
  }
  if (!wantListening) {
    stream.getTracks().forEach((t) => t.stop());
    return true;
  }
  const Ctx = win.AudioContext ?? win.webkitAudioContext;
  const ctx: AudioContext = new Ctx();
  const ws: WebSocket = new win.WebSocket(`${BASE.replace(/^http/, 'ws')}/v1/stt/stream`);
  ws.binaryType = 'arraybuffer';
  const source = ctx.createMediaStreamSource(stream);
  const node = ctx.createScriptProcessor(4096, 1, 1);
  let pending: number[] = [];
  node.onaudioprocess = (e: AudioProcessingEvent) => {
    if (paused || ws.readyState !== 1) return;
    const samples = to16k(e.inputBuffer.getChannelData(0), ctx.sampleRate);
    for (let i = 0; i < samples.length; i++) pending.push(samples[i]);
    while (pending.length >= SEND_SAMPLES) {
      ws.send(Int16Array.from(pending.slice(0, SEND_SAMPLES)).buffer);
      pending = pending.slice(SEND_SAMPLES);
    }
  };
  source.connect(node);
  node.connect(ctx.destination); // 연결해야 소리 처리가 돈다 (출력은 0)
  const me: ServerStt = { ws, ctx, stream, node };
  serverStt = me;
  ws.onmessage = (event: MessageEvent) => {
    let m: { type?: string; text?: string } = {};
    try {
      m = JSON.parse(String(event.data));
    } catch {
      return;
    }
    if (paused) return;
    if (m.type === 'speech_start') listener.onInterim('…');
    if (m.type === 'final' && m.text?.trim()) listener.onFinal(m.text.trim(), 0.9);
  };
  ws.onclose = () => {
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
    void s.ctx.close();
    if (s.ws.readyState <= 1) s.ws.close();
  } catch {
    /* 무시 */
  }
}

function stopPlaying() {
  const a = playing;
  playing = null;
  if (a) {
    try {
      a.pause();
    } catch {
      /* 무시 */
    }
  }
}

/** 브라우저 음성 인식(Web Speech API)으로 듣기. 백엔드 받아 적기를 못 쓸 때만. */
function startBrowserStt(listener: Listener) {
  if (!RecognitionCtor || !wantListening) return;
  const r = new RecognitionCtor();
  r.lang = 'ko-KR';
  r.continuous = true;
  r.interimResults = true;
  r.onresult = (e: any) => {
    if (paused) return;
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
  ttsSupported: () => !!win?.speechSynthesis,

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
    if (!(RecognitionCtor || canStream()) || !win?.navigator?.mediaDevices?.getUserMedia) return 'unsupported';
    try {
      const stream: MediaStream = await win.navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((t) => t.stop());
      return 'granted';
    } catch {
      return 'denied';
    }
  },

  /** 앱이 켜져 있는 동안 계속 듣는다. 버튼도 호출어도 없다. 백엔드 받아 적기가 먼저, 안 되면 브라우저 인식. */
  start(listener: Listener) {
    voice.stop();
    wantListening = true;
    paused = false;
    const generation = ++startGeneration;
    void serverSttReady().then(async (ready) => {
      if (!wantListening || generation !== startGeneration) return;
      if (ready && (await startServerStt(listener, () => startBrowserStt(listener)))) return;
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
    if (serverStt?.ws.readyState === 1) serverStt.ws.send(JSON.stringify({ type: 'pause' }));
  },
  /** 다시 듣는다. 기기 목소리는 '다 읽었다' 뒤에도 조금 남아 있어서 RESUME_TAIL_MS 뒤에 듣기 시작한다.
   * (그래도 들어온 도나 목소리는 서버가 흘려듣는다: server/voice/dialog/echo.py) */
  resume() {
    clearTimeout(resumeTimer);
    resumeTimer = setTimeout(() => {
      paused = false;
      if (serverStt?.ws.readyState === 1) serverStt.ws.send(JSON.stringify({ type: 'resume' }));
    }, RESUME_TAIL_MS);
  },

  /** 이번 응답에서 읽을 문장들의 도나 목소리를 미리 받아 둔다 (첫 문장을 읽는 동안 다음 문장을 받는다). */
  prefetch(texts: string[]) {
    texts.forEach((t) => void donnaVoice(t));
  },

  /** 한 문장을 소리 내어 읽는다. 도나 목소리가 있으면 그것으로, 없으면 기기 목소리로.
   * 소리가 꺼져 있으면 읽는 데 걸릴 시간만큼 기다린다(화면 글이 그동안 보인다). */
  speak(text: string, opts: { sound: boolean }): { done: Promise<void>; cancel: () => void } {
    let finish: () => void = () => {};
    let cancelled = false;
    const estimate = Math.max(1400, text.length * 130);
    const done = new Promise<void>((resolve) => {
      let settled = false;
      let guard: ReturnType<typeof setTimeout> | undefined;
      const end = () => {
        if (settled) return;
        settled = true;
        clearTimeout(guard);
        resolve();
      };
      finish = end;
      if (!opts.sound) {
        guard = setTimeout(end, estimate);
        return;
      }

      /** 기기 목소리 (도나 목소리가 없을 때).
       * 2026-11-18: 한국어 기기 목소리는 시작까지 1초 넘게 걸리기도 한다. 예전에는 0.7초 안에 시작하지 않으면 글 길이로 끝을
       * 어림해 일찍 끝냈는데, 그러면 아직 읽는 중에 다시 듣기 시작해 도나 말이 마이크로 들어갔다. 이제는 시작 신호를 3초까지
       * 기다리고, 시작했으면 끝 신호(onend)를 기다린다. 그 사이 기기 목소리 줄에 남은 앞 문장은 비우고 읽는다. */
      const device = () => {
        if (settled || cancelled) return;
        clearTimeout(guard);
        const synth = win?.speechSynthesis;
        guard = setTimeout(end, synth ? estimate * 2 + 4000 : estimate); // 끝 신호를 끝내 안 주는 브라우저 대비
        if (!synth) return;
        const say = () => {
          if (settled || cancelled) return;
          try {
            const u = new win.SpeechSynthesisUtterance(text);
            let started = false;
            u.lang = 'ko-KR';
            u.rate = 1;
            u.onstart = () => {
              started = true;
              clearTimeout(guard);
              guard = setTimeout(end, estimate * 2 + 1500); // 읽기 시작한 뒤로 넉넉히
            };
            u.onend = end;
            u.onerror = end;
            synth.speak(u);
            // 3초가 지나도 시작하지 못하면(이 기기에 목소리가 없음) 글을 읽을 시간만큼만 기다린다
            setTimeout(() => {
              if (started || settled) return;
              clearTimeout(guard);
              guard = setTimeout(end, estimate);
            }, 3000);
          } catch {
            /* 소리 없이 시간만 기다린다 */
          }
        };
        // 크롬은 cancel() 바로 뒤의 speak() 를 소리 없이 버리는 일이 있다. 앞 문장이 남아 있거나 막 지웠으면 조금 뒤에 읽는다
        if (synth.speaking || synth.pending || Date.now() - lastCancelAt < 250) {
          synth.cancel();
          lastCancelAt = Date.now();
          setTimeout(say, 250);
        } else {
          say();
        }
      };

      if (!canPlay) return device();
      let gaveUp = false;
      const wait = setTimeout(() => {
        gaveUp = true;
        device();
      }, VOICE_WAIT_MS);
      donnaVoice(text).then((url) => {
        if (gaveUp || settled || cancelled) return;
        clearTimeout(wait);
        if (!url) return device();
        const a: HTMLAudioElement = new win.Audio(url);
        playing = a;
        let failed = false;
        const fail = () => {
          if (failed) return;
          failed = true;
          if (playing === a) playing = null;
          device();
        };
        a.onended = () => {
          if (playing === a) playing = null;
          end();
        };
        a.onerror = fail;
        guard = setTimeout(end, estimate * 3 + 4000);
        a.play().catch(fail);
      });
    });
    return {
      done,
      cancel: () => {
        if (cancelled) return;
        cancelled = true;
        stopPlaying();
        try {
          win?.speechSynthesis?.cancel();
        } catch {
          /* 무시 */
        }
        finish();
      },
    };
  },

  cancelSpeech() {
    stopPlaying();
    try {
      win?.speechSynthesis?.cancel();
      lastCancelAt = Date.now();
    } catch {
      /* 무시 */
    }
  },
};
