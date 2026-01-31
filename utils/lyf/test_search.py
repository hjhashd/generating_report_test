import asyncio
import httpx
from bs4 import BeautifulSoup
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def web_search(query: str, max_results: int = 5) -> str:
    logger.info(f"🌐 正在执行真实联网搜索: {query}")
    url = "https://html.duckduckgo.com/html/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {"q": query}
    
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.post(url, data=data, headers=headers)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "html.parser")
            results = []
            
            for i, result in enumerate(soup.find_all("div", class_="result"), 1):
                if i > max_results:
                    break
                
                title_tag = result.find("a", class_="result__a")
                snippet_tag = result.find("a", class_="result__snippet")
                
                if title_tag and snippet_tag:
                    title = title_tag.get_text(strip=True)
                    link = title_tag.get("href")
                    snippet = snippet_tag.get_text(strip=True)
                    results.append(f"[{i}] 标题: {title}\n    链接: {link}\n    摘要: {snippet}")
            
            if not results:
                return "未找到相关搜索结果。"
            
            return "\n\n".join(results)
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"搜索过程中发生错误: {str(e)}"

async def main():
    result = await web_search("2024年中国节能降碳政策")
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
