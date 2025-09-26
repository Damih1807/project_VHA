import os
import boto3
import warnings
from dotenv import load_dotenv
from langchain_community.embeddings import BedrockEmbeddings

warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*BedrockEmbeddings.*")

load_dotenv()

session = boto3.Session(
    aws_access_key_id=os.getenv("ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("SECRET_ACCESS_KEY"),
    region_name=os.getenv("REGION")
)
bedrock_client = session.client(service_name="bedrock-runtime")
s3_client = session.client("s3")
bedrock_embeddings = BedrockEmbeddings(
    model_id=os.getenv("MODEL_ID"),
    client=bedrock_client
)
print("region:", os.getenv("REGION"))