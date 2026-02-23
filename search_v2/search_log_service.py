def log_search_to_db(conn, data: dict):
    cursor = conn.cursor()

    sql = """
    INSERT INTO search_logs
    (session_id, user_input, analyze_type, analyze_payload,
     optimized_query, affiliate_count)
    VALUES (%s, %s, %s, %s, %s, %s)
    """

    cursor.execute(sql, (
        data.get("session_id"),
        data.get("user_input"),
        data.get("analyze_type"),
        json.dumps(data.get("analyze_payload")),
        data.get("optimized_query"),
        data.get("affiliate_count"),
    ))

    conn.commit()