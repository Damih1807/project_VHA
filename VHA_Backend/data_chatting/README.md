# Enhanced Chatbot Training Data & Fast Response System

Thư mục này chứa dữ liệu cải thiện cho chatbot với các kịch bản trả lời và tài liệu học về HR, bao gồm **hệ thống phản hồi nhanh** cho chitchat và câu hỏi HR.

## 📁 Cấu trúc thư mục

```
data_chatting/
├── chitchat_data.json              # Dữ liệu chitchat gốc
├── enhanced_chitchat_data.json     # Dữ liệu chitchat cải thiện với responses
├── hr_training_data.json           # Dữ liệu training về HR
├── hr_quick_responses.json         # ⭐ RESPONSES NHANH CHO HR
└── README.md                       # File hướng dẫn này
```

## 🚀 Hệ thống Fast Response (MỚI)

### ⚡ Tính năng chính:
- **Phản hồi tức thì** cho chitchat và HR questions
- **Không cần AI processing** - trả lời từ database cứng
- **Admin dễ dàng quản lý** qua JSON files
- **Tự động matching** câu hỏi với độ chính xác cao

### 📋 Cách hoạt động:
1. **Phân loại intent** (chitchat, hr_inquiry, policy_inquiry)
2. **Tìm kiếm trong fast response database**
3. **Trả về ngay lập tức** nếu tìm thấy match
4. **Fallback** to AI nếu không có fast response

### 🔧 Hướng dẫn Admin thêm Fast Responses:

#### ✅ Thêm chitchat response mới:
1. Mở `enhanced_chitchat_data.json`
2. Thêm entry mới:
```json
{
  "question": "Bạn giúp được gì?",
  "response": "Tôi có thể hỗ trợ bạn với:\n✅ Chính sách nhân sự\n✅ Quy định công ty\n✅ Hướng dẫn sử dụng hệ thống"
}
```

#### ✅ Thêm HR quick response mới:
1. Mở `hr_quick_responses.json`  
2. Thêm entry mới:
```json
{
  "question": "Thời gian làm việc như thế nào?",
  "category": "Giờ làm việc",
  "response": "⏰ **Thời gian làm việc:**\n- Thứ 2-6: 8:30 - 17:30\n- Nghỉ trưa: 12:00 - 13:00\n\nBạn muốn biết thêm về quy định giờ làm không?"
}
```

## 🎯 Mục đích

### 1. Enhanced Chitchat Data (`enhanced_chitchat_data.json`)
- **Mục đích**: Cải thiện khả năng trả lời chitchat của chatbot
- **Đặc điểm**:
  - Mỗi entry có cả `question` và `response`
  - Responses được thiết kế để tự nhiên, thân thiện
  - Tích hợp thông tin về chính sách công ty
  - Hỗ trợ cả tiếng Việt và tiếng Anh

### 2. HR Training Data (`hr_training_data.json`)
- **Mục đích**: Cung cấp kiến thức chuyên sâu về HR
- **Danh mục**:
  - **Lương thưởng**: Lương cơ bản, thưởng, phụ cấp
  - **Nghỉ phép**: Quy định nghỉ phép, đăng ký, các loại nghỉ
  - **Bảo hiểm**: BHXH, BHYT, BHTN, các loại bảo hiểm khác
  - **Hợp đồng lao động**: Thử việc, chính thức, điều kiện
  - **Phúc lợi**: Canteen, xe đưa đón, gym, team building
  - **Kỷ luật**: Quy định, hình thức xử lý
  - **Đào tạo và phát triển**: Khóa học, mentor, thăng tiến
  - **Môi trường làm việc**: Giờ làm, cơ sở vật chất

## 🚀 Cách sử dụng

### 1. Xây dựng Index

Chạy script để xây dựng index cho dữ liệu mới:

```bash
python build_enhanced_indexes.py
```

### 2. Sử dụng trong code

```python
from utils.user.enhanced_chitchat_classifier import EnhancedChitchatClassifier, get_enhanced_response

# Khởi tạo classifier
classifier = EnhancedChitchatClassifier(embeddings)

# Phân loại và trả lời
response, response_type, confidence = classifier.classify_and_respond("Bạn khỏe không?")

# Hoặc sử dụng hàm tiện ích
response, response_type, confidence = get_enhanced_response("Lương cơ bản là bao nhiêu?", embeddings)
```

### 3. Cập nhật ngưỡng phân loại

```python
classifier.update_thresholds(
    chitchat_threshold=0.3,  # Ngưỡng cho chitchat
    hr_threshold=0.4         # Ngưỡng cho HR questions
)
```

## 📊 Cấu trúc dữ liệu

### Enhanced Chitchat Data
```json
{
  "question": "Bạn khỏe không?",
  "response": "Cảm ơn bạn đã hỏi thăm! Tôi luôn sẵn sàng hỗ trợ bạn với các câu hỏi về chính sách công ty..."
}
```

### HR Training Data
```json
{
  "category": "Lương thưởng",
  "questions": ["Lương cơ bản của tôi là bao nhiêu?", ...],
  "responses": ["Lương cơ bản được quy định theo hợp đồng lao động...", ...]
}
```

## 🔧 Tùy chỉnh

### 1. Thêm câu hỏi mới

**Cho chitchat:**
```json
{
  "question": "Câu hỏi mới",
  "response": "Câu trả lời mới"
}
```

**Cho HR:**
```json
{
  "category": "Danh mục mới",
  "questions": ["Câu hỏi 1", "Câu hỏi 2"],
  "responses": ["Trả lời 1", "Trả lời 2"]
}
```

### 2. Cập nhật responses

Chỉnh sửa trực tiếp trong file JSON và chạy lại script build index.

### 3. Thêm danh mục HR mới

Thêm category mới vào `hr_training_data.json` với cấu trúc tương tự.

## 📈 Hiệu suất

### Metrics theo dõi:
- **Confidence Score**: Độ tin cậy của câu trả lời (0-1)
- **Response Type**: Loại câu trả lời (chitchat, hr_*, unknown)
- **Response Time**: Thời gian phản hồi

### Tối ưu hóa:
- Sử dụng caching cho embeddings
- Parallel processing cho vector search
- Early exit khi confidence cao
- Fallback mechanisms

## 🐛 Troubleshooting

### 1. Index không được tạo
- Kiểm tra đường dẫn file dữ liệu
- Đảm bảo AWS credentials đúng
- Kiểm tra quyền ghi thư mục

### 2. Confidence thấp
- Điều chỉnh threshold
- Thêm dữ liệu training
- Cải thiện quality của responses

### 3. Response time chậm
- Kiểm tra kết nối AWS
- Giảm số lượng documents
- Tối ưu hóa embeddings

## 📝 Ghi chú

- Dữ liệu được cập nhật định kỳ
- Backup dữ liệu trước khi thay đổi
- Test thoroughly trước khi deploy
- Monitor performance metrics

## 🤝 Đóng góp

Để cải thiện dữ liệu:
1. Thêm câu hỏi/trả lời mới
2. Cải thiện chất lượng responses
3. Thêm danh mục HR mới
4. Tối ưu hóa performance

---

**Lưu ý**: Đảm bảo chạy `build_enhanced_indexes.py` sau mỗi lần cập nhật dữ liệu để rebuild index. 