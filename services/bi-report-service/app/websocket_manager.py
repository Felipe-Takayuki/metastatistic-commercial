import json
from collections import defaultdict
from typing import Any, Dict, Set
from fastapi import WebSocket


class WebSocketManager:
    """
    Gerencia conexões WebSocket em tempo real para colaboração e sincronização
    de relatórios e dashboards em salas identificadas por `room_id`.
    """

    def __init__(self):
        # room_id -> set of WebSocket instances
        self.active_rooms: Dict[str, Set[WebSocket]] = defaultdict(set)
        # websocket -> metadata {user_id, client_id, room_id, tenant_id}
        self.connection_meta: Dict[WebSocket, Dict[str, Any]] = {}

    async def connect(
        self,
        websocket: WebSocket,
        room_id: str,
        user_id: str = "anonymous",
        tenant_id: str = "default",
    ) -> None:
        await websocket.accept()
        self.active_rooms[room_id].add(websocket)
        self.connection_meta[websocket] = {
            "user_id": user_id,
            "room_id": room_id,
            "tenant_id": tenant_id,
        }

    def disconnect(self, websocket: WebSocket) -> None:
        meta = self.connection_meta.pop(websocket, None)
        if meta:
            room_id = meta.get("room_id")
            if room_id and room_id in self.active_rooms:
                self.active_rooms[room_id].discard(websocket)
                if not self.active_rooms[room_id]:
                    del self.active_rooms[room_id]

    async def broadcast(
        self,
        room_id: str,
        message: dict[str, Any] | str,
        exclude: WebSocket | None = None,
    ) -> None:
        """Envia mensagem serializada em JSON para todos os clientes conectados na sala."""
        payload = message if isinstance(message, str) else json.dumps(message)
        room_members = list(self.active_rooms.get(room_id, []))
        for connection in room_members:
            if connection != exclude:
                try:
                    await connection.send_text(payload)
                except Exception:
                    self.disconnect(connection)

    def get_active_users(self, room_id: str) -> list[str]:
        """Retorna lista de user_ids atualmente conectados na sala."""
        users = []
        for ws in self.active_rooms.get(room_id, []):
            meta = self.connection_meta.get(ws)
            if meta:
                users.append(meta.get("user_id", "anonymous"))
        return sorted(list(set(users)))


ws_manager = WebSocketManager()
