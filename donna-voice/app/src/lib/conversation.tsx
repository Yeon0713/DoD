import { usePathname, useRouter } from 'expo-router';
import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { Platform } from 'react-native';

import { api, Home, Notice, Turn } from './api';
import { onDev, sendDev } from './devChannel';
import { useSession } from './session';
import { voice } from './voice';

// 화면 맨 아래 듣기 알약이 보여 주는 상태.
//   standby: "도나야" 하고 부르기를 기다린다 (가게에서 오가는 말은 흘려보낸다)
//   listening: 부른 뒤이거나 대화 중이라, 부르지 않아도 듣는다
export type VoiceState = 'standby' | 'listening' | 'hearing' | 'waiting' | 'preparing' | 'retry_audio' | 'speaking' | 'not_understood' | 'error' | 'mic_off';

type Convo = {
  home: Home | null;
  homeFailed: boolean;
  /** 지금 화면에 띄운 도나의 답. 없으면 홈(준비해 둔 것)을 보여 준다 */
  turn: Turn | null;
  /** 지금 읽고 있는 문장의 짧은 글 */
  caption: string | null;
  /** 지금 읽고 있는 문장이 가리키는 줄 */
  focus: string[];
  /** 이번 답을 얼마나 읽었는지 (0 ~ 1). 손을 못 쓰는 사장님 대신 화면이 이만큼 따라 내려간다 */
  progress: number;
  voiceState: VoiceState;
  /** 받아쓴 말 (듣기 알약에 보인다) */
  heard: string;
  retryAudio: () => void;
  /** 도나 알림 (D-05, D-23). 소리 한 번. 알바생 확인·대답 없음 처리는 한 줄을 읽는다 (아쉬운 리뷰는 turn 으로 연다) */
  notice: Notice | null;
  /** 사장님이 말했을 때 (v0.2.1부터 칩이 없다) */
  send: (text: string, confidence?: number, addressed?: boolean) => void;
  /** 손으로 한 일을 마치고 돌아왔을 때 도나가 한마디 한다 (D-02: 인스타를 연결했어요) */
  announce: (headline: string, text: string) => void;
  reloadHome: () => void;
  /** 읽기를 멈추고 홈으로 */
  reset: () => void;
};

const Ctx = createContext<Convo | null>(null);
const TAB_PATH = { home: '/', week: '/calendar', sales: '/sales', settings: '/settings' } as const;
// 한 단계를 다 말한 뒤 다음 단계로 넘어가기 전 쉬는 시간. 사장님이 끼어들 틈이다.
// 요약 세 줄(sum_*)은 같은 카드에서 줄만 바뀌어서 더 짧게 쉰다 (Figma v0.2.1 H-02 ~ H-04). 2026-11-22: 3초 → 1.2초 → 0.4초, 요약 0.3초
const AUTO_NEXT_MS = 400;
const SUMMARY_NEXT_MS = 300;
/** 도나가 답한 뒤, 또는 "도나야"만 부른 뒤 이만큼은 부르지 않아도 듣는다 (빅스비가 답한 뒤 이어서 듣는 것과 같다). */
const FOLLOW_MS = 8000;

