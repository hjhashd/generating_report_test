
import json
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage

def test_stream():
    llm = ChatOllama(
        model="llama3.2:3b",
        base_url="http://localhost:11434",
        temperature=0.3,
    )
    
    messages = [
        SystemMessage(content="You are a helpful assistant."),
        HumanMessage(content="Hello, how are you?")
    ]
    
    print("Starting stream...")
    try:
        for chunk in llm.stream(messages):
            print(f"Chunk: {chunk.content}")
        print("Stream finished.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_stream()
