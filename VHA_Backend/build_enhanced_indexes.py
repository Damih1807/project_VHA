#!/usr/bin/env python3
"""
Script để xây dựng index cho enhanced chitchat và HR training data
"""

import os
import sys
from dotenv import load_dotenv
import boto3
from langchain_community.embeddings import BedrockEmbeddings
from utils.user.enhanced_chitchat_classifier import EnhancedChitchatClassifier

load_dotenv()

def main():
    print("🚀 Bắt đầu xây dựng enhanced indexes...")
    
    session = boto3.Session(
        aws_access_key_id=os.getenv("ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("SECRET_ACCESS_KEY"),
        region_name=os.getenv("REGION")
    )
    
    bedrock_client = session.client(service_name="bedrock-runtime")
    bedrock_embeddings = BedrockEmbeddings(
        model_id=os.getenv("MODEL_ID"),
        client=bedrock_client
    )
    
    classifier = EnhancedChitchatClassifier(bedrock_embeddings)
    
    try:
        print("📝 Đang xây dựng chitchat index...")
        classifier.build_chitchat_index()
        print("✅ Chitchat index đã được xây dựng thành công!")
        
        print("👥 Đang xây dựng HR index...")
        classifier.build_hr_index()
        print("✅ HR index đã được xây dựng thành công!")
        
        print("\n🧪 Testing enhanced classifier...")
        test_questions = [
            "Bạn khỏe không?",
            "Lương cơ bản của tôi là bao nhiêu?",
            "Nghỉ phép năm có bao nhiêu ngày?",
            "Bảo hiểm xã hội đóng bao nhiêu phần trăm?",
            "Có canteen không?"
        ]
        
        for question in test_questions:
            response, response_type, confidence = classifier.classify_and_respond(question)
            print(f"Q: {question}")
            print(f"A: {response[:100]}...")
            print(f"Type: {response_type}, Confidence: {confidence:.2f}")
            print("-" * 50)
        
        print("\n🎉 Hoàn thành xây dựng enhanced indexes!")
        
    except Exception as e:
        print(f"❌ Lỗi: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 