// 부르는 말. 받아쓰기가 "돈아야", "또나야"로 적는 경우까지 받는다.
// 문장 어디에 있어도 부른 말로 본다. 가게 소리가 앞뒤에 붙어 "알람 도나야", "어 도나야 매출 어때"처럼 적히기 때문이다 (2026-11-22).
// 낱말 첫머리에서만 찾는다: "기도 나야", "포도나무"의 '도나'는 부른 말이 아니다. 끝에 '야'가 없는 "도나"는 낱말이 끝날 때만 받는다.
const CALL = /(?<=^|[\s"'“”,.!?~])(?:도\s*나\s*[야아]|돈\s*아\s*야|또\s*나\s*야|도나(?=$|[\s"'“”,.!?~]))[\s"'“”,.!?~]*/g;
/** 말에 "도나야"가 있는지, 그리고 마지막 "도나야" 뒤에 남은 말 (그 앞은 가게 소리로 보고 버린다). */
export function splitCall(text: string): { called: boolean; rest: string } {
  let last: RegExpExecArray | null = null;
  for (const m of text.matchAll(CALL)) last = m as RegExpExecArray;
  if (!last) return { called: false, rest: text.trim() };
  return { called: true, rest: text.slice(last.index + last[0].length).trim() };
}

export function ConversationProvider({ children }: { children: ReactNode }) {
  const session = useSession();
  const router = useRouter();
  const pathname = usePathname();
  const [home, setHome] = useState<Home | null>(null);
  const [homeFailed, setHomeFailed] = useState(false);
  const [turn, setTurn] = useState<Turn | null>(null);
  const [caption, setCaption] = useState<string | null>(null);
  const [focus, setFocus] = useState<string[]>([]);
  const [progress, setProgress] = useState(0);
  const [busy, setBusy] = useState<VoiceState | null>(null);
  const [heard, setHeard] = useState('');
  const [followOpen, setFollowOpen] = useState(false);
  const followTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  /** "도나야"만 부르고 아직 다음 말을 안 했다. 이어지는 한 마디는 도나에게 한 말이다. */
  const justCalled = useRef(false);

  const token = useRef(0);
  const pendingRetry = useRef<((retry: boolean) => void) | null>(null);
  const retryAudio = useCallback(() => pendingRetry.current?.(true), []);
  const cancelPlayback = useCallback(() => {
    pendingRetry.current?.(false);
    pendingRetry.current = null;
    voice.cancelSpeech();
  }, []);
  const autoTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastTurnId = useRef<string | null>(null);
  const soundRef = useRef(session.sound);
  soundRef.current = session.sound;
  const pathRef = useRef(pathname);
  pathRef.current = pathname;

  const micOn = session.mic === 'granted' && voice.sttSupported();
  // 듣는 것은 홈에서만 한다. 이번 주, 매출, 설정은 눈으로 보는 화면이라 마이크가 필요 없다.
  const listenHere = micOn && pathname === '/';
  // 브리핑 중이거나 도나가 물어본 뒤에는 "다음", "응"처럼 부르지 않고 말해도 듣는다.
  // 아쉬운 리뷰 처리를 물었을 때(ask_action)는 영업 중이라 계속 열어 두지 않고, 말한 뒤 8초만 듣는다 (그 뒤엔 "도나야, 진행해").
  const turnOpen = !!turn && ((turn.expects_reply && turn.type !== 'ask_action') || (!!turn.briefing && turn.type !== 'end'));
  const inBriefing = !!turn?.briefing && turn.type !== 'end';
  const open = turnOpen || followOpen;
  const openRef = useRef(open);
  openRef.current = open;
  const voiceState: VoiceState = busy ?? (micOn ? (open ? 'listening' : 'standby') : 'mic_off');

  const closeFollow = useCallback(() => {
    if (followTimer.current) clearTimeout(followTimer.current);
    followTimer.current = null;
    justCalled.current = false;
    setFollowOpen(false);
  }, []);
  const openFollow = useCallback(() => {
    if (followTimer.current) clearTimeout(followTimer.current);
    setFollowOpen(true);
    followTimer.current = setTimeout(() => {
      justCalled.current = false;
      setFollowOpen(false);
    }, FOLLOW_MS);
  }, []);

  const clearAuto = () => {
    if (autoTimer.current) clearTimeout(autoTimer.current);
    autoTimer.current = null;
  };

  const reloadHome = useCallback(() => {
    api
      .home()
      .then((h) => {
        setHome(h);
        setHomeFailed(false);
      })
      .catch(() => setHomeFailed(true));
  }, []);

  /** 한 문장씩 읽는다. 읽는 동안 그 문장의 짧은 글과 가리키는 줄을 화면에 보인다. */
  const speakAll = useCallback(async (say: Turn['say'], my: number) => {
    cancelPlayback();
    voice.pause();
    let ready: Promise<Blob | null> | undefined;
    for (let i = 0; i < say.length; i++) {
      if (token.current !== my) return false;
      const seg = say[i];
      if (seg.caption !== null) setCaption(seg.caption);
      setFocus(seg.focus ?? []);
      setProgress(say.length > 1 ? i / (say.length - 1) : 0);
      let next: Promise<Blob | null> | undefined;
      while (token.current === my) {
        setBusy(soundRef.current && voice.ttsSupported() ? 'preparing' : 'speaking');
        const playback = voice.speak(seg.text, {
          sound: soundRef.current, ready,
          onStart: () => {
            if (token.current !== my) return;
            setBusy('speaking');
            if (say[i + 1]) next ??= voice.prepare(say[i + 1].text);
          },
        });
        if (await playback.done) break;
        if (token.current !== my) return false;
        setCaption(seg.text);
        setBusy('retry_audio');
        voice.resume();
        const retry = await new Promise<boolean>((resolve) => { pendingRetry.current = resolve; });
        if (!retry || token.current !== my) return false;
        pendingRetry.current = null;
        voice.pause();
        ready = undefined;
      }
      ready = next;
    }
    if (token.current !== my) return false;
    setFocus([]);
    setProgress(1); // 다 읽으면 맨 아래의 '할 수 있는 말'이 보이게 한다
    setBusy(null);
    voice.resume();
    return true;
  }, [cancelPlayback]);

  const handle = useCallback(
    async (t: Turn) => {
      const my = ++token.current;
      cancelPlayback();
      lastTurnId.current = t.turn_id;
      // 개발자 모드 탭에 도나가 한 답을 알린다 (그 탭에서는 사장님 화면이 안 보이므로)
      sendDev({ type: 'turn', said: t.owner_said, headline: t.headline, kind: t.type, intent: t.intent, say: t.say.map((x) => x.text) });
      if (t.type === 'ignore') {
        // 도나에게 한 말이 아니다. 화면도 소리도 그대로 둔다.
        setHeard('');
        setBusy(null);
        return;
      }
      if (t.type === 'not_understood') {
        setBusy('not_understood');
        voice.pause(); // 도나의 말이 마이크로 다시 들어오지 않게
        await voice.speak('잘 못 들었어요. 한 번 더 말씀해 주세요.', { sound: soundRef.current }).done;
        if (token.current === my) {
          setHeard('');
          setBusy(null);
          voice.resume();
          openFollow();
        }
        return;
      }
      setHeard('');
      if (t.type === 'stop') {
        closeFollow();
        setTurn(null);
        setCaption(null);
        setFocus([]);
        setBusy(null);
        reloadHome();
        return;
      }
      if (t.type === 'navigate') {
        const path = TAB_PATH[t.tab ?? 'home'];
        if (pathRef.current !== path) router.navigate(path);
        if (await speakAll(t.say, my)) openFollow();
        return;
      }
      if (t.clock_moved) reloadHome(); // 밤 9시로 넘어갔다: 가게 상태 줄(영업 끝)을 다시 불러온다
      setCaption(t.say.find((s) => s.caption)?.caption ?? null);
      setFocus([]);
      setProgress(0);
      setTurn(t);
      if (pathRef.current !== '/') router.navigate('/');
      const finished = await speakAll(t.say, my);
      if (finished) openFollow();
      // 한 단계를 다 말하고 사장님이 가만히 있으면 다음 단계로 넘어간다. 물어본 뒤에는 대답을 기다린다.
      const briefingStep = t.type === 'answer' && !!t.briefing && !t.expects_reply && !/^detail\./.test(t.intent);
      // 시연: 브리핑 끝 화면을 보여 준 뒤 밤 9시 인사과 보고로 넘어간다 (Figma J-12b → K-01)
      const scene = t.next_scene;
      if (finished && scene) {
        clearAuto();
        autoTimer.current = setTimeout(() => {
          if (token.current !== my) return;
          api
            .turn({ event: scene.event, lastTurnId: lastTurnId.current })
            .then((n) => {
              if (token.current === my) void handle(n);
            })
            .catch(() => {});
        }, scene.after_ms);
      }
      if (finished && briefingStep) {
        clearAuto();
        autoTimer.current = setTimeout(() => {
          if (token.current !== my) return;
          api
            .turn({ event: 'auto_next', lastTurnId: lastTurnId.current })
            .then((n) => {
              if (token.current === my) void handle(n);
            })
            .catch(() => {});
        }, t.briefing?.step_key?.startsWith('sum_') ? SUMMARY_NEXT_MS : AUTO_NEXT_MS);
      }
    },
    [reloadHome, router, speakAll, openFollow, closeFollow, cancelPlayback],
  );

  const send = useCallback(
    (text: string, confidence = 1, addressed = false) => {
      const clean = text.trim();
      if (!clean) return;
      clearAuto();
      setNotice(null);
      const my = ++token.current;
      cancelPlayback();
      setHeard(clean);
      setBusy('waiting');
      api
        .turn({ text: clean, confidence, addressed, lastTurnId: lastTurnId.current })
        .then((t) => {
          if (token.current === my) void handle(t);
        })
        .catch(async () => {
          if (token.current !== my) return;
          setBusy('error');
          voice.pause(); // 도나의 말이 마이크로 다시 들어오지 않게
          await voice.speak('지금은 답하기 어려워요. 조금 뒤에 다시 말씀해 주세요.', { sound: soundRef.current }).done;
          if (token.current === my) {
            setHeard('');
            setBusy(null);
            voice.resume();
          }
        });
    },
    [handle, cancelPlayback],
  );

  const reset = useCallback(() => {
    clearAuto();
    token.current++;
    cancelPlayback();
    voice.resume();
    closeFollow();
    setTurn(null);
    setCaption(null);
    setFocus([]);
    setHeard('');
    setBusy(null);
    reloadHome();
  }, [reloadHome, closeFollow, cancelPlayback]);

  /** "도나야"만 불렀을 때. 오전에 처음 부르고 오늘 브리핑을 아직 안 들었으면 서버가 "오늘 브리핑을 시작할까요?"라고 묻는다.
   *  그 밖에는 짧게 "네."라고 대답하고, 이어지는 말을 부르지 않아도 듣는다. */
  const answerCall = useCallback(async () => {
    setHeard('');
    setBusy(null);
    openFollow();
    justCalled.current = true;
    try {
      const offer = await api.turn({ event: 'called', lastTurnId: lastTurnId.current });
      if (offer.type === 'ask') {
        void handle(offer);
        return;
      }
    } catch {
      // 서버에 닿지 않으면 그냥 "네."
    }
    if (!soundRef.current || !voice.ttsSupported()) return;
    voice.pause(); // 도나의 "네"가 마이크로 다시 들어오지 않게
    await voice.speak('네.', { sound: true }).done;
    voice.resume();
  }, [openFollow, handle]);

  /** 마이크로 들은 말 한 마디. 도나를 부른 말이거나 대화 중일 때만 서버로 보낸다. */
  const hear = useCallback(
    (raw: string, confidence: number) => {
      const { called, rest } = splitCall(raw);
      if (!called && !openRef.current) {
        // 손님이나 직원과 나눈 말이다. 화면에 적지도, 서버로 보내지도 않는다.
        sendDev({ type: 'heard', text: raw, result: 'uncalled' });
        setHeard('');
        setBusy((b) => (b === 'hearing' ? null : b));
        return;
      }
      if (called && rest.length < 2) {
        void answerCall();
        return;
      }
      const text = called ? rest : raw;
      // 너무 짧거나 못 알아들은 말은 서버로 보내지 않는다.
      if (text.length < 2 || confidence < 0.5) {
        sendDev({ type: 'heard', text: raw, result: 'too_short' });
        const my = ++token.current;
        setBusy('not_understood');
        setTimeout(() => {
          if (token.current !== my) return;
          setHeard('');
          setBusy(null);
          openFollow();
        }, 2500);
        return;
      }
      const addressed = called || justCalled.current;
      justCalled.current = false;
      sendDev({ type: 'heard', text: raw, result: 'sent' });
      send(text, confidence, addressed);
    },
    [answerCall, openFollow, send],
  );

  useEffect(() => {
    reloadHome();
    return () => {
      clearAuto();
      if (followTimer.current) clearTimeout(followTimer.current);
      token.current++;
      cancelPlayback();
    };
  }, [reloadHome, cancelPlayback]);

  // 마이크를 허용했으면 앱이 켜져 있는 동안 계속 듣는다.
  const hearRef = useRef(hear);
  hearRef.current = hear;
  useEffect(() => {
    if (!listenHere) return;
    voice.start({
      onInterim: (text) => {
        // 부르지 않은 말은 알약에 받아 적지 않는다.
        if (!openRef.current && !splitCall(text).called) return;
        if (openRef.current && followTimer.current) openFollow(); // 말하는 도중에 듣기가 닫히지 않게
        setHeard(text);
        setBusy((b) => (b === null || b === 'hearing' ? 'hearing' : b));
      },
      onFinal: (text, confidence) => hearRef.current(text, confidence),
      onError: (reason) => {
        if (reason === 'denied' || reason === 'unsupported') session.setMic(reason);
      },
    });
    return () => voice.stop();
  }, [listenHere]); // eslint-disable-line react-hooks/exhaustive-deps

  // 개발할 때 말을 대신 넣는 길. 마이크로 들은 말과 같은 길을 탄다 (웹 콘솔에서 __donna.say('도나야, 오늘 일정 브리핑해 줘')).
  useEffect(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined' || !__DEV__) return;
    (window as any).__donna = { say: (text: string) => hearRef.current(text, 0.9), reset };
  }, [reset]);
  // 다른 탭의 개발자 모드(/dev)가 보낸 사장님 말. 위의 __donna.say 와 같은 길이다 (lib/devChannel.ts)
  useEffect(() => onDev((m) => m.type === 'say' && hearRef.current(m.text, 0.9)), []);

  // 도나 알림: 홈에 있고 도나가 조용할 때 몇 초마다 본다 (브리핑 중에는 끝난 뒤로 미룬다. 알림은 한 번 읽으면 다시 오지 않는다).
  //   아쉬운 리뷰(opens_turn): 소리 → turn(event: notice) → 도나가 묻는다 → 8초 동안 "도나야" 없이 대답을 듣는다 (2026-11-18 팀 개선안)
  //   알바생 확인, 대답 없음 처리(say): 소리 → 알림 카드 → 한 줄 읽기
  //   알바생 가입: 소리와 알림 카드만
  const [notice, setNotice] = useState<Notice | null>(null);
  const quiet = busy === null && pathname === '/' && !inBriefing;
  useEffect(() => {
    if (!quiet) return;
    const id = setInterval(() => {
      api
        .notices()
        .then(async ({ notices }) => {
          if (!notices.length) return;
          if (soundRef.current) voice.chime();
          const asking = [...notices].reverse().find((n) => n.opens_turn);
          if (asking) {
            setNotice(null);
            const t = await api.turn({ event: 'notice', noticeId: asking.id, lastTurnId: lastTurnId.current });
            void handle(t);
            return;
          }
          setNotice(notices[notices.length - 1]);
          setTurn(null);
          reloadHome();
          const lines = notices.flatMap((n) => n.say ?? []);
          if (!lines.length) return;
          const my = ++token.current;
          if (await speakAll(lines.map((text) => ({ text, caption: null, focus: [] })), my)) openFollow();
        })
        .catch(() => {});
    }, 4000);
    return () => clearInterval(id);
  }, [quiet, reloadHome, handle, speakAll, openFollow]);

  const announce = useCallback(
    (headline: string, text: string) => {
      const my = ++token.current;
      const t: Turn = {
        turn_id: `local_${Date.now()}`, type: 'answer', intent: 'local.announce', owner_said: null, briefing: null,
        headline, say: [{ text, caption: null, focus: [] }], cards: [], expects_reply: false,
      };
      setNotice(null);
      setCaption(null);
      setFocus([]);
      setTurn(t);
      void speakAll(t.say, my).then((done) => done && openFollow());
    },
    [speakAll, openFollow],
  );

  const value = useMemo<Convo>(
    () => ({ home, homeFailed, turn, caption, focus, progress, voiceState, heard, retryAudio, notice, send, announce, reloadHome, reset }),
    [home, homeFailed, turn, caption, focus, progress, voiceState, heard, retryAudio, notice, send, announce, reloadHome, reset],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useConversation(): Convo {
  const v = useContext(Ctx);
  if (!v) throw new Error('ConversationProvider가 없습니다');
  return v;
}
