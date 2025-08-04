import pymysql

# Параметры подключения
host = "shopdaow.beget.tech"
port = 3306
user = "shopdaow_dance"
password = "Xx9Ht1WzlR&1"
database = "shopdaow_dance"

# Попытка подключения
try:
    connection = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )
    print("✅ Успешно подключено к базе данных!")

    # Пример запроса
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM oc_category")
        result = cursor.fetchall()
        print("Список таблиц:", result)

except pymysql.MySQLError as e:
    print("❌ Ошибка подключения:", e)

finally:
    if 'connection' in locals() and connection.open:
        connection.close()
        print("🔌 Соединение закрыто.")
