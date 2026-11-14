"""가게 로고 그림 다루기 (Pillow).

- logo_score: 사진이 로고처럼 생겼는지 본다. 네이버 소식 사진 중에서 로고를 찾을 때 쓴다.
  로고: 테두리가 한 가지 색(바탕)이고, 그림이 차지하는 곳이 작고, 색이 몇 가지뿐이다.
  음식 사진·안내 포스터는 테두리 색이 섞이거나 그림이 화면 대부분을 채워서 걸러진다.
- cut_out: 로고의 바탕을 지우고(투명) 둘레 여백을 잘라 PNG 로 돌려준다. 포스터 위에 바탕 네모 없이 얹으려고 한다.
  바탕이 한 가지 색일 때만 지운다. 사진처럼 바탕이 섞여 있으면 지우지 않는다 (사진에 구멍이 나지 않게).
  지우는 곳은 바깥 바탕과 글자 속 넓은 빈 곳뿐이다. 바탕과 비슷한 크림색 얼굴, 눈의 작은 하이라이트는 남긴다.
"""

import io

from PIL import Image, ImageFilter, UnidentifiedImageError

Image.MAX_IMAGE_PIXELS = 40_000_000  # 아주 큰 그림(압축 폭탄)은 열지 않는다

MAX_SIDE = 800  # 지운 로고의 긴 변 (포스터에 넣기에 넉넉하다)
NEAR = 24  # 바탕색과 이보다 덜 다르면 바탕으로 본다 (0~255, 세 색 중 가장 큰 차이)
SOLID = 96  # 바탕색과 이보다 더 다르면 그림 (지운 바탕 바로 옆에서만 그 사이를 반투명으로. 글자 가장자리가 매끄럽게)
HOLE_MIN = 0.0005  # 그림 안쪽에 갇힌 바탕색 덩어리가 그림 넓이의 이 몫보다 크면 글자 속 빈 곳으로 보고 지운다


class LogoImageError(ValueError):
    pass


def _open(raw: bytes) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise LogoImageError("사진을 읽지 못했어요") from error
    return image.convert("RGBA")


def _diff(color: tuple, bg: tuple) -> int:
    return max(abs(color[0] - bg[0]), abs(color[1] - bg[1]), abs(color[2] - bg[2]))


