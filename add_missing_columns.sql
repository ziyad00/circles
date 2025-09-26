-- Add missing columns to places table
-- These columns are defined in the Place model but missing from the database

-- Check if columns exist before adding them
DO $$
BEGIN
    -- Add postal_code column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'places' AND column_name = 'postal_code') THEN
        ALTER TABLE places ADD COLUMN postal_code VARCHAR;
        RAISE NOTICE 'Added postal_code column';
    ELSE
        RAISE NOTICE 'postal_code column already exists';
    END IF;

    -- Add cross_street column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'places' AND column_name = 'cross_street') THEN
        ALTER TABLE places ADD COLUMN cross_street VARCHAR;
        RAISE NOTICE 'Added cross_street column';
    ELSE
        RAISE NOTICE 'cross_street column already exists';
    END IF;

    -- Add formatted_address column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'places' AND column_name = 'formatted_address') THEN
        ALTER TABLE places ADD COLUMN formatted_address TEXT;
        RAISE NOTICE 'Added formatted_address column';
    ELSE
        RAISE NOTICE 'formatted_address column already exists';
    END IF;

    -- Add distance_meters column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'places' AND column_name = 'distance_meters') THEN
        ALTER TABLE places ADD COLUMN distance_meters FLOAT;
        RAISE NOTICE 'Added distance_meters column';
    ELSE
        RAISE NOTICE 'distance_meters column already exists';
    END IF;

    -- Add venue_created_at column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'places' AND column_name = 'venue_created_at') THEN
        ALTER TABLE places ADD COLUMN venue_created_at TIMESTAMP WITH TIME ZONE;
        RAISE NOTICE 'Added venue_created_at column';
    ELSE
        RAISE NOTICE 'venue_created_at column already exists';
    END IF;

    -- Add photo_url column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'places' AND column_name = 'photo_url') THEN
        ALTER TABLE places ADD COLUMN photo_url VARCHAR;
        RAISE NOTICE 'Added photo_url column';
    ELSE
        RAISE NOTICE 'photo_url column already exists';
    END IF;

    -- Add additional_photos column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'places' AND column_name = 'additional_photos') THEN
        ALTER TABLE places ADD COLUMN additional_photos JSONB;
        RAISE NOTICE 'Added additional_photos column';
    ELSE
        RAISE NOTICE 'additional_photos column already exists';
    END IF;
END $$;
