import pymysql
import re
import html

DB_CONFIG = {
    "host": "shopdaow.beget.tech",
    "port": 3306,
    "user": "shopdaow_dance",
    "password": "Xx9Ht1WzlR&1",
    "database": "shopdaow_dance",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}


def clean_html_description(raw_html):
    # Распаковываем HTML-сущности (&lt; и т.п.)
    decoded = html.unescape(raw_html)

    # Заменяем <br>, <br/> и <br /> на перенос строки
    decoded = re.sub(r"<br\s*/?>", "\n", decoded, flags=re.IGNORECASE)

    # Удаляем все остальные теги (<p>, <b> и т.п.)
    cleaned = re.sub(r"<.*?>", "", decoded)

    return cleaned.strip()


def build_image_url(image_path):
    if not image_path:
        return None
    image_path = image_path.strip()
    if image_path.endswith(".jpg"):
        image_path = image_path.replace(".jpg", "-300x300.jpg")
    return f"https://shopdance24.ru/image/cache/{image_path}"


def search_products_by_article(search_term):
    return _search_products(search_term, search_type="article")


def search_products_by_name(search_term):
    return _search_products(search_term, search_type="name")


def _search_products(search_term, search_type="article"):
    connection = pymysql.connect(**DB_CONFIG)
    try:
        with connection.cursor() as cursor:
            query = """
                SELECT p.product_id, p.model, p.sku, p.image, pd.name, pd.description
                FROM oc_product p
                JOIN oc_product_description pd ON p.product_id = pd.product_id
                WHERE (
                    {search_clause}
                ) AND pd.language_id = 1
                LIMIT 1
            """.format(
                search_clause="p.model LIKE %s OR p.sku LIKE %s" if search_type == "article" else "pd.name LIKE %s"
            )

            like_value = f"%{search_term}%"
            if search_type == "article":
                cursor.execute(query, (like_value, like_value))
            else:
                cursor.execute(query, (like_value,))

            result = cursor.fetchone()  # fetchone вместо fetchall

            if result:
                result["description"] = clean_html_description(result.get("description", ""))
                result["image_url"] = build_image_url(result.get("image"))
                return result

            return None

    finally:
        connection.close()

