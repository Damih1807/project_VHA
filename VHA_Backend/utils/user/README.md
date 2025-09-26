# Chat Utils Refactor

## Tổng quan

File `chat_utils.py` đã được refactor thành các module nhỏ hơn để cải thiện khả năng bảo trì và đọc hiểu. Tất cả logic và hành vi hiện tại được giữ nguyên.

## Cấu trúc mới

### 1. `llm_services.py`
- **Chức năng**: Xử lý các dịch vụ LLM và AI
- **Functions chính**:
  - `chatgpt_generate()`: Generate response từ OpenAI
  - `process_question_with_llm()`: Phân tích câu hỏi bằng LLM
  - `build_prompt()`: Tạo prompt cho LLM

### 2. `language_utils.py`
- **Chức năng**: Xử lý language detection và classification
- **Functions chính**:
  - `detect_language()`: Phát hiện ngôn ngữ
  - `unified_classification()`: Phân loại câu hỏi thống nhất
  - `should_use_hr_training_data()`: Kiểm tra sử dụng HR training data
  - `should_skip_chitchat()`: Kiểm tra skip chitchat

### 3. `keywords_utils.py`
- **Chức năng**: Xử lý keywords và context analysis
- **Functions chính**:
  - `is_hr_related_question()`: Kiểm tra câu hỏi HR
  - `check_keywords_in_docs()`: Kiểm tra keywords trong docs
  - `enhance_question_for_search()`: Tăng cường câu hỏi tìm kiếm
  - `lightweight_context_analysis()`: Phân tích context nhẹ
  - `enhance_question_with_context()`: Tăng cường câu hỏi với context

### 4. `vector_store_utils.py`
- **Chức năng**: Xử lý vector store và document retrieval
- **Functions chính**:
  - `get_latest_n_files()`: Lấy file mới nhất
  - `load_multiple_vector_stores()`: Load nhiều vector stores
  - `retrieve_relevant_docs()`: Lấy documents liên quan
  - `build_context()`: Xây dựng context từ documents
  - `prioritize_files_for_hr_questions()`: Ưu tiên file cho câu hỏi HR

### 5. `chitchat_handler.py`
- **Chức năng**: Xử lý chitchat
- **Functions chính**:
  - `handle_chitchat()`: Xử lý chitchat
  - `is_basic_greeting()`: Kiểm tra greeting cơ bản
  - `should_handle_as_chitchat()`: Kiểm tra xử lý như chitchat

### 6. `response_utils.py`
- **Chức năng**: Xử lý response và notifications
- **Functions chính**:
  - `notify_no_documents()`: Thông báo không có documents
  - `notify_error_loading_vectors()`: Thông báo lỗi load vectors
  - `notify_no_answer_found()`: Thông báo không tìm thấy câu trả lời
  - `validate_response()`: Validate response
  - `handle_follow_up_questions()`: Xử lý câu hỏi follow-up

### 7. `chat_utils.py` (file chính)
- **Chức năng**: Orchestrate tất cả các module
- **Functions chính**:
  - `get_response_from_multiple_sources()`: Function chính
  - `_handle_conversation_memory()`: Xử lý conversation memory
  - `_enhance_question_for_search()`: Tăng cường câu hỏi tìm kiếm
  - `_save_conversation_message()`: Lưu message vào conversation

## Lợi ích của refactor

1. **Tách biệt trách nhiệm**: Mỗi module có một chức năng cụ thể
2. **Dễ bảo trì**: Có thể sửa đổi từng module độc lập
3. **Dễ test**: Có thể test từng module riêng biệt
4. **Dễ đọc hiểu**: Code ngắn gọn, rõ ràng hơn
5. **Tái sử dụng**: Các function có thể được sử dụng ở nhiều nơi

## Cách sử dụng

```python
from utils.user.chat_utils import get_response_from_multiple_sources

# Sử dụng function chính như trước
response = get_response_from_multiple_sources(
    question="Câu hỏi của bạn",
    retrieve_k=5,
    rerank_k=3
)
```

## Import các function riêng lẻ

```python
from utils.user.llm_services import chatgpt_generate
from utils.user.language_utils import detect_language
from utils.user.keywords_utils import is_hr_related_question
# ... và các function khác
```

## Lưu ý

- Tất cả logic và flow xử lý được giữ nguyên
- Không có tính năng mới được thêm vào
- Chỉ cải thiện cấu trúc code để dễ bảo trì hơn 