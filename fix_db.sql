-- Fix the alembic migration state
UPDATE alembic_version SET version_num = 'add_user_collections_tables' WHERE version_num = '499278ad9251';
