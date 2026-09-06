import base64
import re
import uuid
import boto3
from botocore.client import Config
import psycopg2
from psycopg2.extras import RealDictCursor

from config import settings

def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY.get_secret_value(),
        region_name="us-east-1",
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"}
        )
    )

def get_db_connection():
    return psycopg2.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        dbname=settings.DB_NAME,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD.get_secret_value()
    )

def main():
    s3 = get_s3_client()
    bucket_name = settings.S3_BUCKET

    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # 1. Проверяем наличие колонок таблицы characters
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'characters';
        """)
        columns = [row["column_name"] for row in cursor.fetchall()]

        # 2. Определяем имя поля с картинкой
        target_col = None
        for col in ["token_image", "image", "token", "avatar"]:
            if col in columns:
                target_col = col
                break

        if not target_col:
            print(f"❌ Подходящая колонка изображения не найдена среди: {columns}")
            return

        print(f"🔎 Сканируем таблицу characters (колонка '{target_col}')...")

        cursor.execute(f"SELECT id, name, {target_col} FROM characters WHERE {target_col} LIKE 'data:image%';")
        rows = cursor.fetchall()

        if not rows:
            print("✅ Все токены уже перенесены в MinIO, Base64 не найден.")
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
                print(f"  ❌ Ошибка с персонажем ID {char_id}: {e}")

        conn.commit()
        print(f"\n🎉 Миграция успешно завершена! Обновлено: {migrated_count}")

    except Exception as exc:
        conn.rollback()
        print(f"💥 Ошибка выполнения: {exc}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    main()