async def up(conn):
    await conn.execute('''
        ALTER TABLE keywords_applications
        ADD CONSTRAINT keywords_applications_name_project_id_unique
        UNIQUE (name, project_id)
    ''')

async def down(conn):
    await conn.execute('''
        ALTER TABLE keywords_applications
        DROP CONSTRAINT IF EXISTS keywords_applications_name_project_id_unique
    ''')
