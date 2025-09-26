import tiktoken

def count_tokens(text: str) -> int:
    enc = tiktoken.encoding_for_model("gpt-3.5-turbo")
    return len(enc.encode(text))
