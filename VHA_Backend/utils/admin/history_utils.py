import datetime
from config.database import db
from models.models_db import ConversationLog
def get_chat_history(con_id: str, limit: int):
    """
    Lấy lịch sử hội thoại theo conversation_id (con_id), mặc định lấy 3 lượt gần nhất.
    """
    if not con_id:
        return []

    logs = (
        ConversationLog.query
        .filter_by(con_id=con_id)
        .order_by(ConversationLog.timestamp.asc())
        .limit(limit)
        .all()
    )

    chat_history = []
    for log in logs:
        chat_history.append({"role": "user", "content": log.question})
        chat_history.append({"role": "assistant", "content": log.answer})

    return chat_history
def save_conversation_log(con_id, user_id, email, question, answer):
    """
    Lưu một lượt hội thoại vào DB.
    """
    if not all([con_id, email, question, answer]):
        return

    log = ConversationLog(
        con_id=con_id,
        user_id=user_id,
        email=email,
        question=question,
        answer=answer,
        timestamp=datetime.now()
    )
    db.session.add(log)
    db.session.commit()
