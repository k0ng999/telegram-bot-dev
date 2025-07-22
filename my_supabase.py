import psycopg2

def get_user(telegram_id):
    try:
        # Подключение к базе данных
        conn = psycopg2.connect(
            user="postgres.zeqerhklxnrwetjfmlhd",
            password="paradoksisquirtik123",
            host="aws-0-eu-north-1.pooler.supabase.com",
            port=6543,
            dbname="postgres"
        )
        cur = conn.cursor()

        # Выполнение запроса на получение пользователя
        query = "SELECT * FROM users WHERE telegram_id = %s;"
        cur.execute(query, (telegram_id,))
        user = cur.fetchone()

        # Закрытие соединения
        cur.close()
        conn.close()

        return user

    except Exception as e:
        print("Ошибка при получении пользователя:", e)
        return None
def add_user(telegram_id: int, name: str, shop_name: str, city: str):
    try:
        conn = psycopg2.connect(
            user="postgres.zeqerhklxnrwetjfmlhd",
            password="paradoksisquirtik123",
            host="aws-0-eu-north-1.pooler.supabase.com",
            port=6543,
            dbname="postgres"
        )
        cur = conn.cursor()

        insert_query = """
            INSERT INTO users (telegram_id, name, shop_name, city)
            VALUES (%s, %s, %s, %s);
        """
        cur.execute(insert_query, (telegram_id, name, shop_name, city))

        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print("Ошибка при добавлении пользователя:", e)