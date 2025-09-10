# import pymysql

# def fetch_products():
#     connection = pymysql.connect(
#         host="shopdaow.beget.tech",
#         port=3306,
#         user="shopdaow_dance",
#         password="Xx9Ht1WzlR&1",
#         database="shopdaow_dance",
#         charset='utf8mb4',
#         cursorclass=pymysql.cursors.DictCursor
#     )

#     try:
#         with connection.cursor() as cursor:
#             cursor.execute("SELECT * FROM oc_product")
#             rows = cursor.fetchall()

#             for row in rows:
#                 print(row)  # выводит каждую запись как словарь

#             return rows

#     except pymysql.MySQLError as e:
#         print("Ошибка при выполнении запроса:", e)
#         return []

#     finally:
#         connection.close()

# # Вызов функции
# fetch_products()
import psycopg2

conn = psycopg2.connect("""
    host=logeseketub.beget.app
    port=5432
    sslmode=disable
    dbname=Maison_bot
    user=cloud_user
    password=gLD*pxLc9ZCM
    target_session_attrs=read-write
""")

q = conn.cursor()
q.execute('SELECT version()')

print(q.fetchone())

conn.close()