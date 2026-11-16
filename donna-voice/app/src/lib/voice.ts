// 음성은 이 파일 뒤에 숨긴다. 화면 코드는 여기 함수만 부른다.
// 듣기(STT)는 웹(브라우저의 Web Speech API)만 된다. 휴대폰·태블릿 앱용 STT는 아직 없다 (docs/open-features.md).
// 읽기(TTS)는 도나 목소리가 먼저다: 백엔드가 Qwen3-TTS(Sohee + 도나 목소리 설계)로 미리 만들어 둔 소리 (GET /v1/tts).
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

export const voice = {
  sttSupported: () => !!RecognitionCtor,
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
    if (!RecognitionCtor || !win?.navigator?.mediaDevices?.getUserMedia) return 'unsupported';
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
    if (!RecognitionCtor) return;
    voice.stop();
    wantListening = true;
    paused = false;
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
  },

  stop() {
    wantListening = false;
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
    paused = true;
  },
  resume() {
    paused = false;
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

      /** 기기 목소리 (도나 목소리가 없을 때) */
      const device = () => {
        if (settled || cancelled) return;
        clearTimeout(guard);
        // 브라우저가 "다 읽었다"는 신호를 안 주는 경우가 있어서 시간으로도 끝낸다.
        guard = setTimeout(end, win?.speechSynthesis ? estimate * 2 + 1500 : estimate);
        if (!win?.speechSynthesis) return;
        try {
          const u = new win.SpeechSynthesisUtterance(text);
          let started = false;
          u.lang = 'ko-KR';
          u.rate = 1;
          u.onstart = () => {
            started = true;
          };
          u.onend = end;
          u.onerror = end;
          win.speechSynthesis.speak(u);
          // 읽기를 시작하지 못하는 브라우저에서는(목소리가 없는 경우) 글을 읽을 시간만큼만 기다린다.
          setTimeout(() => {
            if (started || settled) return;
            clearTimeout(guard);
            guard = setTimeout(end, Math.max(0, estimate - 700));
          }, 700);
        } catch {
          /* 소리 없이 시간만 기다린다 */
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
    } catch {
      /* 무시 */
    }
  },
};
