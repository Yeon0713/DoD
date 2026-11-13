"""가게 지역 날씨를 받아 weather.json 으로 저장한다 (server 폴더에서 실행, server/.env 의 KMA_API_KEY 필요).

    python -m app.weather s101                  # 가게 s101 좌표로 받아 weather.json 에 저장
    python -m app.weather s101 -o out.json
    python -m app.weather s101 --save           # 그 가게 DB(store_weather_daily)에도 저장
"""

import argparse
import json
import sys
from pathlib import Path

from app.data_pipeline import read_store_db
from app.weather import store_weather
from app.weather.client import KmaError
from app.weather.service import get_weather


def main() -> int:
    parser = argparse.ArgumentParser(description="가게 지역 기상청 날씨 받기")
    parser.add_argument("store_id", help="가게 id (예: s101)")
    parser.add_argument("-o", "--output", default="weather.json")
    parser.add_argument("--past-days", type=int, default=store_weather.PAST_DAYS)
    parser.add_argument("--save", action="store_true", help="가게 DB 에도 저장")
    args = parser.parse_args()

    if args.store_id not in read_store_db.list_store_ids():
        print(f"가게 {args.store_id} 가 없어요", file=sys.stderr)
        return 1
    store = read_store_db.read_store(args.store_id)
    try:
        result = get_weather(store["lat"], store["lng"], past_days=args.past_days)
    except KmaError as error:
        print(f"기상청 날씨를 받지 못했어요: {error}", file=sys.stderr)
        return 1
    Path(args.output).write_text(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
    meta = result.metadata
    print(f"{store['name']} ({store['address']}) → 격자 {result.location.nx},{result.location.ny}")
    if result.location.station:
        s = result.location.station
        print(f"관측소 {s.station_id} {s.name or ''} ({s.distance_km}km)")
    print(f"관측 {sum(o.temperature_avg is not None for o in result.observations)}/{len(result.observations)}일, "
          f"시간별 예보 {len(result.forecasts.hourly)}개, 일별 예보 {len(result.forecasts.daily)}일 (마지막 {meta.forecast_end_at})")
    for o in result.observations[-3:]:
        print(f"  {o.date} 관측  {o.sky or '-'} / {o.precipitation_type or '-'}  {o.temperature_min}~{o.temperature_max}℃  {o.precipitation_mm}mm")
    for f in result.forecasts.daily:
        print(f"  {f.date} 예보  {f.sky or '-'} / {f.precipitation_type or '-'}  {f.temperature_min}~{f.temperature_max}℃  강수확률 {f.precipitation_probability_max}%")
    for error in meta.errors:
        print(f"  실패 {error.section}: {error.code} {error.message}")
    print(f"저장: {args.output}")
    if args.save:
        if not store_weather.registered_stores.is_mock_store(args.store_id) and int(args.store_id[1:]) < store_weather.registered_stores.FIRST_NUMBER:
            print("목업 가게 파일은 고치지 않아요 (--save 건너뜀)")
        else:
            print(store_weather.save(args.store_id, result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
