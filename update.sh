#!/usr/bin/env bash
# Обновление на сервере: /srv/inbody/update.sh
#
# Тело в функции: git pull переписывает этот же файл, а bash дочитывает скрипт
# по ходу выполнения. Функция парсится целиком до первого действия.
main() {
  set -e
  cd "$(dirname "$(readlink -f "$0")")"

  echo "== git pull =="
  git pull --ff-only

  echo "== сборка =="
  docker compose up -d --build

  echo "== проверка =="
  local code=""
  for _ in $(seq 30); do
    code=$(curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:8400/api/data 2>/dev/null || true)
    [ "$code" = "200" ] && break
    sleep 1
  done
  echo "сайт: $code"
  echo "версия: $(git log -1 --format='%h %s')"
  echo "время:  $(date '+%d.%m.%Y %H:%M:%S')"
  [ "$code" = "200" ] || { docker compose logs --tail 50; echo "!!! сайт не отвечает" >&2; return 1; }
}
main "$@"
