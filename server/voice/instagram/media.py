"""인스타에 올릴 사진 만들기와 공개 주소.

prepare: 원본 사진(가게 메뉴 사진, 로고)을 인스타 비율의 JPEG 로 바꾼다. 지금은 캔버스 가운데에 놓고 여백을 채우기만 한다.
         문구를 얹는 등 사진 디자인은 아직 정하지 않았다. 정해지면 이 함수만 바꾼다.
public_url: 인스타 서버가 내려받을 공개 HTTPS 주소 (settings.media_host)
  base_url        PUBLIC_MEDIA_BASE_URL/media/<게시물>/<n>.jpg  (main.py 가 MEDIA_DIR 을 /media 로 내보낸다. ngrok 등으로 백엔드를 열어야 한다)
  object_storage  NCP Object Storage 버킷에 public-read 로 올린 주소
  litterbox       litterbox.catbox.moe 에 올린 임시 주소 (1시간 뒤 지워진다). 테스트용이다. 사진이 외부 서비스에 공개로 올라간다
"""

import time
from pathlib import Path

import httpx
from PIL import Image

from app.core.config import settings
from voice.instagram.graph import InstagramError

STATIC_DIR = Path(__file__).resolve().parents[1] / "static"
MEDIA_DIR = Path(__file__).resolve().parents[2] / "db" / "app_data" / "voice_media"
SIZES = {"feed": (1080, 1350), "story": (1080, 1920)}  # 피드 4:5, 스토리 9:16
BACKGROUND = (246, 241, 232)
QUALITY = 90


def source_path(url: str) -> Path:
    """'/static/menus/x.png' → voice/static/menus/x.png. static 밖은 받지 않는다."""
    if not url.startswith("/static/"):
        raise InstagramError(f"올릴 수 없는 사진 주소예요: {url}")
    path = (STATIC_DIR / url.removeprefix("/static/")).resolve()
    if STATIC_DIR.resolve() not in path.parents or not path.exists():
        raise InstagramError(f"사진 파일이 없어요: {url}")
    return path


def made_path(url: str) -> Path:
    """'/media/se_x/poster_1.jpg' → MEDIA_DIR/se_x/poster_1.jpg (이미 만든 그림, story_event). MEDIA_DIR 밖은 받지 않는다."""
    if not url.startswith("/media/"):
        raise InstagramError(f"올릴 수 없는 사진 주소예요: {url}")
    path = (MEDIA_DIR / url.removeprefix("/media/")).resolve()
    if MEDIA_DIR.resolve() not in path.parents or not path.exists():
        raise InstagramError(f"사진 파일이 없어요: {url}")
    return path


def prepare(post_id: str, sources: list[str], kind: str) -> list[Path]:
    """원본 사진들 → MEDIA_DIR/<post_id>/<n>.jpg (kind: feed | story)."""
    size = SIZES[kind]
    out_dir = MEDIA_DIR / post_id
    out_dir.mkdir(parents=True, exist_ok=True)
    made = []
    for number, url in enumerate(sources, 1):
        with Image.open(source_path(url)) as image:
            image = image.convert("RGBA")
            scale = min(size[0] / image.width, size[1] / image.height)
            image = image.resize((round(image.width * scale), round(image.height * scale)), Image.LANCZOS)
            canvas = Image.new("RGB", size, BACKGROUND)
            canvas.paste(image, ((size[0] - image.width) // 2, (size[1] - image.height) // 2), image)
        path = out_dir / f"{number}.jpg"
        canvas.save(path, "JPEG", quality=QUALITY)
        made.append(path)
    return made


def _s3():
    import boto3  # object_storage 모드에서만 필요하다

    return boto3.client("s3", endpoint_url=settings.ncp_object_storage_endpoint, region_name=settings.ncp_object_storage_region,
                        aws_access_key_id=settings.ncloud_access_key, aws_secret_access_key=settings.ncloud_secret_key)


s3_client = _s3  # 테스트에서 가짜를 넣는다

LITTERBOX = "https://litterbox.catbox.moe/resources/internals/api.php"
UPLOAD_TRIES = 3
post = httpx.post  # 테스트에서 가짜를 넣는다


def _litterbox(path: Path) -> str:
    """litterbox 에 1시간짜리로 올리고 그 주소를 돌려준다. 연결이 안 될 때만 다시 시도한다."""
    for attempt in range(1, UPLOAD_TRIES + 1):
        try:
            with path.open("rb") as f:
                response = post(LITTERBOX, data={"reqtype": "fileupload", "time": "1h"},
                                files={"fileToUpload": (path.name, f, "image/jpeg")}, timeout=60)
            break
        except (httpx.ConnectError, httpx.ConnectTimeout) as error:
            if attempt == UPLOAD_TRIES:
                raise InstagramError(f"사진을 올리지 못했어요 ({type(error).__name__})") from error
            time.sleep(1)
        except httpx.HTTPError as error:
            raise InstagramError(f"사진을 올리지 못했어요 ({type(error).__name__})") from error
    url = response.text.strip()
    if response.status_code != 200 or not url.startswith("https://"):
        raise InstagramError(f"사진을 올리지 못했어요 (litterbox {response.status_code})")
    return url


def public_url(path: Path) -> str:
    key = path.relative_to(MEDIA_DIR).as_posix()
    if settings.media_host == "litterbox":
        return _litterbox(path)
    if settings.media_host == "object_storage":
        bucket = settings.ncp_object_storage_bucket
        if not bucket:
            raise InstagramError("NCP_OBJECT_STORAGE_BUCKET 이 비어 있어요")
        key = f"instagram/{key}"
        s3_client().upload_file(str(path), bucket, key, ExtraArgs={"ACL": "public-read", "ContentType": "image/jpeg"})
        return f"{settings.ncp_object_storage_endpoint.rstrip('/')}/{bucket}/{key}"
    base = settings.public_media_base_url.rstrip("/")
    if not base.startswith("https://"):
        raise InstagramError("PUBLIC_MEDIA_BASE_URL 에 인스타가 닿을 수 있는 https 주소를 넣어 주세요")
    return f"{base}/media/{key}"
