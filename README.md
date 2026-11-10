# Static Site Cloner (Gamma & others)

Клонирует опубликованный сайт в статический HTML без JS, с оптимизацией изображений и Lighthouse-бюджетами.

## 🚀 Как использовать

1. Нажми **Use this template** (зелёная кнопка вверху страницы).
2. Создай новый репозиторий.
3. Перейди в **Settings → Pages** и включи GitHub Pages (ветка `master`, папка `/ (root)`).
4. Перейди в **Actions → Clone Site → Run workflow**.
5. Введи параметры:
   * **target_url**: `https://example.gamma.site/`
   * **marker_text**: текст, который должен появиться (например, `Массажист Андрей`)
   * **max_edge**: `1200` (максимальная сторона картинки)
   * **quality**: `78` (качество WebP)
6. Дождись зелёной галочки. Сайт готов по адресу `https://<username>.github.io/<repo>/`.

## ⚠️ Важно

* Используй **published** ссылку (`gamma.site`), а не редакторскую (`gamma.app/docs`), иначе Cloudflare заблокирует GitHub Actions.
* Если сайт закрыт паролем, клонирование не сработает — нужны куки.
