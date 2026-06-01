import sqlite3

SEED_QUERY = """
-- 1. If another ID is squatting on the 'superuser' username, delete it first to prevent conflicts
DELETE FROM users 
WHERE username = 'superuser' AND id != 1;

-- 2. Insert or forcefully overwrite ID 1 to be our master 'superuser'
INSERT INTO users (
    id, 
    username, 
    full_name, 
    password, 
    role, 
    is_active
) VALUES (
    1, 
    'superuser', 
    'System Administrator', 
    'admin123', 
    'superuser', 
    1
)
ON CONFLICT (id) 
DO UPDATE SET 
    username = EXCLUDED.username,
    full_name = EXCLUDED.full_name,
    role = EXCLUDED.role,
    is_active = EXCLUDED.is_active;
"""