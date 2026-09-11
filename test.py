import psycopg2
from config import settings


def inspect_database():
    query = """
        SELECT 
            t.table_name,
            c.column_name,
            c.data_type,
            c.udt_name,
            c.is_nullable,
            c.column_default
        FROM information_schema.tables t
        JOIN information_schema.columns c 
            ON t.table_name = c.table_name 
            AND t.table_schema = c.table_schema
        WHERE t.table_schema = 'public' 
          AND t.table_type = 'BASE TABLE'
        ORDER BY t.table_name, c.ordinal_position;
    """

    fk_query = """
        SELECT
            tc.table_name, 
            kcu.column_name, 
            ccu.table_name AS foreign_table_name,
            ccu.column_name AS foreign_column_name 
        FROM information_schema.table_constraints AS tc 
        JOIN information_schema.key_column_usage AS kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage AS ccu
            ON ccu.constraint_name = tc.constraint_name
            AND ccu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY' 
          AND tc.table_schema = 'public';
    """

    conn = psycopg2.connect(
        dbname=settings.DB_NAME,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD.get_secret_value() if hasattr(settings.DB_PASSWORD, 'get_secret_value') else str(
            settings.DB_PASSWORD),
        host=settings.DB_HOST,
        port=settings.DB_PORT
    )

    with conn.cursor() as cur:
        # Сбор внешних ключей
        cur.execute(fk_query)
        fks = {}
        for row in cur.fetchall():
            fks[(row[0], row[1])] = f"{row[2]}({row[3]})"

        # Сбор таблиц и колонок
        cur.execute(query)
        rows = cur.fetchall()

    conn.close()

    tables = {}
    for table_name, col_name, data_type, udt_name, is_null, col_default in rows:
        if table_name not in tables:
            tables[table_name] = []

        # Определяем фактический тип (для массивов udt_name начинается с _)
        type_str = data_type
        if data_type == 'ARRAY':
            type_str = f"{udt_name.lstrip('_')}[]"
        elif data_type == 'USER-DEFINED':
            type_str = udt_name

        fk_target = fks.get((table_name, col_name))
        fk_str = f" -> REFERENCES {fk_target}" if fk_target else ""
        null_str = "NOT NULL" if is_null == 'NO' else "NULL"
        def_str = f" DEFAULT {col_default}" if col_default else ""

        tables[table_name].append(f"  • {col_name}: {type_str} {null_str}{def_str}{fk_str}")

    print("=" * 60)
    print(f"База данных: {settings.DB_NAME} (Всего таблиц: {len(tables)})")
    print("=" * 60)
    for t_name, cols in sorted(tables.items()):
        print(f"\n[{t_name}]")
        for col in cols:
            print(col)


if __name__ == "__main__":
    inspect_database()