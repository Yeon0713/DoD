// 작은 저장소 하나: 이 기기에 저장하고, 바뀌면 그 값을 쓰는 화면을 다시 그린다.
import { useSyncExternalStore } from "react";
import { storage } from "./storage";

export function createStore<T extends object>(key: string, initial: T) {
  const listeners = new Set<() => void>();
  let cache: T | null = null;

  const read = (): T => {
    if (cache) return cache;
    try {
      cache = { ...initial, ...(JSON.parse(storage.getItem(key) ?? "{}") as Partial<T>) };
    } catch {
      cache = initial;
    }
    return cache;
  };
  const emit = () => listeners.forEach((l) => l());
  const write = (patch: Partial<T>) => {
    cache = { ...read(), ...patch };
    storage.setItem(key, JSON.stringify(cache));
    emit();
  };
  const replace = (next: T) => {
    cache = next;
    storage.setItem(key, JSON.stringify(cache));
    emit();
  };
  const reset = () => {
    cache = initial;
    storage.removeItem(key);
    emit();
  };
  const subscribe = (cb: () => void) => {
    listeners.add(cb);
    return () => {
      listeners.delete(cb);
    };
  };
  // 이름이 useXxx 모양이어야 React Compiler가 훅으로 보고 메모해 두지 않는다 (그냥 use()면 첫 렌더 한 번만 불린다).
  const useValue = (): T => useSyncExternalStore(subscribe, read, read);
  return { read, write, replace, reset, useValue, subscribe };
}
