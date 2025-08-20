/**
 * WebSocket Client Example for Circles App
 * This example demonstrates how to connect to and use the real-time features
 */

class CirclesWebSocketClient {
    constructor(baseUrl = 'ws://localhost:8000') {
        this.baseUrl = baseUrl;
        this.connections = new Map(); // thread_id -> WebSocket
        this.userConnection = null;
        this.token = null;
        this.userId = null;
        this.eventHandlers = new Map();
        this.reconnectAttempts = new Map();
        this.maxReconnectAttempts = 5;
    }

    /**
     * Initialize the client with authentication token
     */
    init(token, userId) {
        this.token = token;
        this.userId = userId;
        this.connectToUserNotifications();
    }

    /**
     * Connect to user-wide notifications
     */
    connectToUserNotifications() {
        if (this.userConnection) {
            this.userConnection.close();
        }

        const ws = new WebSocket(`${this.baseUrl}/ws/user/${this.userId}?token=${this.token}`);
        
        ws.onopen = () => {
            console.log('Connected to user notifications');
            this.startPingInterval(ws);
        };

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.handleMessage(data, 'user');
        };

        ws.onclose = () => {
            console.log('User notification connection closed');
            this.handleReconnect('user', () => this.connectToUserNotifications());
        };

        ws.onerror = (error) => {
            console.error('User notification connection error:', error);
        };

        this.userConnection = ws;
    }

    /**
     * Connect to a specific DM thread
     */
    connectToThread(threadId) {
        if (this.connections.has(threadId)) {
            return this.connections.get(threadId);
        }

        const ws = new WebSocket(`${this.baseUrl}/ws/dms/${threadId}?token=${this.token}`);
        
        ws.onopen = () => {
            console.log(`Connected to thread ${threadId}`);
            this.startPingInterval(ws);
        };

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.handleMessage(data, threadId);
        };

        ws.onclose = () => {
            console.log(`Thread ${threadId} connection closed`);
            this.connections.delete(threadId);
            this.handleReconnect(threadId, () => this.connectToThread(threadId));
        };

        ws.onerror = (error) => {
            console.error(`Thread ${threadId} connection error:`, error);
        };

        this.connections.set(threadId, ws);
        return ws;
    }

    /**
     * Disconnect from a specific thread
     */
    disconnectFromThread(threadId) {
        const ws = this.connections.get(threadId);
        if (ws) {
            ws.close();
            this.connections.delete(threadId);
        }
    }

    /**
     * Send a message to a thread
     */
    sendMessage(threadId, text) {
        const ws = this.connections.get(threadId);
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
                type: 'message',
                text: text
            }));
        }
    }

    /**
     * Send typing indicator
     */
    sendTyping(threadId, typing = true) {
        const ws = this.connections.get(threadId);
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
                type: 'typing',
                typing: typing
            }));
        }
    }

    /**
     * Mark messages as read
     */
    markAsRead(threadId) {
        const ws = this.connections.get(threadId);
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
                type: 'mark_read'
            }));
        }
    }

    /**
     * Send message reaction
     */
    sendReaction(threadId, messageId, reaction = '❤️') {
        const ws = this.connections.get(threadId);
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
                type: 'reaction',
                message_id: messageId,
                reaction: reaction
            }));
        }
    }

    /**
     * Start ping interval to keep connection alive
     */
    startPingInterval(ws) {
        const pingInterval = setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ type: 'ping' }));
            } else {
                clearInterval(pingInterval);
            }
        }, 30000); // Send ping every 30 seconds
    }

    /**
     * Handle reconnection logic
     */
    handleReconnect(connectionId, reconnectFn) {
        const attempts = this.reconnectAttempts.get(connectionId) || 0;
        if (attempts < this.maxReconnectAttempts) {
            this.reconnectAttempts.set(connectionId, attempts + 1);
            const delay = Math.min(1000 * Math.pow(2, attempts), 30000); // Exponential backoff, max 30s
            
            setTimeout(() => {
                console.log(`Attempting to reconnect to ${connectionId} (attempt ${attempts + 1})`);
                reconnectFn();
            }, delay);
        } else {
            console.error(`Max reconnection attempts reached for ${connectionId}`);
        }
    }

    /**
     * Handle incoming messages
     */
    handleMessage(data, source) {
        console.log(`Received message from ${source}:`, data);

        const { type } = data;

        switch (type) {
            case 'connection_established':
                this.emit('connected', { source, data });
                break;

            case 'thread_info':
                this.emit('thread_info', { source, data });
                break;

            case 'message':
                this.emit('message', { source, data });
                break;

            case 'typing':
                this.emit('typing', { source, data });
                break;

            case 'presence':
                this.emit('presence', { source, data });
                break;

            case 'read_receipt':
                this.emit('read_receipt', { source, data });
                break;

            case 'reaction':
                this.emit('reaction', { source, data });
                break;

            case 'notification':
                this.emit('notification', { source, data });
                break;

            case 'dm_notification':
                this.emit('dm_notification', { source, data });
                break;

            case 'pong':
                // Handle pong response
                break;

            case 'error':
                this.emit('error', { source, data });
                break;

            default:
                console.log(`Unknown message type: ${type}`);
        }
    }

    /**
     * Register event handlers
     */
    on(event, handler) {
        if (!this.eventHandlers.has(event)) {
            this.eventHandlers.set(event, []);
        }
        this.eventHandlers.get(event).push(handler);
    }

    /**
     * Emit events to registered handlers
     */
    emit(event, data) {
        const handlers = this.eventHandlers.get(event);
        if (handlers) {
            handlers.forEach(handler => {
                try {
                    handler(data);
                } catch (error) {
                    console.error(`Error in event handler for ${event}:`, error);
                }
            });
        }
    }

    /**
     * Disconnect all connections
     */
    disconnect() {
        // Close all thread connections
        this.connections.forEach((ws, threadId) => {
            ws.close();
        });
        this.connections.clear();

        // Close user connection
        if (this.userConnection) {
            this.userConnection.close();
            this.userConnection = null;
        }

        // Clear reconnection attempts
        this.reconnectAttempts.clear();
    }
}

// Usage Example:
/*
const client = new CirclesWebSocketClient();

// Initialize with token and user ID
client.init('your-jwt-token', 123);

// Connect to a DM thread
client.connectToThread(456);

// Register event handlers
client.on('message', ({ source, data }) => {
    console.log(`New message in thread ${source}:`, data.message);
    // Update UI with new message
});

client.on('typing', ({ source, data }) => {
    console.log(`User ${data.user_id} is typing in thread ${source}`);
    // Show typing indicator
});

client.on('presence', ({ source, data }) => {
    console.log(`User ${data.user_id} is ${data.online ? 'online' : 'offline'}`);
    // Update presence indicator
});

client.on('notification', ({ source, data }) => {
    console.log(`New notification:`, data);
    // Show notification to user
});

// Send a message
client.sendMessage(456, 'Hello, world!');

// Send typing indicator
client.sendTyping(456, true);

// Mark as read
client.markAsRead(456);

// Send reaction
client.sendReaction(456, 789, '❤️');

// Disconnect when done
client.disconnect();
*/
