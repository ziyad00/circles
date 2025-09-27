-- Create user 60 to fix check-in foreign key constraint issues
INSERT INTO users (id, phone, is_verified, created_at, updated_at)
VALUES (60, '+2222222222', true, NOW(), NOW())
ON CONFLICT (id) DO NOTHING;

-- Verify user was created
SELECT id, phone, is_verified, created_at FROM users WHERE id = 60;