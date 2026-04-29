"""Database access for llm-convos."""

from __future__ import annotations

from functools import lru_cache

import llm
import sqlite_utils


def get_db_path(database: str | None = None) -> str:
    if database:
        return database
    return str(llm.user_dir() / "logs.db")


def open_db(database: str | None = None) -> sqlite_utils.Database:
    return sqlite_utils.Database(get_db_path(database))


def fetch_rows(
    limit: int, search: str | None, database: str | None
) -> list[tuple[str, str | None, int, str, str]]:
    """Return (id, model, num_responses, last_active, matched_text) per conversation.

    Sorted by last_active descending. If `search` is given, only conversations
    where any prompt or response matches (case-insensitive) are returned, and
    `matched_text` is set to the first matching prompt or response. Pass
    `limit=-1` to disable the limit.
    """
    db = open_db(database)

    if search:
        match_cte = """
        , best_match AS (
            SELECT conversation_id,
                CASE WHEN lower(prompt) LIKE lower(:search) THEN prompt ELSE response END AS matched_text
            FROM (
                SELECT conversation_id, prompt, response,
                    ROW_NUMBER() OVER (
                        PARTITION BY conversation_id
                        ORDER BY
                            CASE WHEN lower(prompt) LIKE lower(:search) THEN 0 ELSE 1 END,
                            datetime_utc ASC
                    ) AS rn
                FROM responses
                WHERE conversation_id IS NOT NULL
                  AND (lower(prompt) LIKE lower(:search) OR lower(response) LIKE lower(:search))
            ) sub
            WHERE rn = 1
        )
        """
        match_join = "JOIN best_match bm ON bm.conversation_id = c.id"
        select_extra = ", bm.matched_text"
    else:
        match_cte = ""
        match_join = ""
        select_extra = ", fp.prompt AS matched_text"

    query = f"""
        WITH ranked AS (
            SELECT r.conversation_id, r.prompt, r.datetime_utc, r.model, r.response,
                ROW_NUMBER() OVER (PARTITION BY r.conversation_id ORDER BY r.datetime_utc ASC) AS rn_first,
                ROW_NUMBER() OVER (PARTITION BY r.conversation_id ORDER BY r.datetime_utc DESC) AS rn_last
            FROM responses r WHERE r.conversation_id IS NOT NULL
        ),
        first_prompt AS (SELECT conversation_id, prompt, datetime_utc, model FROM ranked WHERE rn_first = 1),
        last_activity AS (SELECT conversation_id, datetime_utc AS last_dt FROM ranked WHERE rn_last = 1),
        msg_counts AS (
            SELECT conversation_id, COUNT(*) AS num_responses
            FROM responses WHERE conversation_id IS NOT NULL GROUP BY conversation_id
        )
        {match_cte}
        SELECT c.id, fp.model, mc.num_responses, la.last_dt AS last_active {select_extra}
        FROM conversations c
        JOIN first_prompt fp ON fp.conversation_id = c.id
        JOIN last_activity la ON la.conversation_id = c.id
        JOIN msg_counts mc ON mc.conversation_id = c.id
        {match_join}
        ORDER BY la.last_dt DESC
        {"" if limit == -1 else "LIMIT :limit"}
    """
    params: dict = {"search": f"%{search}%"} if search else {}
    if limit != -1:
        params["limit"] = limit
    return list(db.execute(query, params).fetchall())


@lru_cache(maxsize=128)
def fetch_messages(cid: str, database: str | None) -> list[tuple[str, str]]:
    """Return list of (role, text) for a conversation, oldest first."""
    db = open_db(database)
    rows = db.execute(
        "SELECT prompt, response FROM responses WHERE conversation_id = ? ORDER BY datetime_utc ASC",
        [cid],
    ).fetchall()
    messages: list[tuple[str, str]] = []
    for prompt, response in rows:
        messages.append(("user", prompt or ""))
        messages.append(("assistant", response or ""))
    return messages
