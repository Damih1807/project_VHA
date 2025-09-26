import json
import os
from typing import List
from langchain_community.vectorstores import FAISS
from langchain.schema import Document
from langchain.embeddings.base import Embeddings

CHITCHAT_DATA = "data_chatting/chitchat_data.json"
CHITCHAT_FAISS = "faiss_indexes/chitchat_index"

def build_chitchat_index(embeddings: Embeddings):
    if not os.path.exists(CHITCHAT_DATA):
        raise FileNotFoundError(f"Không tìm thấy file: {CHITCHAT_DATA}")

    with open(CHITCHAT_DATA, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    docs = [Document(page_content=entry["question"], metadata={}) for entry in raw_data]
    vectorstore = FAISS.from_documents(docs, embeddings)
    vectorstore.save_local(CHITCHAT_FAISS)

def is_chitchat(question: str, embeddings: Embeddings, threshold: float = 0.2) -> bool:
    if not os.path.exists(os.path.join(CHITCHAT_FAISS, "index.faiss")):
        build_chitchat_index(embeddings)

    vectorstore = FAISS.load_local(
        CHITCHAT_FAISS,
        embeddings,
        allow_dangerous_deserialization=True
    )

    results = vectorstore.similarity_search_with_score(question, k=1)

    if not results:
        return False

    for i, (doc, score) in enumerate(results):

        return any(score < threshold for _, score in results)


