#!/usr/bin/env python3
"""
Backfill topics for existing ConversationLog rows.

Usage examples:
  - Dry run, keyword-only (no LLM), limit 20:
      python backfill_topics.py --mode keyword_only --dry-run --limit 20
  - Backfill only missing topics using keyword caching (may call LLM as fallback):
      python backfill_topics.py --mode keyword_caching --limit 100 --batch-size 50 --yes
  - Reclassify all within date range using pure LLM (token heavy):
      python backfill_topics.py --mode llm --start-date 2024-01-01 --end-date 2024-12-31 --update-existing --yes
"""

import os
import sys
import argparse
from datetime import datetime, timedelta
from typing import Optional

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app
from config.database import db
from models.models_db import ConversationLog
from sqlalchemy import func

try:
    from utils.user.llm_services import (
        classify_topic_with_llm,
        classify_topic_with_keywords_caching,
    )
except Exception:
    classify_topic_with_llm = None
    classify_topic_with_keywords_caching = None


KEYWORD_MAP = {
    "nghỉ phép": [
        "chính sách nghỉ phép", "leave", "nghỉ", "phép", "xin nghỉ", "đơn xin nghỉ", "nghỉ năm",
        "annual leave", "paid leave", "unpaid leave", "nghỉ ốm", "sick leave", "maternity leave",
        "paternity leave", "compassionate leave", "nghỉ bù", "day off",
    ],
    "làm thêm giờ": [
        "làm thêm giờ", "overtime", "ot", "thêm giờ", "tăng ca", "extra hours", "after hours",
        "làm ca đêm", "night shift", "ca tối", "weekend work", "holiday work", "double pay",
    ],
    "làm việc từ xa": [
        "làm việc từ xa", "remote", "work from home", "wfh", "từ xa", "telework", "telecommute",
        "online work", "virtual work", "hybrid work", "offsite work", "remote policy",
    ],
    "nghỉ việc": [
        "nghỉ việc", "quit", "resign", "thôi việc", "xin nghỉ việc", "termination", "end contract",
        "nghỉ hưu", "retirement", "chấm dứt hợp đồng", "sa thải", "fired", "layoff", "voluntary leave",
    ],
    "quy định": [
        "policy", "quy định", "nội quy", "quy chế", "rules", "regulation", "guidelines",
        "code of conduct", "standard operating procedure", "SOP", "company policy",
    ],
    "lương thưởng": [
        "chính sách về lương", "lương", "thưởng", "salary", "bonus", "tiền", "lương bổng",
        "pay", "compensation", "allowance", "phụ cấp", "thu nhập", "payroll", "wage",
        "commission", "incentive", "13th month salary",
    ],
    "bảo hiểm": [
        "bảo hiểm", "insurance", "bhxh", "bhyt", "bảo hiểm xã hội", "bảo hiểm y tế",
        "social insurance", "health insurance", "unemployment insurance", "life insurance",
        "medical coverage", "bảo hiểm thất nghiệp",
    ],
    "đào tạo": [
        "đào tạo", "training", "học", "course", "khóa học", "onboarding", "orientation",
        "seminar", "workshop", "mentoring", "coaching", "professional development",
        "technical training", "soft skills training",
    ],
    "công việc": [
        "công việc", "work", "job", "task", "dự án", "project", "assignment", "responsibility",
        "job description", "JD", "duty", "role", "performance", "KPI", "objective",
    ],
    "chitchat": [
        "xin chào", "hello", "hi", "cảm ơn", "thank", "tạm biệt", "bye", "chào", "good morning",
        "good afternoon", "good evening", "how are you", "nice to meet you", "see you",
        "have a nice day",
    ],
}


def classify_with_keywords(question: str) -> str:
    q = (question or "").lower()
    for topic, keywords in KEYWORD_MAP.items():
        if any(keyword.lower() in q for keyword in keywords):
            return topic
    return "khác"


