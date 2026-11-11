// 개발 화면 맨 위 "매장 시나리오". 매장과 장면을 고르면 그 가게 카드 3~6장만 홈에 보인다 (mocks/personas.ts).
// 아래에 데모 한 주 카드 28장 중 매장 시나리오가 다루지 않는 카드가 있는지 보여 준다.
import { Pressable, View } from "react-native";
import { Text } from "@/components/ui/Text";
import type { TodayCards } from "@/lib/todayCards";
import { COVERED, FLOW_LABEL, PERSONAS, findScene, type Persona, type Scene } from "@/mocks/personas";

function Chip({ children, strong }: { children: string; strong?: boolean }) {
  return (
    <View className={`rounded-full px-2.5 py-1 ${strong ? "bg-brand" : "bg-brand-soft"}`}>
      <Text className={`text-small ${strong ? "font-bold text-brand-ink" : "text-brand"}`}>{children}</Text>
    </View>
  );
}

function PersonaCard({ p, picked, pickedScene, onPick }: { p: Persona; picked: boolean; pickedScene: Scene | null; onPick: (p: Persona, s: Scene) => void }) {
  return (
    <View testID={`dev-persona-${p.id}`} className={`gap-2.5 rounded-card border bg-surface p-4 ${picked ? "border-2 border-brand" : "border-line"}`}>
      <View className="flex-row flex-wrap items-center gap-2">
        <Text className="text-title text-ink">{p.store.name}</Text>
        {p.main ? <Chip strong>발표 시나리오</Chip> : null}
      </View>
      <Text className="text-small text-ink-2">
        {p.store.category}, {p.store.area}
      </Text>
      <Text className="text-label text-ink">{p.who}</Text>
      <View className="flex-row flex-wrap gap-1.5">
        {p.flows.map((f) => (
          <Chip key={f}>{FLOW_LABEL[f]}</Chip>
        ))}
      </View>
      <View className="gap-1.5">
        {p.scenes.map((s) => {
          const on = picked && pickedScene?.id === s.id;
          return (
            <Pressable
              key={s.id}
              testID={`dev-scene-${p.id}-${s.id}`}
              accessibilityRole="button"
              accessibilityState={{ selected: on }}
              onPress={() => onPick(p, s)}
              className={`gap-0.5 rounded-button border px-3 py-2.5 active:bg-brand-soft ${on ? "border-brand bg-brand-soft" : "border-line bg-paper"}`}
            >
              <View className="flex-row items-center justify-between">
                <Text className={`text-body ${on ? "font-bold text-brand" : "font-medium text-ink"}`}>{s.label}</Text>
                <Text className="text-small text-ink-3">할 일 {s.cards.length}개</Text>
              </View>
              <Text className="text-small text-ink-2">{s.note}</Text>
            </Pressable>
          );
        })}
      </View>
      {picked ? (
        <View className="gap-0.5 border-t border-line pt-2">
          <Text className="text-small font-bold text-ink-2">이 가게에서 도나가 보는 것</Text>
          {p.data.map((d) => (
            <Text key={d} className="text-small text-ink-2">
              - {d}
            </Text>
          ))}
          <Text className="text-small text-ink-3">
            직원 {p.store.staff}. 주문 {p.store.channels}
          </Text>
        </View>
      ) : null}
    </View>
  );
}

export function StoreScenarios({
  personaId,
  sceneId,
  allWeek,
  week,
  onPick,
}: {
  personaId: string | null;
  sceneId: string | null;
  allWeek: boolean;
  /** 데모 한 주 카드 전부 (빠진 카드 확인용) */
  week: TodayCards | null;
  onPick: (p: Persona, s: Scene) => void;
}) {
  const ids = new Set(week?.cards.map((c) => c.id) ?? []);
  const missing = week?.cards.filter((c) => !COVERED.includes(c.id)) ?? [];
  const unknown = week ? COVERED.filter((id) => !ids.has(id)) : [];
  return (
    <View className="gap-3">
      {PERSONAS.map((p) => {
        const picked = !allWeek && p.id === personaId;
        return <PersonaCard key={p.id} p={p} picked={picked} pickedScene={picked ? findScene(p, sceneId) : null} onPick={onPick} />;
      })}
      {week ? (
        <Text testID="dev-coverage" className="text-small text-ink-3">
          데모 한 주 카드 {week.cards.length}장 중 {week.cards.length - missing.length}장을 매장 시나리오에서 볼 수 있어요
          {missing.length ? `\n빠진 카드: ${missing.map((c) => c.id).join(", ")}` : ""}
          {unknown.length ? `\n없는 카드 id: ${unknown.join(", ")}` : ""}
        </Text>
      ) : null}
    </View>
  );
}
