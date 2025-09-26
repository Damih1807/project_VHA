from langdetect import detect, DetectorFactory
import re
import random
import hashlib

DetectorFactory.seed = 0

def deterministic_seed(text):
    return int(hashlib.md5(text.encode()).hexdigest(), 16) % (2**32)

def get_random_topic_word_in_VN():
    keywords = [
        "Nội dung", "Thắc mắc", "Câu hỏi", "Yêu cầu",
        "Vấn đề", "Thông tin", "Tra cứu", "Kiến thức", "Điều cần biết"
    ]
    return random.choice(keywords)

def get_random_topic_word_in_EN():
    keywords = ["Question", "Topic", "Issue", "Idea", "Concern", "Suggestion"]
    return random.choice(keywords)

def generate_summary_from_question_auto_lang(question, start=4):
    if not question or question.strip() == "":
        return "No question provided."
    
    random.seed(deterministic_seed(question))

    try:
        lang = detect(question)
    except:
        lang = "en"

    words = re.findall(r'\b\w+\b', question)
    if len(words) <= start + 1:
        return "Câu hỏi chưa rõ ràng." if lang == "vi" else "No clear topic."  

    matches = list(re.finditer(r'\b\w+\b', question))
    if len(matches) <= start:
        return "Câu hỏi chưa rõ ràng." if lang == "vi" else "No clear topic."  

    start_pos = matches[start].start()
    punctuation_match = re.search(r'[.!?…:]', question[start_pos:])
    end_pos = start_pos + punctuation_match.start() if punctuation_match else len(question)

    trimmed = question[start_pos:end_pos].strip()
    phrase = " ".join(re.findall(r'\b\w+\b', trimmed))

    if not phrase:
        return "Câu hỏi chưa rõ ràng." if lang == "vi" else "No clear topic."  

    if lang == "vi":
        return f"{get_random_topic_word_in_VN()} về {phrase}."
    elif lang == "en":
        return f"{get_random_topic_word_in_EN()} về {phrase}."
    else:
        return f"{get_random_topic_word_in_VN()} về {phrase}."
