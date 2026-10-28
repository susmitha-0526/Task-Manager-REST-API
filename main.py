"""Task Manager REST API - FastAPI + SQLite.

Run with:  uvicorn main:app --reload
Docs at:   http://127.0.0.1:8000/docs
"""

import sqlite3
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status

from auth import verify_api_key
from database import get_db, init_db
from schemas import Priority, TaskCreate, TaskOut, TaskUpdate


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # create tables on startup
    yield


app = FastAPI(
    title="Task Manager API",
    description="A simple REST API for managing tasks, built with FastAPI and SQLite. "
    "Authenticate by sending the `X-API-Key` header.",
    version="1.0.0",
    lifespan=lifespan,
)


def row_to_task(row: sqlite3.Row) -> dict:
    task = dict(row)
    task["completed"] = bool(task["completed"])
    return task


def get_task_or_404(db: sqlite3.Connection, task_id: int) -> sqlite3.Row:
    row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return row


@app.get("/health", tags=["System"])
def health_check():
    """Public endpoint to check the API is running."""
    return {"status": "ok"}


@app.post(
    "/tasks",
    response_model=TaskOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Tasks"],
    dependencies=[Depends(verify_api_key)],
)
def create_task(task: TaskCreate, db: sqlite3.Connection = Depends(get_db)):
    """Create a new task."""
    cursor = db.execute(
        "INSERT INTO tasks (title, description, priority) VALUES (?, ?, ?)",
        (task.title, task.description, task.priority),
    )
    db.commit()
    return row_to_task(get_task_or_404(db, cursor.lastrowid))


@app.get(
    "/tasks",
    response_model=List[TaskOut],
    tags=["Tasks"],
    dependencies=[Depends(verify_api_key)],
)
def list_tasks(
    completed: Optional[bool] = Query(None, description="Filter by completion status"),
    priority: Optional[Priority] = Query(None, description="Filter by priority"),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    db: sqlite3.Connection = Depends(get_db),
):
    """List tasks with optional filters and pagination."""
    query = "SELECT * FROM tasks WHERE 1=1"
    params: list = []
    if completed is not None:
        query += " AND completed = ?"
        params.append(int(completed))
    if priority is not None:
        query += " AND priority = ?"
        params.append(priority)
    query += " ORDER BY id LIMIT ? OFFSET ?"
    params += [limit, skip]
    rows = db.execute(query, params).fetchall()
    return [row_to_task(r) for r in rows]


@app.get(
    "/tasks/{task_id}",
    response_model=TaskOut,
    tags=["Tasks"],
    dependencies=[Depends(verify_api_key)],
)
def get_task(task_id: int, db: sqlite3.Connection = Depends(get_db)):
    """Get a single task by ID."""
    return row_to_task(get_task_or_404(db, task_id))


@app.patch(
    "/tasks/{task_id}",
    response_model=TaskOut,
    tags=["Tasks"],
    dependencies=[Depends(verify_api_key)],
)
def update_task(task_id: int, update: TaskUpdate, db: sqlite3.Connection = Depends(get_db)):
    """Partially update a task. Only the fields you send are changed."""
    get_task_or_404(db, task_id)
    data = update.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields provided to update")
    if "completed" in data:
        data["completed"] = int(data["completed"])

    # Column names come from the schema (never from user input), values are parameterized.
    set_clause = ", ".join(f"{col} = ?" for col in data)
    db.execute(f"UPDATE tasks SET {set_clause} WHERE id = ?", (*data.values(), task_id))
    db.commit()
    return row_to_task(get_task_or_404(db, task_id))


@app.delete(
    "/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Tasks"],
    dependencies=[Depends(verify_api_key)],
)
def delete_task(task_id: int, db: sqlite3.Connection = Depends(get_db)):
    """Delete a task."""
    get_task_or_404(db, task_id)
    db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
