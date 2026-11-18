"""인스타그램 피드·스토리 올리기 (Instagram API with Facebook Login).

  graph.py   Graph API 호출 (컨테이너 만들기, 상태 확인, 게시, 한도)
  media.py   올릴 사진 만들기(JPEG, 비율)와 공개 주소 (공개 base URL 또는 NCP Object Storage)
  posts.py   게시물 초안, 게시 작업, 실제로 올리기, 연결 상태
API 는 voice/api/instagram.py, 브리핑 4단계는 voice/jobs/briefing.py 의 step_instagram.
"""
