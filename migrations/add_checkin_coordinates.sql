-- Migration to add latitude and longitude fields to check_ins table
-- Run this on your database to add the new fields

-- Add new columns (SQLite doesn't support IF NOT EXISTS for ALTER TABLE)
ALTER TABLE check_ins ADD COLUMN latitude FLOAT;
ALTER TABLE check_ins ADD COLUMN longitude FLOAT;

-- Add indexes for better performance on location-based queries
CREATE INDEX IF NOT EXISTS idx_check_ins_latitude ON check_ins(latitude);
CREATE INDEX IF NOT EXISTS idx_check_ins_longitude ON check_ins(longitude);
CREATE INDEX IF NOT EXISTS idx_check_ins_location ON check_ins(latitude, longitude);