def classify_topic(question: str, mode: str, lang: str = "vi") -> str:
    """Classify topic based on selected mode."""
    if mode == "keyword_only":
        return classify_with_keywords(question)
    if mode == "keyword_caching":
        if classify_topic_with_keywords_caching is None:
            return classify_with_keywords(question)
        result = classify_topic_with_keywords_caching(question, lang)
        return result.get("topic", "khác")
    if mode == "llm":
        if classify_topic_with_llm is None:
            return classify_with_keywords(question)
        result = classify_topic_with_llm(question, lang)
        return result.get("topic", "khác")
    return "khác"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill topics for existing ConversationLog entries")
    parser.add_argument("--start-date", type=str, default=None, help="YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, default=None, help="YYYY-MM-DD (inclusive)")
    parser.add_argument("--user-id", type=str, default=None, help="Filter by user_id")
    parser.add_argument("--email", type=str, default=None, help="Filter by email contains")
    parser.add_argument("--limit", type=int, default=1000, help="Max rows to process")
    parser.add_argument("--offset", type=int, default=0, help="Offset for pagination")
    parser.add_argument("--batch-size", type=int, default=100, help="Commit every N updates")
    parser.add_argument("--mode", type=str, default="keyword_caching", choices=["keyword_only", "keyword_caching", "llm"], help="Classification mode")
    parser.add_argument("--lang", type=str, default="vi", help="Language for LLM-based modes")
    parser.add_argument("--update-existing", action="store_true", help="Reclassify rows that already have a topic")
    parser.add_argument("--dry-run", action="store_true", help="Do not persist changes")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation and proceed")
    return parser.parse_args()


def build_query(args: argparse.Namespace):
    query = db.session.query(ConversationLog)
    if args.start_date:
        start = datetime.strptime(args.start_date, "%Y-%m-%d")
        query = query.filter(ConversationLog.timestamp >= start)
    if args.end_date:
        end = datetime.strptime(args.end_date, "%Y-%m-%d") + timedelta(days=1)
        query = query.filter(ConversationLog.timestamp < end)
    if args.user_id:
        query = query.filter(ConversationLog.user_id == args.user_id)
    if args.email:
        query = query.filter(ConversationLog.email.ilike(f"%{args.email}%"))
    if not args.update_existing:
        query = query.filter((ConversationLog.topic.is_(None)) | (ConversationLog.topic == ""))
    return query.order_by(ConversationLog.timestamp.asc())


def main():
    args = parse_args()
    with app.app_context():
        query = build_query(args)
        total_candidates = query.count()
        print(f"Found {total_candidates} candidate rows to process.")
        if total_candidates == 0:
            print("Nothing to do.")
            return

        query = query.offset(args.offset).limit(args.limit)
        rows = query.all()
        print(f"Loaded {len(rows)} rows (offset={args.offset}, limit={args.limit}).")

        if not args.yes:
            print("Add --yes to proceed without confirmation.")
            print("This is a dry run by default." if args.dry_run else "This will update the database.")
            return

        updated = 0
        processed = 0
        batch_counter = 0

        for row in rows:
            processed += 1
            original_topic: Optional[str] = row.topic
            try:
                topic = classify_topic(row.question, mode=args.mode, lang=args.lang)
            except Exception as e:
                print(f"[ERROR] Classify failed for row id={row.id}: {e}")
                continue

            if not topic:
                topic = "khác"

            will_update = args.update_existing or (not original_topic)
            if will_update:
                print(f"id={row.id}: '{row.question[:60]}...' -> topic='{topic}' (was='{original_topic}')")
                if not args.dry_run:
                    row.topic = topic
                    updated += 1
                    batch_counter += 1
                    if batch_counter >= args.batch_size:
                        try:
                            db.session.commit()
                            batch_counter = 0
                        except Exception as e:
                            db.session.rollback()
                            print(f"[ERROR] Commit failed: {e}")
            else:
                print(f"id={row.id}: skip (existing topic='{original_topic}')")

        if not args.dry_run and batch_counter > 0:
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f"[ERROR] Final commit failed: {e}")

        print("---")
        print(f"Processed: {processed}")
        print(f"Updated:   {updated}{' (dry-run)' if args.dry_run else ''}")
        print(f"Mode:      {args.mode}")


if __name__ == "__main__":
    main()
