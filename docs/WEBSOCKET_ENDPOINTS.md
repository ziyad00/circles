### Circles WebSocket API

This document describes all WebSocket endpoints exposed by the backend, how to authenticate, what messages they accept, and what events the server emits.

WebSockets are served behind the ALB and hosted by our FastAPI app on ECS/Fargate. No subscription handshake is required after connecting; the token in the URL authenticates the socket.

---

## Common

- Base URL (prod): `ws://circles-alb-<...>.us-east-1.elb.amazonaws.com`
- Authentication: pass a JWT access token as a query parameter: `?token=<JWT>`
- Close codes:
  - `4401` Unauthorized (token missing/invalid)
  - `4403` Forbidden (not allowed for this resource)
  - `1000` Normal close
- Keepalive:
  - Client may send `{ "type": "ping" }` at 15–30s intervals
  - Server responds with `{ "type": "pong", "timestamp": <ISO8601> }`
  - ALB idle timeout applies; keep pings running on the client

---

## 1) Direct Messages (DM) – Thread Socket

Path: `/ws/dms/{thread_id}`

### Purpose

Realtime, per-thread DM channel between exactly two participants.

### Authorization

- JWT is required (`?token=...`).
- The user must be a participant in the thread and the thread must have status `accepted`.
- Failing authorization closes the socket with code `4403`.

### Server messages on connect

- `connection_established`:
  ```json
  {
    "type": "connection_established",
    "thread_id": 2,
    "user_id": 8,
    "timestamp": "2025-..."
  }
  ```
- `thread_info` (participants and presence):
  ```json
  {
    "type": "thread_info",
    "participants": [ {"id": 8, "name": "...", "avatar_url": "..."}, {"id": 6, ...} ],
    "other_user_online": false,
    "timestamp": "2025-..."
  }
  ```

### Client → Server messages

- `ping`

  - Example: `{ "type": "ping" }`
  - Server replies: `{ "type": "pong", "timestamp": "..." }`

- `typing`

  - Example: `{ "type": "typing", "typing": true }`
  - Broadcasts typing state to the other participant and updates a short server-side `typing_until` window.

- `message`

  - Example: `{ "type": "message", "text": "Hello there" }`
  - Persists a new `DMMessage` (text only via WS). Server broadcasts:
    ```json
    {
      "type": "message",
      "message": {
        "id": 35,
        "thread_id": 2,
        "sender_id": 8,
        "text": "Hello there",
        "created_at": "2025-...",
        "sender_info": { "id": 8, "name": "...", "avatar_url": null }
      },
      "timestamp": "2025-..."
    }
    ```

- `mark_read`

  - Example: `{ "type": "mark_read" }`
  - Updates `DMParticipantState.last_read_at` and broadcasts:
    ```json
    {
      "type": "read_receipt",
      "user_id": 8,
      "last_read_at": "2025-...",
      "timestamp": "2025-..."
    }
    ```

- `reaction` (ephemeral in WS path)
  - Example: `{ "type": "reaction", "message_id": 35, "reaction": "❤️" }`
  - Broadcasts `{ "type": "reaction", "message_id": 35, "user_id": <me>, "reaction": "❤️" }`
  - Note: Persistent reactions are available via the HTTP endpoints; WS path only broadcasts.

### Server → Client events

- `presence`: `{ "type": "presence", "user_id": <id>, "online": true|false, "timestamp": "..." }`
- `typing`: `{ "type": "typing", "user_id": <id>, "typing": true|false, "timestamp": "..." }`
- `message`: see above
- `reaction`: see above
- `read_receipt`: see above
- `pong`: heartbeat response

---

## 2) User-Wide Socket (Notifications)

Path: `/ws/user/{user_id}`

### Purpose

Single socket per user for cross-thread notifications: inbox updates, new DM requests/messages, reaction updates, etc.

### Authorization

- JWT required and must match the `{user_id}` in the path; otherwise close with `4401`.

### Client → Server messages

- `ping`: `{ "type": "ping" }` → `{ "type": "pong", "timestamp": "..." }`

### Server → Client events (examples)

- `connection_established`: `{ "type": "connection_established", "user_id": 8, "timestamp": "..." }`
- `dm_notification` variants (payload shape depends on the originating action):
  - New message: `{ "type": "dm_message", "thread_id": 2, "message_id": 35, ... }`
  - Reply: `{ "type": "dm_reply", "thread_id": 2, "message_id": 36, "reply_to_id": 35, ... }`
  - Media: `{ "type": "dm_media", "thread_id": 2, "message_id": 37, ... }`
  - DM request: `{ "type": "dm_request", "thread_id": 10, "from_user": 6, ... }`
  - Reactions: `{ "type": "reaction", "message_id": 35, "emoji": "❤️", "from_user": 6, ... }`

> Note: These are emitted by server-side business logic (HTTP DM endpoints) via the internal WebSocket service.

---

## 3) Place Chat Socket (Ephemeral, Check‑in Gated)

Path: `/ws/places/{place_id}/chat`

### Purpose

Ad-hoc chat room bound to a place. Only users with a **recent check‑in** can join (window configurable).

### Authorization

- JWT required.
- The server checks for a `CheckIn` by the authenticated user for the given place within the last `APP_PLACE_CHAT_WINDOW_HOURS` (default 12). If none, the server closes with `4403`.

### Server messages on connect

- `connection_established`: `{ "type": "connection_established", "place_id": 1, "user_id": 8, "window_hours": 12 }`

### Client → Server messages

- `ping`: heartbeat
- `typing`: `{ "type": "typing", "typing": true|false }` → broadcast to room
- `message`: `{ "type": "message", "text": "Anyone around?" }` → broadcast to room

### Server → Client events

- `pong`: heartbeat response
- `typing`: broadcast to other attendees
- `message`: payload echoed to all current attendees (ephemeral; not persisted)

---

## Error Handling & Troubleshooting

- 401/4401: invalid or missing token → check that `?token=<JWT>` is appended and unexpired
- 403/4403 on DM socket: not a participant or thread not `accepted`
- 403/4403 on place socket: no recent check‑in for the place
- Timeouts during opening handshake in production usually indicate ALB routing/misconfiguration or missing health/target registration

---

## Example Connections

```
# DM thread (thread 2)
ws://<base>/ws/dms/2?token=<JWT>

# User-wide notifications (user 8)
ws://<base>/ws/user/8?token=<JWT>

# Place chat (place 1)
ws://<base>/ws/places/1/chat?token=<JWT>
```

Clients should send `ping` periodically and handle `pong`, `connection_established`, and domain events as above. No additional subscription message is required after connect.