def _background(image: Image.Image) -> tuple[tuple[int, int, int], float]:
    """(테두리에서 가장 흔한 바탕색, 테두리 중 그 색에 가까운 몫)"""
    rgb = image.convert("RGB")
    w, h = rgb.size
    px = rgb.load()
    step = max(1, max(w, h) // 200)
    border = [px[x, y] for x in range(0, w, step) for y in (0, h - 1)] + [px[x, y] for y in range(0, h, step) for x in (0, w - 1)]
    bg = tuple(sorted(c[i] for c in border)[len(border) // 2] for i in range(3))
    return bg, sum(_diff(c, bg) < NEAR for c in border) / len(border)


def _transparent_already(image: Image.Image) -> bool:
    w, h = image.size
    alpha = image.getchannel("A")
    return sum(alpha.getpixel(p) < 16 for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))) >= 3


def logo_score(raw: bytes) -> float | None:
    """로고처럼 생겼으면 0~1 점수(색이 적을수록 높다), 아니면 None"""
    try:
        image = _open(raw)
    except LogoImageError:
        return None
    image.thumbnail((128, 128))
    if _transparent_already(image):
        return 1.0
    bg, border = _background(image)
    if border < 0.97:  # 테두리가 한 가지 색이 아니다 (사진)
        return None
    rgb = image.convert("RGB")
    w, h = rgb.size
    pixels = [rgb.getpixel((x, y)) for y in range(h) for x in range(w)]
    marks = [(i % w, i // w) for i, c in enumerate(pixels) if _diff(c, bg) >= NEAR]
    if not marks:
        return None
    filled = len(marks) / len(pixels)
    xs, ys = [x for x, _ in marks], [y for _, y in marks]
    box = (max(xs) - min(xs) + 1) * (max(ys) - min(ys) + 1) / (w * h)
    counts = sorted((n for n, _ in rgb.quantize(colors=16).convert("RGB").getcolors(1 << 16)), reverse=True)
    few_colors = sum(counts[:3]) / len(pixels)
    if filled > 0.25 or box > 0.6 or few_colors < 0.85:  # 글·그림이 화면을 채운 안내문, 색이 많은 그림
        return None
    return round(few_colors, 3)


def cut_out(raw: bytes) -> bytes:
    """바탕을 지우고 둘레 여백을 자른 PNG"""
    image = _open(raw)
    image.thumbnail((MAX_SIDE * 2, MAX_SIDE * 2))
    if not _transparent_already(image):
        bg, border = _background(image)
        if border >= 0.9:
            image = _color_to_alpha(image, bg)
    image = _trim(image)
    image.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    image.save(out, "PNG", optimize=True)
    return out.getvalue()


def _background_regions(image: Image.Image, bg: tuple[int, int, int]) -> bytearray:
    """지울 바탕 칸 (1 = 지움). 바탕색에 가까운 칸 덩어리 중 테두리에 닿거나(바깥 바탕) 넓은 것(글자 속 빈 곳, 예: D·O 구멍)만 지운다.
    눈의 하이라이트처럼 작은 흰 곳과 바탕색과 조금 다른 크림색 얼굴은 그대로 둔다."""
    w, h = image.size
    rgb = image.convert("RGB").tobytes()
    near = bytearray(w * h)
    br, bgr, bb = bg
    for i in range(w * h):
        r, g, b = rgb[3 * i], rgb[3 * i + 1], rgb[3 * i + 2]
        if max(abs(r - br), abs(g - bgr), abs(b - bb)) < NEAR:
            near[i] = 1
    remove = bytearray(w * h)
    seen = bytearray(w * h)
    # 한두 가지 색으로 된 납작한 로고(선과 글자)는 갇힌 바탕도 모두 지운다 (예: ㅇ 구멍). 여러 색 그림 로고는 넓은 곳만
    big = 1 if _is_flat(image, near) else max(64, int(w * h * HOLE_MIN))
    for start in range(w * h):
        if not near[start] or seen[start]:
            continue
        stack, region, edge = [start], [], False
        seen[start] = 1
        while stack:
            i = stack.pop()
            region.append(i)
            x, y = i % w, i // w
            if x == 0 or y == 0 or x == w - 1 or y == h - 1:
                edge = True
            for j in (i - 1 if x > 0 else -1, i + 1 if x < w - 1 else -1, i - w if y > 0 else -1, i + w if y < h - 1 else -1):
                if j >= 0 and near[j] and not seen[j]:
                    seen[j] = 1
                    stack.append(j)
        if edge or len(region) >= big:
            for i in region:
                remove[i] = 1
    return remove


def _is_flat(image: Image.Image, near: bytearray) -> bool:
    """그림 칸(바탕과 아주 다른 칸)이 거의 한 가지 색이면 True (선·글자 로고, 예: 갈색 한 색). 얼굴처럼 여러 색 그림이면 False"""
    small = image.convert("RGBA").copy()
    small.thumbnail((200, 200))
    bg, _ = _background(small)
    solid = [c[:3] for c in small.getdata() if c[3] > 200 and _diff(c, bg) >= SOLID]
    if len(solid) < 20:
        return True
    mid = tuple(sorted(c[i] for c in solid)[len(solid) // 2] for i in range(3))
    return sum(_diff(c, mid) < 70 for c in solid) / len(solid) >= 0.85


def _color_to_alpha(image: Image.Image, bg: tuple[int, int, int]) -> Image.Image:
    """지울 바탕(_background_regions)은 투명, 그 바로 옆 1~2칸은 바탕색에서 먼 만큼 반투명(바탕색을 빼낸 색). 나머지는 그대로."""
    w, h = image.size
    remove = _background_regions(image, bg)
    removed = Image.frombytes("L", (w, h), bytes(v * 255 for v in remove))
    near_edge = removed.filter(ImageFilter.MaxFilter(5)).tobytes()  # 지운 곳에서 2칸 안
    data = bytearray(image.tobytes())
    br, bgr, bb = bg
    span = SOLID - NEAR
    for i in range(w * h):
        k = 4 * i
        if remove[i]:
            data[k + 3] = 0
            continue
        if not near_edge[i]:
            continue
        r, g, b, a = data[k], data[k + 1], data[k + 2], data[k + 3]
        d = max(abs(r - br), abs(g - bgr), abs(b - bb))
        if d >= SOLID:
            continue
        alpha = max(d - NEAR, 0) / span
        if alpha <= 0:
            data[k + 3] = 0
            continue
        data[k] = max(0, min(255, round(br + (r - br) / alpha)))
        data[k + 1] = max(0, min(255, round(bgr + (g - bgr) / alpha)))
        data[k + 2] = max(0, min(255, round(bb + (b - bb) / alpha)))
        data[k + 3] = round(a * alpha)
    return Image.frombytes("RGBA", image.size, bytes(data))


def _trim(image: Image.Image) -> Image.Image:
    box = image.getchannel("A").point(lambda a: 255 if a > 16 else 0).getbbox()
    if not box:
        return image
    left, top, right, bottom = box
    pad = round(max(right - left, bottom - top) * 0.03)
    w, h = image.size
    return image.crop((max(0, left - pad), max(0, top - pad), min(w, right + pad), min(h, bottom + pad)))
