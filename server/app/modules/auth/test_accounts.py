"""테스트 네이버 계정 (임시 네이버 로그인용).

도메인을 받아 네이버 개발자 센터에 앱을 등록하기 전까지, 임시 네이버 로그인 화면에서 이 아이디와 비밀번호로 로그인한다.
네이버 로그인으로는 사장님 가게를 알 수 없어서, 계정에 가게를 정해 두지 않는다. 가입할 때 네이버 지도에서 가게를 찾아 등록하고,
한 번 등록하면 다음 로그인부터 그 가게로 들어온다 (app/data_pipeline/registered_stores.py owners 표).
profile 은 네이버 회원 프로필 조회 API(/v1/nid/me)가 돌려주는 모양과 같다.

진짜 비밀번호가 아니라 시험용 값이다. 진짜 네이버 계정 정보를 여기에 적지 않는다.
"""

TEST_ACCOUNTS: list[dict] = [
    {
        "login_id": "dona_test1",
        "password": "dona1234",
        "scenario": "사장님 1 (김한림)",
        "profile": {
            "id": "TEST_NAVER_ID_0001",
            "nickname": "한림국수사장",
            "name": "김한림",
            "email": "dona_test1@example.com",
            "gender": "F",
            "age": "50-59",
            "birthday": "03-14",
            "birthyear": "1971",
            "mobile": "010-1111-0001",
            "mobile_e164": "+821011110001",
        },
    },
    {
        "login_id": "dona_test2",
        "password": "dona1234",
        "scenario": "사장님 2 (박두리)",
        "profile": {
            "id": "TEST_NAVER_ID_0002",
            "nickname": "두리맥주",
            "name": "박두리",
            "email": "dona_test2@example.com",
            "gender": "M",
            "age": "30-39",
            "birthday": "08-02",
            "birthyear": "1990",
            "mobile": "010-2222-0002",
            "mobile_e164": "+821022220002",
        },
    },
    {
        "login_id": "dona_test3",
        "password": "dona1234",
        "scenario": "사장님 3 (이석사)",
        "profile": {
            "id": "TEST_NAVER_ID_0003",
            "nickname": "석사돈가스",
            "name": "이석사",
            "email": "dona_test3@example.com",
            "gender": "M",
            "age": "40-49",
            "birthday": "11-27",
            "birthyear": "1983",
            "mobile": "010-3333-0003",
            "mobile_e164": "+821033330003",
        },
    },
]


def find_account(login_id: str, password: str) -> dict | None:
    for account in TEST_ACCOUNTS:
        if account["login_id"] == login_id.strip() and account["password"] == password:
            return account
    return None
