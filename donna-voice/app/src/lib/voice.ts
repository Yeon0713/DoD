// 음성은 이 파일 뒤에 숨긴다. 화면 코드는 여기 함수만 부른다.
// 지금은 웹(브라우저의 Web Speech API)만 된다. 휴대폰·태블릿 앱용 STT·TTS는 아직 없다 (docs/open-features.md).
import { Platform } from 'react-native';

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

export const voice = {
  sttSupported: () => !!RecognitionCtor,
  ttsSupported: () => !!win?.speechSynthesis,

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

  /** 한 문장을 소리 내어 읽는다. 소리가 꺼져 있으면 읽는 데 걸릴 시간만큼 기다린다(화면 글이 그동안 보인다). */
  speak(text: string, opts: { sound: boolean }): { done: Promise<void>; cancel: () => void } {
    let finish: () => void = () => {};
    let cancelled = false;
    const estimate = Math.max(1400, text.length * 130);
    const done = new Promise<void>((resolve) => {
      let settled = false;
      const end = () => {
        if (settled) return;
        settled = true;
        clearTimeout(guard);
        resolve();
      };
      finish = end;
      // 브라우저가 "다 읽었다"는 신호를 안 주는 경우가 있어서 시간으로도 끝낸다.
      let guard = setTimeout(end, opts.sound && win?.speechSynthesis ? estimate * 2 + 1500 : estimate);
      if (!opts.sound || !win?.speechSynthesis) return;
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
    });
    return {
      done,
      cancel: () => {
        if (cancelled) return;
        cancelled = true;
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
    try {
      win?.speechSynthesis?.cancel();
    } catch {
      /* 무시 */
    }
  },
};
