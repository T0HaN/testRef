import base64
import re
import uuid
import boto3
from botocore.client import Config
import psycopg2
from psycopg2.extras import RealDictCursor

import config

def get_s3_client():
    endpoint = getattr(config, "S3_ENDPOINT", "http://127.0.0.1:9000")
    access_key = getattr(config, "S3_ACCESS_KEY", "admin")
    secret_key = getattr(config, "S3_SECRET_KEY", "strong-password")

    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="us-east-1",
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"}
        )
    )

def get_db_connection():
    # Если в config есть готовый DSN / DATABASE_URL
    db_url = getattr(config, "DATABASE_URL", None)
    if db_url:
        return psycopg2.connect(db_url)

    # Либо берем отдельные параметры
    return psycopg2.connect(
        host=getattr(config, "DB_HOST", "127.0.0.1"),
        port=getattr(config, "DB_PORT", 5432),
        database=getattr(config, "DB_NAME", getattr(config, "POSTGRES_DB", "dnd")),
        user=getattr(config, "DB_USER", getattr(config, "POSTGRES_USER", "postgres")),
        password=getattr(config, "DB_PASSWORD", getattr(config, "POSTGRES_PASSWORD", ""))
    )

def main():
    s3 = get_s3_client()
    bucket_name = getattr(config, "S3_BUCKET", "folio-maps")

    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # Проверяем структуру колонок таблицы characters
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'characters';
        """)
        columns = [row["column_name"] for row in cursor.fetchall()]

        # Определяем имя колонки с картинкой (token_image / image / token)
        target_col = None
        for col in ["token_image", "image", "token", "avatar"]:
            if col in columns:
                target_col = col
                break

        if not target_col:
            print(f"❌ Не найдена подходящая колонка изображения среди: {columns}")
            return

        print(f"🔎 Сканируем таблицу characters, колонка: '{target_col}'...")

        cursor.execute(f"SELECT id, name, {target_col} FROM characters WHERE {target_col} LIKE 'data:image%';")
        rows = cursor.fetchall()

        if not rows:
            print("✅ Записей с base64-изображениями не обнаружено.")
            return

        print(f"Найдено записей для конвертации: {len(rows)}")
        migrated_count = 0

        for row in rows:
            char_id = row["id"]
            char_name = row.get("name", "Unknown")
            img_data = row[target_col]

            try:
                header, encoded = img_data.split(",", 1)
                ext_match = re.search(r"data:image/(\w+);base64", header)
                ext = ext_match.group(1) if ext_match else "png"
                if ext == "jpeg":
                    ext = "jpg"

                file_bytes = base64.b64decode(encoded)
                s3_key = f"tokens/char_{char_id}_{uuid.uuid4().hex[:8]}.{ext}"

                s3.put_object(
                    Bucket=bucket_name,
                    Key=s3_key,
                    Body=file_bytes,
                    ContentType=f"image/{ext}"
                )

                new_url = f"/media/{s3_key}"

                cursor.execute(
                    f"UPDATE characters SET {target_col} = %s WHERE id = %s;",
                    (new_url, char_id)
                )

                migrated_count += 1
                print(f"  [ID {char_id}] {char_name} -> {new_url}")

            except Exception as e:
                print(f"  ❌ Ошибка с ID {char_id}: {e}")

        conn.commit()
        print(f"\n🎉 Успешно мигрировано записей: {migrated_count}")

    except Exception as exc:
        conn.rollback()
        print(f"💥 Ошибка транзакции: {exc}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    main()