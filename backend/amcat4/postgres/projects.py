from psycopg import AsyncConnection


async def create_project(conn: AsyncConnection, project_id: str, name: str | None = None) -> int:
    """Create a project and return its internal primary key"""
    cur = await conn.execute("INSERT INTO projects (id, name) VALUES (%s, %s) RETURNING pk", [project_id, name or project_id])
    row = await cur.fetchone()
    return row["pk"]  # type: ignore[index, call-overload]


async def get_project_pk(conn: AsyncConnection, project_id: str) -> int | None:
    cur = await conn.execute("SELECT pk FROM projects WHERE id = %s", [project_id])
    row = await cur.fetchone()
    return row["pk"] if row else None  # type: ignore[index, call-overload]


async def delete_project(conn: AsyncConnection, project_id: str) -> None:
    """Delete a project, including its fields and documents"""
    await conn.execute("DELETE FROM projects WHERE id = %s", [project_id])
