import { useRouter } from 'expo-router';
import { useState } from 'react';
import { Image, StyleSheet, View } from 'react-native';

import { Surface, Tile } from '@/components/cards';
import { Icon, IconName } from '@/components/Icon';
import { Txt } from '@/components/Txt';
import { Button, LinkButton, StartFrame } from '@/components/ui';
import { useLayout } from '@/lib/layout';
import { useSession } from '@/lib/session';
import { voice } from '@/lib/voice';
import { colors, space } from '@/theme/tokens';

// E-03 마이크를 켜 달라고 부탁하기, E-05 허용하지 않았을 때.
// 휴대폰이 묻는 창(E-04)은 기기가 띄운다.
type Look = { img: any; off: boolean; title: string; desc: string; rows: { icon: IconName; text: string }[]; button: string };

const ASK: Look = {
  img: require('@/assets/donna/b4-0.png'),
  off: false,
  title: '마이크를 켜 주세요',
  desc: '“도나야” 하고 부르면 들어요',
  rows: [
    { icon: 'phone', text: '앱을 켜 둔 동안에만 들어요' },
    { icon: 'power', text: '언제든 끌 수 있어요' },
  ],
  button: '마이크 켜기',
};
const DENIED: Look = {
  img: require('@/assets/donna/b1-2.png'),
  off: true,
  title: '마이크가 꺼져 있어요',
  desc: '켜야 말로 쓸 수 있어요',
  rows: [
    { icon: 'phone', text: '휴대폰 설정에서 켤 수 있어요' },
    { icon: 'mic', text: '켜면 바로 듣기 시작해요' },
  ],
  button: '다시 켜 보기',
};
const UNSUPPORTED: Look = {
  img: require('@/assets/donna/b1-2.png'),
  off: true,
  title: '이 기기는 말을 못 들어요',
  desc: '화면의 말 칩을 눌러서 쓸 수 있어요',
  rows: [
    { icon: 'message', text: '따옴표가 든 칩이 할 수 있는 말이에요' },
    { icon: 'volume', text: '도나의 말은 소리로 들려 드려요' },
  ],
  button: '눌러서 쓰기',
};

export default function MicScreen() {
  const router = useRouter();
  const { mic, setMic } = useSession();
  const { scale } = useLayout();
  const [asking, setAsking] = useState(false);
  const look = mic === 'denied' ? DENIED : mic === 'unsupported' ? UNSUPPORTED : ASK;

  const turnOn = async () => {
    if (mic === 'unsupported') return router.replace('/');
    if (asking) return;
    setAsking(true);
    const result = await voice.requestMic();
    setAsking(false);
    setMic(result);
    if (result === 'granted') router.replace('/');
  };
  const later = () => {
    if (mic === 'unknown') setMic('later');
    router.replace('/');
  };

  return (
    <StartFrame
      bottom={
        <>
          <Button label={look.button} onPress={turnOn} />
          {mic === 'unsupported' ? null : <LinkButton label="나중에 할게요" onPress={later} />}
        </>
      }
    >
      <View style={{ alignItems: 'center', marginBottom: -28 * scale }}>
        <Image source={look.img} style={{ width: 190 * scale, height: 190 * scale }} resizeMode="contain" />
      </View>
      <View style={[styles.badge, { width: 64 * scale, height: 64 * scale, borderRadius: 32 * scale, backgroundColor: look.off ? colors.busySoft : colors.brandSoft }]}>
        <Icon name={look.off ? 'micOff' : 'mic'} size={Math.round(30 * scale)} color={look.off ? 'busy' : 'brand'} />
      </View>
      <Txt variant="display" center style={{ marginTop: space.s8 }}>
        {look.title}
      </Txt>
      <Txt variant="body" color="ink2" center style={{ marginTop: space.s8 }}>
        {look.desc}
      </Txt>
      <View style={{ alignSelf: 'stretch', marginTop: space.s24 }}>
        <Surface pad={space.s4} gap={0}>
          {look.rows.map((r) => (
            <View key={r.text} style={styles.row}>
              <Tile icon={r.icon} tone="brand" soft="brandSoft" />
              <Txt variant="bodyStrong" style={{ flex: 1 }}>
                {r.text}
              </Txt>
            </View>
          ))}
        </Surface>
      </View>
    </StartFrame>
  );
}

const styles = StyleSheet.create({
  badge: { alignItems: 'center', justifyContent: 'center', borderWidth: 4, borderColor: colors.paper },
  row: { flexDirection: 'row', alignItems: 'center', gap: space.s12, padding: space.s12 },
});
