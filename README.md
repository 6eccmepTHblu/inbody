# inbody

Парсер PDF-отчётов InBody (DDX Fitness) в JSON. Блоки «История состава тела» и
«Обмен веществ / Суточная норма калорий / Оптимальный вес / До оптимального веса» пропускаются.

```bash
pip install -r requirements.txt
python parse_inbody.py результаты/261016_inbody_result.pdf   # JSON в stdout
python parse_inbody.py результаты -o json                      # все PDF -> json/*.json
python test_parse_inbody.py                                    # проверка
```

Поддерживаются оба макета отчёта: старый (с трендом у карточек → `change`) и новый (с `inbody_score`).
Подписи частей тела в PDF — картинки, сегменты определяются по положению на странице.
