# 📱 Direct Messages (DM) Endpoints - Complete API Guide

## Overview

The DM system provides a comprehensive messaging platform with privacy controls, real-time features, and advanced thread management.

---

## 🔐 Authentication & Privacy

### Privacy Settings

- `everyone`: Anyone can send DM requests
- `followers`: Only followers can send requests
- `no_one`: No one can send requests

### Rate Limiting

- **DM Requests**: 5 per minute per user
- **DM Messages**: 20 per minute per user

---

## 📨 DM Request Management

### `POST /dms/requests` - Send DM Request

**Purpose**: Start a conversation with another user

**Authentication**: Required  
**Body**:

```json
{
  "recipient_id": 123,
  "text": "Hello!"
}
```

**Features**:

- Respects recipient's DM privacy settings
- Auto-accepts if sender follows recipient
- Rate limited (5/minute)

### `GET /dms/requests` - List Incoming DM Requests

**Purpose**: View pending DM requests you received

**Authentication**: Required  
**Returns**: Array of pending threads

```json
[
  {
    "id": 1,
    "status": "pending",
    "initiator_id": 123,
    "user_a_id": 123,
    "user_b_id": 456
  }
]
```

### `PUT /dms/requests/{thread_id}` - Accept/Reject DM Request

**Purpose**: Respond to DM request

**Authentication**: Required  
**Body**:

```json
{
  "status": "accepted" // or "rejected"
}
```

---

## 💬 DM Thread Management

### `GET /dms/inbox` - DM Inbox

**Purpose**: View all active DM conversations

**Authentication**: Required  
**Query Parameters**:

- `q`: Search messages or participant names
- `include_archived`: Include archived threads (default: false)
- `only_pinned`: Show only pinned threads (default: false)
- `limit`: Page size (default: 20)
- `offset`: Pagination offset (default: 0)

**Features**:

- Advanced search and filtering
- Pinned threads appear first
- Ordered by most recent activity

### `GET /dms/threads/{thread_id}/messages` - List Messages

**Purpose**: Get messages in a DM thread

**Authentication**: Required  
**Query Parameters**:

- `limit`: Messages per page (default: 50)
- `offset`: Pagination offset (default: 0)

**Response**:

```json
{
  "items": [
    {
      "id": 1,
      "thread_id": 123,
      "sender_id": 456,
      "text": "Hello!",
      "created_at": "2025-09-05T19:33:40Z",
      "seen": true,
      "heart_count": 2,
      "liked_by_me": false
    }
  ],
  "total": 25,
  "limit": 50,
  "offset": 0
}
```

### `POST /dms/threads/{thread_id}/messages` - Send Message

**Purpose**: Send a message in an active DM thread

**Authentication**: Required  
**Body**:

```json
{
  "text": "Your message here"
}
```

**Features**:

- Rate limited (20/minute)
- Real-time delivery via WebSocket
- Automatic unread count updates

---

## 🔔 Notifications & Status

### `GET /dms/unread-count` - Total Unread Messages

**Purpose**: Get count of unread messages across all threads

**Authentication**: Required  
**Returns**:

```json
{
  "unread": 5
}
```

### `GET /dms/threads/{thread_id}/unread-count` - Thread Unread Count

**Purpose**: Get unread message count for specific thread

**Authentication**: Required  
**Returns**:

```json
{
  "unread": 2
}
```

### `POST /dms/threads/{thread_id}/mark-read` - Mark Thread as Read

**Purpose**: Mark all messages in thread as read

**Authentication**: Required  
**Response**: 204 No Content

---

## ⚙️ Thread Settings

### `PUT /dms/threads/{thread_id}/mute` - Mute/Unmute Thread

**Body**:

```json
{
  "muted": true
}
```

### `PUT /dms/threads/{thread_id}/pin` - Pin/Unpin Thread

**Body**:

```json
{
  "pinned": true
}
```

### `PUT /dms/threads/{thread_id}/archive` - Archive/Unarchive Thread

**Body**:

```json
{
  "archived": true
}
```

### `PUT /dms/threads/{thread_id}/block` - Block/Unblock User

**Body**:

```json
{
  "blocked": true
}
```

---

## ⌨️ Typing & Presence Indicators

### `POST /dms/threads/{thread_id}/typing` - Set Typing Status

**Body**:

```json
{
  "typing": true
}
```

**Response**: 204 No Content

### `GET /dms/threads/{thread_id}/typing` - Get Typing Status

**Returns**:

```json
{
  "typing": true,
  "until": "2025-09-05T19:33:40Z"
}
```

### `GET /dms/threads/{thread_id}/presence` - Get User Presence

**Returns**:

```json
{
  "user_id": 123,
  "online": true,
  "last_active_at": "2025-09-05T19:33:40Z"
}
```

---

## ❤️ Message Reactions

### `POST /dms/threads/{thread_id}/messages/{message_id}/heart` - Like Message

**Purpose**: Toggle heart/like on a message

**Returns**:

```json
{
  "liked": true,
  "heart_count": 5
}
```

---

## 🌐 WebSocket Endpoints

### `WebSocket /ws/dms/{thread_id}` - Real-time DM Chat

**Purpose**: Real-time messaging in DM threads

**Features**:

- Send/receive messages instantly
- Typing indicators
- Online presence
- Message reactions
- Unread count updates

#### WebSocket Message Types:

**Connection Established**:

```json
{
  "type": "connection_established",
  "thread_id": 123,
  "user_id": 456,
  "timestamp": "2025-09-05T19:33:40Z"
}
```

**New Message**:

```json
{
  "type": "new_message",
  "message": {
    "id": 1,
    "thread_id": 123,
    "sender_id": 456,
    "text": "Hello!",
    "created_at": "2025-09-05T19:33:40Z"
  }
}
```

**Typing Update**:

```json
{
  "type": "typing_update",
  "user_id": 456,
  "typing": true
}
```

**Presence Update**:

```json
{
  "type": "presence_update",
  "user_id": 456,
  "online": true
}
```

---

## 🛡️ Security Features

- **Authentication**: JWT required for all endpoints
- **Authorization**: Only thread participants can access
- **Rate Limiting**: Prevents spam and abuse
- **Blocking**: Users can block others
- **Privacy Controls**: Granular DM privacy settings
- **Input Validation**: Message length and content validation

---

## 📊 Usage Flow Example

1. **Send DM Request**:

   ```bash
   POST /dms/requests
   {
     "recipient_id": 123,
     "text": "Hello!"
   }
   ```

2. **Accept Request**:

   ```bash
   PUT /dms/requests/456
   {
     "status": "accepted"
   }
   ```

3. **Send Message**:

   ```bash
   POST /dms/threads/456/messages
   {
     "text": "How are you?"
   }
   ```

4. **Real-time Chat**:

   ```javascript
   const ws = new WebSocket("ws://localhost:8000/ws/dms/456");
   ```

5. **Mark Read**:
   ```bash
   POST /dms/threads/456/mark-read
   ```

---

## 🔧 Response Codes

- `200`: Success
- `201`: Created
- `204`: No Content
- `400`: Bad Request
- `401`: Unauthorized
- `403`: Forbidden (privacy/blocked)
- `404`: Thread/Message not found
- `429`: Rate limit exceeded
- `500`: Internal server error

---

## 📝 Notes

- All endpoints require JWT authentication
- Thread participants only can access thread-specific endpoints
- Rate limits prevent spam and abuse
- WebSocket provides real-time features
- Privacy settings control who can send requests
- Blocking prevents future messages from specific users

The DM system provides a complete messaging experience with privacy controls, real-time features, and comprehensive management options! 🚀
