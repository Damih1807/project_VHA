# 🤖 VHA Backend - AI Chatbot System

Hệ thống chatbot AI thông minh với khả năng xử lý câu hỏi HR, chitchat, và tìm kiếm tài liệu.

## ✨ **Tính Năng Chính**

- 🤖 **AI Chatbot** với LLM processing
- 🧠 **Unified Classification** (LLM + FAISS)
- 💾 **Conversation Memory** với Redis fallback
- 🔍 **Context Analysis** lightweight
- 📚 **Document Search** với vector embeddings
- 🌐 **Multi-language Support** (VI/EN)
- ⚡ **Performance Optimized**

## 🚀 **Quick Start**

### **1. Clone Repository**
```bash
git clone <repository-url>
cd VHA_Backend
```

### **2. Auto Setup (Recommended)**
```bash
# Windows
python setup.py

# Linux/Mac
python3 setup.py
```

### **3. Manual Setup (Alternative)**

#### **Prerequisites**
- Python 3.8+
- pip
- Git

#### **Step 1: Create Virtual Environment**
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/Mac
python3 -m venv venv
source venv/bin/activate
```

#### **Step 2: Install Dependencies**
```bash
pip install -r requirements.txt
```

#### **Step 3: Setup Environment**
```bash
# Copy environment template
cp env.example .env

# Edit .env with your credentials
nano .env  # or use any text editor
```

#### **Step 4: Create Directories**
```bash
mkdir -p data data_chatting faiss_indexes uploads logs
```

## ⚙️ **Configuration**

### **Environment Variables (.env)**

```env
# AWS Configuration (Required)
ACCESS_KEY_ID=your_aws_access_key_id
SECRET_ACCESS_KEY=your_aws_secret_access_key
REGION=us-east-1
BUCKET_NAME=your_s3_bucket_name

# OpenAI Configuration (Required)
OPENAI_API_KEY=your_openai_api_key

# Bedrock Configuration (Required)
MODEL_ID=amazon.titan-embed-text-v1

# Redis Configuration (Optional)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
```

### **Required Services**

#### **1. AWS Account**
- **S3 Bucket**: Lưu trữ documents và vector indexes
- **Bedrock**: Embeddings và AI services
- **IAM User**: Access keys với quyền S3 và Bedrock

#### **2. OpenAI Account**
- **API Key**: Cho LLM processing
- **Model**: gpt-4o-mini (recommended)

#### **3. Redis (Optional)**
```bash
# Install Redis
# Ubuntu/Debian
sudo apt-get install redis-server

# macOS
brew install redis

# Windows
# Download from https://redis.io/download
```

## 🏃‍♂️ **Running the Application**

### **1. Activate Virtual Environment**
```bash
# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### **2. Run Application**
```bash
python app.py
```

### **3. Test Integration**
```bash
python test_integration.py
```

## 📁 **Project Structure**

```
VHA_Backend/
├── app.py                          # Main application
├── requirements.txt                # Python dependencies
├── setup.py                       # Auto setup script
├── env.example                    # Environment template
├── README.md                      # This file
├── utils/
│   ├── user/
│   │   ├── chat_utils.py          # Main chatbot logic
│   │   ├── conversation_memory.py # Memory management
│   │   ├── enhanced_chitchat_classifier.py
│   │   └── contextual_understanding.py
│   ├── admin/
│   │   └── upload_s3_utils.py     # S3 utilities
│   └── aws_client.py              # AWS client
├── data/                          # Document storage
├── data_chatting/                 # Training data
│   ├── hr_training_data.json
│   └── enhanced_chitchat_data.json
├── faiss_indexes/                 # Vector indexes
│   ├── chitchat_index/
│   ├── hr_index/
│   └── file_registry.json
├── uploads/                       # File uploads
└── logs/                          # Application logs
```

## 🧪 **Testing**

### **Run All Tests**
```bash
python test_integration.py
```

### **Test Specific Components**
```python
# Test classification
from utils.user.chat_utils import unified_classification
result = unified_classification("ở Việt Nam có những ngày lễ nào ?")

# Test conversation memory
from utils.user.conversation_memory import create_user_conversation
conversation_id = create_user_conversation("test_user")

# Test context analysis
from utils.user.chat_utils import lightweight_context_analysis
context = lightweight_context_analysis("nghỉ việc có được trợ cấp không ?")
```

## 🔧 **Troubleshooting**

### **Common Issues**

#### **1. Import Errors**
```bash
# Make sure virtual environment is activated
# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

#### **2. AWS Credentials Error**
```bash
# Check .env file
cat .env

# Verify AWS credentials
aws sts get-caller-identity
```

#### **3. Redis Connection Error**
```bash
# Redis is optional - system will use local cache
# To enable Redis:
sudo systemctl start redis  # Linux
brew services start redis   # macOS
```

#### **4. OpenAI API Error**
```bash
# Check API key in .env
# Verify OpenAI account and billing
```

### **Performance Issues**

#### **Slow Response Times**
- Check internet connection
- Verify AWS/OpenAI API limits
- Consider upgrading API plans

#### **Memory Issues**
- Increase system RAM
- Optimize batch sizes in code
- Use Redis for better memory management

## 📊 **API Endpoints**

### **Chat Endpoint**
```http
POST /chat
Content-Type: application/json

{
    "question": "ở Việt Nam có những ngày lễ nào ?",
    "user_id": "user123",
    "conversation_id": "conv456"
}
```

### **Upload Document**
```http
POST /upload
Content-Type: multipart/form-data

file: [PDF/DOCX file]
```

### **Health Check**
```http
GET /health
```

## 🔒 **Security**

### **Environment Variables**
- Never commit `.env` file
- Use strong API keys
- Rotate credentials regularly

### **File Uploads**
- Validate file types
- Scan for malware
- Limit file sizes

### **API Security**
- Rate limiting
- Authentication (if needed)
- Input validation

## 📈 **Monitoring**

### **Logs**
```bash
# Application logs
tail -f logs/app.log

# Error logs
tail -f logs/error.log
```

### **Performance Metrics**
- Response time
- Memory usage
- API call counts
- Error rates

## 🤝 **Contributing**

### **Development Setup**
```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Run linting
flake8 .

# Run tests
pytest

# Format code
black .
```

### **Code Style**
- Follow PEP 8
- Use type hints
- Add docstrings
- Write tests

## 📄 **License**

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 **Support**

### **Documentation**
- [API Documentation](docs/api.md)
- [Architecture Overview](docs/architecture.md)
- [Deployment Guide](docs/deployment.md)

### **Issues**
- Create GitHub issue
- Provide error logs
- Include environment details

### **Contact**
- Email: support@example.com
- Slack: #vha-backend

---

**Made with ❤️ by VHA Team**



