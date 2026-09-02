import psycopg2
from psycopg2.extras import RealDictCursor
from config import settings

# Подключаемся с таймаутом, чтобы не висеть, если БД не запущена
CONNECTION_PARAMS = {
    "dbname": settings.DB_NAME,
    "user": settings.DB_USER,
    "password": settings.DB_PASSWORD.get_secret_value(),
    "host": settings.DB_HOST,
    "port": settings.DB_PORT,
    "connect_timeout": 5
}


def migrate_monsters():
    """Создаёт/обновляет таблицу monsters и очищает её."""
    conn = psycopg2.connect(**CONNECTION_PARAMS)
    cur = conn.cursor()

    # Проверяем наличие таблицы
    cur.execute("SELECT to_regclass('public.monsters')")
    exists = cur.fetchone()[0]
    if not exists:
        cur.execute("""
            CREATE TABLE monsters (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                meta TEXT,
                armor_class INTEGER,
                hit_points INTEGER,
                hit_dice TEXT,
                speed TEXT,
                attributes JSONB,
                challenge_rating TEXT,
                traits JSONB,
                actions JSONB,
                legendary_actions JSONB,
                token_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("✅ Таблица monsters создана.")
    else:
        # Добавляем столбец token_path, если его нет
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='monsters' AND column_name='token_path'")
        if not cur.fetchone():
            cur.execute("ALTER TABLE monsters ADD COLUMN token_path TEXT")
            print("✅ Столбец token_path добавлен.")
        else:
            print("ℹ️ Столбец token_path уже существует.")

        # Очищаем таблицу
        cur.execute("TRUNCATE TABLE monsters RESTART IDENTITY")
        print("✅ Таблица monsters очищена.")

    conn.commit()
    cur.close()
    conn.close()
    print("✅ Миграция монстров завершена.")


def main():
    try:
        migrate_monsters()
    except Exception as e:
        print(f"❌ Ошибка миграции: {e}")
        print("   Убедитесь, что PostgreSQL запущен и доступен.")


if __name__ == "__main__":
    main()
