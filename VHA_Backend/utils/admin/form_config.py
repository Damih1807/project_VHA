from models.models_db import UserFormConfig
from config.database import db

def get_form_config(user_id: str) -> dict:
    record = db.session.query(UserFormConfig).filter_by(user_id=user_id).first()
    return {
        "retrieve_k": record.retrieve_k,
        "rerank_k": record.rerank_k,
        "enable_rerank": record.enable_rerank,
        "model": record.model
    } if record else None

def save_form_config(user_id: str, config: dict):
    record = db.session.query(UserFormConfig).filter_by(user_id=user_id).first()
    if record:
        record.retrieve_k = config["retrieve_k"]
        record.rerank_k = config["rerank_k"]
        record.enable_rerank = config["enable_rerank"]
        record.model = config["model"]
    else:
        record = UserFormConfig(
            user_id=user_id,
            **config
        )
        db.session.add(record)
    db.session.commit()
