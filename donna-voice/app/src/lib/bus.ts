// 화면 사이에 한 번 알리는 일 (예: 인스타 화면에서 허용하고 돌아왔다). 받는 쪽이 없으면 버린다.
type Handler = (payload: any) => void;
const handlers: Record<string, Set<Handler>> = {};

export const bus = {
  on(name: string, h: Handler) {
    (handlers[name] ??= new Set()).add(h);
    return () => {
      handlers[name]?.delete(h);
    };
  },
  emit(name: string, payload?: unknown) {
    handlers[name]?.forEach((h) => h(payload));
  },
};
