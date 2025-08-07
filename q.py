import pymysql

def fetch_products():
    connection = pymysql.connect(
        host="shopdaow.beget.tech",
        port=3306,
        user="shopdaow_dance",
        password="Xx9Ht1WzlR&1",
        database="shopdaow_dance",
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM oc_product_description")
            rows = cursor.fetchall()

            for row in rows:
                print(row)  # выводит каждую запись как словарь

            return rows

    except pymysql.MySQLError as e:
        print("Ошибка при выполнении запроса:", e)
        return []

    finally:
        connection.close()

# Вызов функции
fetch_products()
