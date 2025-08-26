-- Enable PostGIS extensions for the default database created at init time
-- This runs only when the database volume is first initialized

\connect circles

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;

