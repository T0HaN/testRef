import json
import time
import threading
from typing import Dict, List, Any
from fastapi.responses import StreamingResponse

sse_queues: Dict[str, List[List[dict]]] = {}
sse_lock = threading.Lock()


def add_sse_listener(room_id: str) -> List[dict]:
    """Создаёт очередь для нового SSE подключения"""
    queue: List[dict] = []
    with sse_lock:
        if room_id not in sse_queues:
            sse_queues[room_id] = []
        sse_queues[room_id].append(queue)
    return queue


def remove_sse_listener(room_id: str, queue: List[dict]) -> None:
    """Удаляет очередь при отключении"""
    with sse_lock:
        if room_id in sse_queues and queue in sse_queues[room_id]:
            sse_queues[room_id].remove(queue)
            if not sse_queues[room_id]:
                del sse_queues[room_id]


def broadcast_room_event(room_id: str, event_type: str, data: Any) -> None:
    """Рассылает событие всем подключённым в комнате"""
    with sse_lock:
        queues = [q for q in sse_queues.get(room_id, [])]

    for queue in queues:
        try:
            queue.append({'event': event_type, 'data': data})
        except:
            pass  # Игнорируем ошибки закрытых соединений


async def sse_generator(room_id: str, queue: List[dict], filter_event: str = None):
    """Генератор для StreamingResponse"""
    from utils import load_rooms

    try:
        while True:
            # Проверяем существование комнаты
            rooms_data = load_rooms()
            if not any(r['id'] == room_id for r in rooms_data['rooms']):
                break

            if queue:
                event = queue.pop(0)
                # Фильтрация событий (например, игроки видят только броски)
                if filter_event and event['event'] != filter_event:
                    continue
                yield f"event: {event['event']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
            else:
                await asyncio.sleep(0.5)
    finally:
        remove_sse_listener(room_id, queue)