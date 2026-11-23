"""인스타에 올릴 사진 만들기와 공개 주소.

prepare: 원본 사진(가게 메뉴 사진, 로고)을 인스타 비율의 JPEG 로 바꾼다. 지금은 캔버스 가운데에 놓고 여백을 채우기만 한다.
         문구를 얹는 등 사진 디자인은 아직 정하지 않았다. 정해지면 이 함수만 바꾼다.
public_url: 인스타 서버가 내려받을 공개 HTTPS 주소 (settings.media_host)
  base_url        PUBLIC_MEDIA_BASE_URL/media/<게시물>/<n>.jpg  (main.py 가 MEDIA_DIR 을 /media 로 내보낸다. ngrok 등으로 백엔드를 열어야 한다)
  ncloud_storage  비공개 Ncloud Storage 버킷에 올리고 발급한 만료형 조회 주소
"""

from pathlib import Path

import boto3
from boto3.exceptions import S3UploadFailedError
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
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


SIGNED_URL_SECONDS = 60 * 60


def _s3():
    access_key = settings.ncloud_storage_access_key
    secret_key = settings.ncloud_storage_secret_key
    if not (access_key or secret_key):
        access_key, secret_key = settings.ncloud_access_key, settings.ncloud_secret_key
    if not (access_key and secret_key):
        raise InstagramError("Ncloud Storage 인증키 두 개를 설정해 주세요")
    endpoint = settings.ncloud_storage_endpoint.rstrip("/")
    if not endpoint.startswith("https://"):
        raise InstagramError("Ncloud Storage에 HTTPS 주소를 설정해 주세요")
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=settings.ncloud_storage_region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


s3_client = _s3  # 테스트에서 가짜를 넣는다


def public_url(path: Path, *, store_id: str) -> str:
    key = path.relative_to(MEDIA_DIR).as_posix()
    if settings.media_host in ("ncloud_storage", "object_storage"):
        bucket = settings.ncloud_storage_bucket
        if not bucket:
            raise InstagramError("NCLOUD_STORAGE_BUCKET 이 비어 있어요")
        key = f"instagram/{store_id}/{key}"
        client = s3_client()
        try:
            client.upload_file(str(path), bucket, key, ExtraArgs={"ContentType": "image/jpeg"})
            return client.generate_presigned_url(
                "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=SIGNED_URL_SECONDS,
            )
        except (BotoCoreError, ClientError, S3UploadFailedError) as error:
            raise InstagramError(f"Ncloud Storage에 사진을 올리지 못했어요 ({type(error).__name__})") from error
    if settings.media_host != "base_url":
        raise InstagramError("MEDIA_HOST에 ncloud_storage 또는 base_url을 설정해 주세요")
    base = settings.public_media_base_url.rstrip("/")
    if not base.startswith("https://"):
        raise InstagramError("PUBLIC_MEDIA_BASE_URL 에 인스타가 닿을 수 있는 https 주소를 넣어 주세요")
    return f"{base}/media/{key}"
