// 없는 주소로 들어왔을 때. 오늘 화면으로 돌아가는 길만 둔다.
import { PrimaryButton } from '@/components/ui/parts';
import { CenterMessage, SubPage } from '@/components/ui/sub';
import { replace } from '@/components/ui/nav';

export default function NotFound() {
  return (
    <SubPage onBack={() => replace('/')} footer={<PrimaryButton onPress={() => replace('/')}>오늘 할 일로 가기</PrimaryButton>}>
      <CenterMessage img="question" title={'화면을\n찾지 못했어요'} sub="주소가 바뀌었거나 이미 끝난 일이에요" />
    </SubPage>
  );
}
