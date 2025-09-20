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

**Response**:

```json
{
  "items": [
    {
      "id": 1,
      "user_a_id": 123,
      "user_b_id": 456,
      "initiator_id": 123,
      "status": "accepted",
      "created_at": "2025-09-05T19:33:40Z",
      "updated_at": "2025-09-05T19:33:40Z",
      "other_user_name": "John Doe",
      "other_user_username": "johndoe",
      "other_user_avatar": "https://...AWSAccessKeyId=...",
      "last_message": "Hey, how are you?",
      "last_message_time": "2025-09-05T19:35:20Z"
    }
  ],
  "total": 25,
  "limit": 20,
  "offset": 0
}
```

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
      "liked_by_me": false,
      // Reply fields (optional)
      "reply_to_id": null,
      "reply_to_text": null,
      "reply_to_sender_name": null,
      // Media fields (optional)
      "photo_urls": [],
      "video_urls": [],
      "caption": null
    },
    {
      "id": 2,
      "thread_id": 123,
      "sender_id": 789,
      "text": "I agree!",
      "created_at": "2025-09-05T19:34:15Z",
      "seen": false,
      "heart_count": 0,
      "liked_by_me": false,
      // Reply example
      "reply_to_id": 1,
      "reply_to_text": "Hello!",
      "reply_to_sender_name": "John Doe",
      // Media example with caption
      "photo_urls": ["https://s3.amazonaws.com/bucket/photos/reply_image.jpg"],
      "video_urls": [],
      "caption": "Check out this amazing view!"
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
  "text": "Your message here",
  "reply_to_id": 123, // Optional: ID of message being replied to
  "photo_urls": ["https://..."], // Optional: Array of photo URLs
  "video_urls": ["https://..."], // Optional: Array of video URLs
  "caption": "Optional caption for media" // Optional: Caption for media messages
}
```

**Enhanced Features**:

- ✅ **Reply functionality**: Reply to specific messages
- ✅ **Threading support**: Maintain conversation context
- ✅ **Media attachments**: Photos and videos support
- ✅ **Rate limited** (20/minute)
- ✅ **Real-time delivery** via WebSocket
- ✅ **Automatic unread count updates**

**Reply Example**:

```json
{
  "text": "I agree with that!",
  "reply_to_id": 456
}
```

**Response includes reply, media, and caption information**:

```json
{
  "id": 789,
  "thread_id": 123,
  "sender_id": 111,
  "text": "I agree with that!",
  "created_at": "2025-09-05T23:45:00Z",
  "reply_to_id": 456,
  "reply_to_text": "What do you think about...",
  "reply_to_sender_name": "John Doe",
  "photo_urls": ["https://s3.amazonaws.com/..."],
  "video_urls": [],
  "caption": "Beautiful sunset view!"
}
```

**Reply to Media Message Example**:

```json
{
  "text": "Love this photo!",
  "reply_to_id": 999 // Can reply to media-only messages
}
```

**Media with Caption Example**:

```json
{
  "text": "Check this out",
  "photo_urls": ["https://s3.amazonaws.com/photo.jpg"],
  "caption": "My vacation photo from the beach!"
}
```

**Media Example**:

```json
{
  "text": "Check out this photo!",
  "photo_urls": [
    "https://s3.amazonaws.com/bucket/photos/image1.jpg",
    "https://s3.amazonaws.com/bucket/photos/image2.jpg"
  ]
}
```

### `POST /dms/upload/media` - Upload Media

**Purpose**: Upload media files (photos/videos) for DM messages

**Authentication**: ✅ **Required** (JWT Bearer Token)
**Security**: User-scoped uploads, file validation, size limits
**Content-Type**: `multipart/form-data`
**Body**: Form data with file

**Security Features**:

- ✅ **Authentication Required**: JWT token validation
- ✅ **User Isolation**: Files stored in user-specific directories
- ✅ **File Type Validation**: Only allowed image/video formats
- ✅ **Size Limits**: 10MB (images), 50MB (videos)
- ✅ **Path Sanitization**: Safe filename handling

**Supported file types**:

- **Images**: `image/jpeg`, `image/png`, `image/gif`
- **Videos**: `video/mp4`, `video/quicktime`

**File size limits**:

- **Images**: 10MB maximum
- **Videos**: 50MB maximum

**Response**:

```json
{
  "url": "https://s3.amazonaws.com/bucket/dm_media/123/photos/image.jpg",
  "media_type": "photos",
  "file_size": 2048576,
  "content_type": "image/jpeg"
}
```

**Usage Flow**:

1. Upload media file to get URL
2. Include URL in `photo_urls` or `video_urls` when sending message
3. Message will display the attached media

### `DELETE /dms/threads/{thread_id}/messages/{message_id}` - Delete Message

**Purpose**: Delete a message in a DM thread (soft delete)

**Authentication**: Required
**Response**: 204 No Content

**Features**:

- Only sender can delete their own messages
- Soft delete (message is hidden but preserved)
- Updates thread's last activity timestamp
- Maintains conversation history integrity

**Permissions**:

- ❌ Recipients cannot delete sender's messages
- ✅ Senders can delete their own messages
- ❌ Cannot delete already deleted messages

**Use Cases**:

- Remove inappropriate messages
- Correct sent messages
- Clean up conversation

**Response Codes**:

- `204`: Message deleted successfully
- `403`: Not authorized to delete this message
- `404`: Message or thread not found

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

### `POST /dms/threads/{thread_id}/messages/{message_id}/reactions` - Add Reaction

**Purpose**: Add an emoji reaction to a DM message

**Authentication**: Required
**Body**:

```json
{
  "emoji": "👍"
}
```

**Features**:

- ✅ One reaction per emoji per user per message
- ✅ Real-time reaction updates via WebSocket
- ✅ Automatic duplicate prevention

**Response**:

```json
{
  "id": 123,
  "message_id": 456,
  "user_id": 789,
  "emoji": "👍",
  "created_at": "2025-09-06T00:12:00Z"
}
```

### `DELETE /dms/threads/{thread_id}/messages/{message_id}/reactions/{emoji}` - Remove Reaction

**Purpose**: Remove an emoji reaction from a DM message

**Authentication**: Required
**URL Parameters**: `emoji` (URL-encoded emoji, e.g., `%F0%9F%91%8D` for 👍)

**Response**:

```json
{
  "success": true
}
```

### `GET /dms/threads/{thread_id}/messages/{message_id}/reactions` - Get Reactions

**Purpose**: Get all reactions for a DM message

**Authentication**: Required

**Response**:

```json
{
  "👍": [
    { "user_id": 123, "user_name": "Alice" },
    { "user_id": 456, "user_name": "Bob" }
  ],
  "❤️": [{ "user_id": 789, "user_name": "Charlie" }]
}
```

---

## 🔔 **Real-time Notifications**

The DM system now includes comprehensive real-time notifications:

### **WebSocket Events**

- `dm_message`: New message received
- `dm_reply`: Reply to your message
- `dm_media`: Media message received
- `dm_request`: New DM request received
- `reaction_update`: Message reaction added/removed

### **Notification Payload Example**

```json
{
  "type": "dm_notification",
  "thread_id": 123,
  "message": {
    "sender_id": 456,
    "sender_name": "Alice",
    "message_text": "Hey there!",
    "has_media": false,
    "is_reply": false,
    "timestamp": "2025-09-06T00:12:00Z"
  }
}
```

### **Smart Notification Types**

- **Text Messages**: `"Alice: Hey there!"`
- **Media Messages**: `"Alice sent you 2 photos"`
- **Replies**: `"Alice replied to your message"`
- **Captions**: Include caption in preview when available

### **Mute Support**

- ✅ Respect thread mute settings
- ✅ No notifications for muted threads
- ✅ User preferences honored

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
